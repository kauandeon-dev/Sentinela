"""Destinos das cópias externas (regra 3-2-1).

Cada cópia local verificada é replicada para um ou mais destinos:

    directory   outro disco/volume montado no servidor (HD externo, NAS, NFS)
    sftp        outro servidor, via SSH/SFTP (senha ou chave, chave do host fixada)
    s3          armazenamento de objetos compatível com S3 (AWS, Backblaze B2,
                Wasabi, Cloudflare R2, MinIO...)

Todos os destinos têm a mesma interface: enviar (de forma atômica), ler de
volta em fluxo (para conferir o SHA-256 e para restaurar), listar e excluir.
Junto de cada cópia vai um manifesto ``.json`` com os metadados — com ele, uma
instalação nova do Sentinela reencontra as cópias ("importar do destino").
"""

import errno
import os
import posixpath
import shutil
import socket
import stat
import uuid
from pathlib import Path

import paramiko

from . import compat, settings, tunnel

TYPES = {"directory": "Outro disco", "sftp": "Servidor SFTP", "s3": "Armazenamento S3"}
SECRETS = {"sftp": ("password", "private_key", "key_passphrase"), "s3": ("secret_key",)}
CHUNK = 1024 * 1024
PROBE = ".sentinela-teste"


class DestinationError(Exception):
    pass


def describe(d):
    """Texto curto do alvo, para logs e para a interface."""
    if d["type"] == "directory":
        return d.get("path", "")
    if d["type"] == "sftp":
        return f"{d.get('user')}@{d.get('host')}:{d.get('path') or '.'}"
    if d["type"] == "s3":
        where = d.get("endpoint") or f"AWS {d.get('region') or 'us-east-1'}"
        prefix = (d.get("prefix") or "").strip("/")
        return f"s3://{d.get('bucket')}/{prefix + '/' if prefix else ''} · {where}"
    return "?"


def medium(d):
    """Identifica a mídia física/serviço do destino (para contar as "2 mídias")."""
    if d["type"] == "directory":
        try:
            return f"dev:{os.stat(d['path']).st_dev}"
        except OSError:
            return f"dir:{d.get('path')}"
    if d["type"] == "sftp":
        return f"sftp:{d.get('host')}:{d.get('port') or 22}"
    return f"s3:{d.get('endpoint') or 'aws'}/{d.get('bucket')}"


def driver(d):
    cls = {"directory": DirectoryDriver, "sftp": SftpDriver, "s3": S3Driver}.get(d.get("type"))
    if not cls:
        raise DestinationError(f"Tipo de destino desconhecido: {d.get('type')}")
    return cls(d)


class Driver:
    def __init__(self, d):
        self.d = d
        self.host_key = None  # chave vista (SFTP), para registrar na 1ª conexão

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self):
        pass

    def close(self):
        pass

    def test(self):
        """Grava, lê e apaga um arquivo de teste. Retorna um resumo do destino."""
        data = b"sentinela " + uuid.uuid4().hex.encode()
        self.put_bytes(data, PROBE)
        got = bytearray()
        self.get(PROBE, got.extend)
        self.delete(PROBE)
        if bytes(got) != data:
            raise DestinationError("O arquivo de teste foi lido com conteúdo diferente do gravado")
        return self.summary()

    def summary(self):
        return describe(self.d)


# ===================================================================== disco

class DirectoryDriver(Driver):
    """Outro disco ou volume montado (USB, NAS via NFS/SMB, segundo HD)."""

    def open(self):
        self.root = Path(self.d["path"])
        try:
            new = not self.root.exists()
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if new:
                compat.private_dir(self.root)
        except OSError as e:
            raise DestinationError(_os_msg(e, f"Não foi possível acessar {self.root}")) from e
        if not os.access(self.root, os.W_OK):
            raise DestinationError(f"Sem permissão de escrita em {self.root}")

    def _p(self, name):
        return self.root / name

    def put(self, src, name, progress=None):
        part = self._p(name + ".part")
        try:
            with open(src, "rb") as fi, open(part, "wb") as fo:
                os.chmod(part, 0o600)
                for chunk in iter(lambda: fi.read(CHUNK), b""):
                    fo.write(chunk)
                    if progress:
                        progress(len(chunk))
                fo.flush()
                os.fsync(fo.fileno())
            os.replace(part, self._p(name))
        except OSError as e:
            _unlink(part)
            raise DestinationError(_os_msg(e, f"Falha ao gravar em {self.root}")) from e
        return str(self._p(name))

    def put_bytes(self, data, name):
        part = self._p(name + ".part")
        try:
            fd = compat.open_private(part)
            with os.fdopen(fd, "wb") as fo:
                fo.write(data)
                fo.flush()
                os.fsync(fo.fileno())
            os.replace(part, self._p(name))
        except OSError as e:
            _unlink(part)
            raise DestinationError(_os_msg(e, f"Falha ao gravar em {self.root}")) from e

    def get(self, name, sink, progress=None):
        try:
            with open(self._p(name), "rb") as f:
                for chunk in iter(lambda: f.read(CHUNK), b""):
                    sink(chunk)
                    if progress:
                        progress(len(chunk))
        except FileNotFoundError as e:
            raise DestinationError(f"Arquivo {name} não encontrado em {self.root}") from e
        except OSError as e:
            raise DestinationError(_os_msg(e, f"Falha ao ler {name}")) from e

    def delete(self, name):
        try:
            os.unlink(self._p(name))
        except FileNotFoundError:
            pass
        except OSError as e:
            raise DestinationError(_os_msg(e, f"Falha ao excluir {name}")) from e

    def list(self):
        try:
            return sorted(p.name for p in self.root.iterdir() if p.is_file())
        except OSError as e:
            raise DestinationError(_os_msg(e, f"Falha ao listar {self.root}")) from e

    def summary(self):
        try:
            du = shutil.disk_usage(self.root)
            return f"{self.root} · {_size(du.free)} livres"
        except OSError:
            return str(self.root)


# ====================================================================== SFTP

class SftpDriver(Driver):
    """Outro servidor, via SFTP. Usa a mesma autenticação do túnel SSH."""

    def open(self):
        d = self.d
        try:
            self.client, self.host_key = tunnel.connect(d)
        except tunnel.HostKeyMismatch as e:
            raise DestinationError(str(e).replace("na tela Conexão", "na tela Cópias externas")) from e
        except tunnel.TunnelError as e:
            raise DestinationError(str(e).replace("servidor SSH", "servidor SFTP")) from e
        try:
            self.sftp = self.client.open_sftp()
        except Exception as e:
            self.client.close()
            raise DestinationError(
                f"O servidor {d['host']} não oferece SFTP (habilite 'Subsystem sftp' no sshd): "
                f"{e or type(e).__name__}") from e
        self.sftp.get_channel().settimeout(settings.NET_TIMEOUT * 3)
        base = (d.get("path") or "").strip() or "."
        try:
            home = self.sftp.normalize(".")
        except Exception:
            home = "/"
        # Caminho relativo: dentro da pasta inicial do usuário SFTP.
        self.root = posixpath.normpath(base if base.startswith("/") else posixpath.join(home, base))
        try:
            self._mkdirs(self.root)
        except DestinationError:
            self.close()
            raise

    def _mkdirs(self, path):
        parts = [p for p in path.split("/") if p]
        cur = "/" if path.startswith("/") else ""
        for p in parts:
            cur = posixpath.join(cur, p) if cur else p
            try:
                if not stat.S_ISDIR(self.sftp.stat(cur).st_mode):
                    raise DestinationError(f"{cur} existe no servidor SFTP, mas não é uma pasta")
            except IOError:
                try:
                    self.sftp.mkdir(cur, 0o700)
                except IOError as e:
                    raise DestinationError(self._io_msg(e, f"Não foi possível criar a pasta {cur}")) from e

    def close(self):
        for o in (getattr(self, "sftp", None), getattr(self, "client", None)):
            if o is not None:
                try:
                    o.close()
                except Exception:
                    pass

    def _p(self, name):
        return posixpath.join(self.root, name)

    def _io_msg(self, e, what):
        if isinstance(e, (socket.timeout, TimeoutError)):
            return f"{what}: tempo esgotado na conexão com o servidor SFTP"
        if isinstance(e, (EOFError, paramiko.SSHException)) or "Socket is closed" in str(e):
            return f"{what}: a conexão com o servidor SFTP caiu"
        code = getattr(e, "errno", None)
        if code == errno.EACCES or "Permission denied" in str(e):
            return f"{what}: permissão negada no servidor SFTP ({self.root})"
        if code == errno.ENOENT:
            return f"{what}: caminho não encontrado no servidor SFTP"
        msg = str(e) or type(e).__name__
        if "size mismatch" in msg:
            return (f"{what}: o arquivo chegou incompleto no servidor SFTP "
                    "(disco cheio ou cota excedida?)")
        if msg in ("Failure", "[Errno None] Failure"):
            msg = "o servidor recusou a gravação (disco cheio ou cota excedida?)"
        return f"{what}: {msg}"

    def put(self, src, name, progress=None):
        part = self._p(name + ".part")
        size = os.path.getsize(src)
        sent = [0]

        def cb(done, _total):
            if progress:
                progress(done - sent[0])
            sent[0] = done
        try:
            with open(src, "rb") as f:
                self.sftp.putfo(f, part, file_size=size, callback=cb, confirm=True)
            self._rename(part, self._p(name))
        except Exception as e:
            self._try_remove(part)
            raise DestinationError(self._io_msg(e, f"Falha ao enviar {name}")) from e
        return self._p(name)

    def put_bytes(self, data, name):
        part = self._p(name + ".part")
        try:
            with self.sftp.open(part, "wb") as f:
                f.write(data)
            self._rename(part, self._p(name))
        except Exception as e:
            self._try_remove(part)
            raise DestinationError(self._io_msg(e, f"Falha ao gravar {name}")) from e

    def _rename(self, a, b):
        try:
            self.sftp.posix_rename(a, b)  # extensão do OpenSSH: substitui de forma atômica
        except IOError:
            self._try_remove(b)
            self.sftp.rename(a, b)

    def _try_remove(self, path):
        try:
            self.sftp.remove(path)
        except Exception:
            pass

    def get(self, name, sink, progress=None):
        try:
            with self.sftp.open(self._p(name), "rb") as f:
                f.prefetch()
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    sink(chunk)
                    if progress:
                        progress(len(chunk))
        except DestinationError:
            raise
        except Exception as e:
            if getattr(e, "errno", None) == errno.ENOENT:
                raise DestinationError(f"Arquivo {name} não encontrado no servidor SFTP") from e
            raise DestinationError(self._io_msg(e, f"Falha ao ler {name}")) from e

    def delete(self, name):
        try:
            self.sftp.remove(self._p(name))
        except IOError as e:
            if getattr(e, "errno", None) == errno.ENOENT:
                return
            raise DestinationError(self._io_msg(e, f"Falha ao excluir {name}")) from e
        except Exception as e:
            raise DestinationError(self._io_msg(e, f"Falha ao excluir {name}")) from e

    def list(self):
        try:
            return sorted(a.filename for a in self.sftp.listdir_attr(self.root)
                          if stat.S_ISREG(a.st_mode))
        except Exception as e:
            raise DestinationError(self._io_msg(e, "Falha ao listar a pasta remota")) from e


# ======================================================================== S3

class S3Driver(Driver):
    """Armazenamento de objetos compatível com S3."""

    def open(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise DestinationError("Biblioteca boto3 não instalada no servidor (pip install boto3)") from e
        d = self.d
        if not d.get("bucket"):
            raise DestinationError("Informe o bucket")
        self.bucket = d["bucket"].strip()
        self.prefix = (d.get("prefix") or "").strip("/")
        endpoint = (d.get("endpoint") or "").strip() or None
        if endpoint and "://" not in endpoint:
            endpoint = "https://" + endpoint
        cfg = Config(connect_timeout=settings.NET_TIMEOUT, read_timeout=settings.NET_TIMEOUT * 3,
                     retries={"max_attempts": 2, "mode": "standard"},
                     s3={"addressing_style": "path" if endpoint else "auto"},
                     signature_version="s3v4")
        self.s3 = boto3.client(
            "s3", endpoint_url=endpoint, region_name=(d.get("region") or "us-east-1").strip(),
            aws_access_key_id=(d.get("access_key") or "").strip() or None,
            aws_secret_access_key=d.get("secret_key") or None, config=cfg)
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except Exception as e:
            raise DestinationError(self._msg(e, f"Não foi possível acessar o bucket {self.bucket}")) from e

    def _k(self, name):
        return f"{self.prefix}/{name}" if self.prefix else name

    def _msg(self, e, what):
        from botocore.exceptions import (ClientError, EndpointConnectionError,
                                         NoCredentialsError, ConnectTimeoutError,
                                         ReadTimeoutError)
        if isinstance(e, ClientError):
            err = e.response.get("Error", {})
            code = str(err.get("Code", ""))
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            known = {
                "NoSuchBucket": "o bucket não existe",
                "404": "o bucket (ou objeto) não existe",
                "NoSuchKey": "objeto não encontrado",
                "AccessDenied": "acesso negado (confira as permissões da chave de acesso)",
                "403": "acesso negado (chave de acesso sem permissão ou credenciais incorretas)",
                "InvalidAccessKeyId": "chave de acesso (Access Key) inválida",
                "SignatureDoesNotMatch": "chave secreta (Secret Key) incorreta",
                "QuotaExceeded": "cota do armazenamento excedida",
                "EntityTooLarge": "arquivo maior que o permitido pelo serviço",
            }
            reason = known.get(code) or known.get(str(status)) or f"{code} {err.get('Message', '')}".strip()
            return f"{what}: {reason}"
        if isinstance(e, EndpointConnectionError):
            return f"{what}: não foi possível conectar ao endpoint ({e.kwargs.get('endpoint_url', '')})"
        if isinstance(e, (ConnectTimeoutError, ReadTimeoutError, socket.timeout)):
            return f"{what}: tempo esgotado na conexão com o armazenamento"
        if isinstance(e, NoCredentialsError):
            return f"{what}: informe a chave de acesso e a chave secreta"
        return f"{what}: {e or type(e).__name__}"

    def put(self, src, name, progress=None):
        from boto3.s3.transfer import TransferConfig
        try:
            self.s3.upload_file(src, self.bucket, self._k(name), Callback=progress,
                                Config=TransferConfig(multipart_threshold=64 * CHUNK,
                                                      multipart_chunksize=16 * CHUNK),
                                ExtraArgs={"ContentType": "application/octet-stream"})
        except Exception as e:
            raise DestinationError(self._msg(e, f"Falha ao enviar {name}")) from e
        return f"s3://{self.bucket}/{self._k(name)}"

    def put_bytes(self, data, name):
        try:
            self.s3.put_object(Bucket=self.bucket, Key=self._k(name), Body=data)
        except Exception as e:
            raise DestinationError(self._msg(e, f"Falha ao gravar {name}")) from e

    def get(self, name, sink, progress=None):
        try:
            body = self.s3.get_object(Bucket=self.bucket, Key=self._k(name))["Body"]
            for chunk in body.iter_chunks(CHUNK):
                sink(chunk)
                if progress:
                    progress(len(chunk))
        except Exception as e:
            raise DestinationError(self._msg(e, f"Falha ao ler {name}")) from e

    def delete(self, name):
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=self._k(name))
        except Exception as e:
            raise DestinationError(self._msg(e, f"Falha ao excluir {name}")) from e

    def list(self):
        out = []
        try:
            pages = self.s3.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=(self.prefix + "/") if self.prefix else "")
            for page in pages:
                for o in page.get("Contents", []):
                    rest = o["Key"][len(self.prefix) + 1:] if self.prefix else o["Key"]
                    if "/" not in rest:
                        out.append(rest)
        except Exception as e:
            raise DestinationError(self._msg(e, "Falha ao listar o bucket")) from e
        return sorted(out)


# ================================================================ utilidades

def _os_msg(e, what):
    if e.errno == errno.ENOSPC:
        return f"{what}: disco cheio"
    if e.errno == errno.EDQUOT:
        return f"{what}: cota de disco excedida"
    if e.errno in (errno.EACCES, errno.EPERM):
        return f"{what}: permissão negada"
    if e.errno == errno.EROFS:
        return f"{what}: o volume está montado somente leitura"
    if e.errno == errno.ENOENT:
        return f"{what}: caminho não encontrado (o disco está montado?)"
    if e.errno == errno.EIO:
        return f"{what}: erro de entrada/saída no disco"
    return f"{what}: {e.strerror or e}"


def _unlink(p):
    try:
        os.unlink(p)
    except OSError:
        pass


def _size(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}".replace(".", ",")
        n /= 1024
