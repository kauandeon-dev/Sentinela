"""Túnel SSH para bancos de dados em outro servidor.

Abre uma porta local (127.0.0.1:porta-aleatória) que encaminha, através do
servidor SSH, para o host/porta do banco *vistos a partir do servidor SSH*
(normalmente localhost:5432 ou localhost:3306). Os clientes pg_dump/mariadb-dump
então se conectam a essa porta local, como se o banco fosse local.

Segurança da chave do host (TOFU): na primeira conexão a impressão digital do
servidor SSH é gravada; nas seguintes, se mudar, a conexão é recusada.
"""

import base64
import hashlib
import io
import logging
import re
import select
import socket
import threading
import time
from contextlib import contextmanager

import paramiko
from cryptography.hazmat.primitives import serialization

from . import settings

log = logging.getLogger("sentinela")

# Os erros do paramiko são traduzidos e registrados pelo Sentinela; evita que
# a biblioteca imprima rastros próprios no terminal.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)


DROPPED = ("a conexão SSH caiu durante a transferência (rede indisponível, servidor SSH "
           "reiniciado ou sessão encerrada)")


class TunnelError(Exception):
    pass


class HostKeyMismatch(TunnelError):
    pass


def fingerprint(key):
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


# ------------------------------------------------------------ chave privada

_PUBLIC_KEY = re.compile(
    r"^\s*(ssh-(rsa|ed25519|dss)|ecdsa-sha2-\S+|sk-\S+)\s+AAAA|-----BEGIN (RSA )?PUBLIC KEY-----"
    r"|---- BEGIN SSH2 PUBLIC KEY ----")


def load_private_key(text, passphrase=None):
    """Carrega uma chave OpenSSH ou PEM (ed25519, RSA, ECDSA).

    Dá mensagens específicas para os erros mais comuns: chave pública colada
    no lugar da privada, formato PuTTY, chave protegida sem senha e senha errada.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise TunnelError("Cole a chave privada SSH")
    if text.startswith("PuTTY-User-Key-File"):
        raise TunnelError("Chave no formato PuTTY (.ppk) não é suportada: no PuTTYgen use "
                          "Conversions → Export OpenSSH key e cole o resultado")
    if _PUBLIC_KEY.search(text):
        raise TunnelError("Essa é a chave pública (.pub). Cole a chave privada, que começa com "
                          "-----BEGIN ... PRIVATE KEY-----")
    if "PRIVATE KEY-----" not in text:
        raise TunnelError("Chave privada inválida: cole o conteúdo completo, de "
                          "-----BEGIN ... PRIVATE KEY----- até -----END ... PRIVATE KEY-----")
    text += "\n"
    pw = passphrase or None

    # Valida criptografia/senha com a biblioteca cryptography, que distingue
    # "senha ausente" de "senha incorreta" (o paramiko não distingue).
    data = text.encode()
    loader = (serialization.load_ssh_private_key if "OPENSSH PRIVATE KEY" in text
              else serialization.load_pem_private_key)
    try:
        loader(data, pw.encode() if pw else None)
    except TypeError as e:
        msg = str(e).lower()
        if "not encrypted" not in msg and any(
                k in msg for k in ("not given", "not provided", "password-protected", "encrypted")):
            raise TunnelError("A chave privada está protegida: informe a senha da chave") from e
        if "not encrypted" in msg:
            pw = None  # senha informada, mas a chave não tem senha: ignora
        else:
            raise TunnelError(f"Chave privada inválida: {e}") from e
    except ValueError as e:
        if pw:
            raise TunnelError("Senha da chave incorreta (ou chave corrompida)") from e
        raise TunnelError("Chave privada inválida ou corrompida") from e
    except Exception as e:  # algoritmos não suportados etc.
        raise TunnelError(f"Chave privada em formato não suportado: {e}") from e

    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(text), password=pw)
        except paramiko.PasswordRequiredException as e:
            raise TunnelError("A chave privada está protegida: informe a senha da chave") from e
        except (paramiko.SSHException, ValueError):
            continue
    raise TunnelError("Tipo de chave não suportado (use ed25519, RSA ou ECDSA)")


# ------------------------------------------------------------- chave do host

class _PinnedHostKey(paramiko.MissingHostKeyPolicy):
    """Aceita apenas a chave gravada; sem chave gravada, aceita e registra (TOFU)."""

    def __init__(self, expected):
        self.expected = expected
        self.seen = None

    def missing_host_key(self, client, hostname, key):
        self.seen = {"type": key.get_name(), "key": key.get_base64(), "fingerprint": fingerprint(key)}
        if self.expected and (self.expected.get("key") != key.get_base64()
                              or self.expected.get("type") != key.get_name()):
            raise HostKeyMismatch(
                f"A chave do servidor SSH mudou (agora {self.seen['fingerprint']}, "
                f"registrada {self.expected.get('fingerprint')}). Possível ataque "
                "man-in-the-middle ou servidor reinstalado. Confira e redefina a chave na tela Conexão.")


def _channel_error(exc, host, port):
    """Traduz a recusa do servidor SSH em abrir o canal até o banco."""
    code = getattr(exc, "code", None)
    target = f"{host}:{port}"
    if code == paramiko.common.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED:
        return (f"o servidor SSH não permite encaminhamento para {target} "
                "(verifique AllowTcpForwarding no sshd ou a opção permitopen da chave)")
    if code == paramiko.common.OPEN_FAILED_CONNECT_FAILED:
        return (f"o servidor SSH não conseguiu conectar em {target} — confira se o banco está "
                "rodando e se host/porta estão corretos do ponto de vista do servidor SSH")
    text = getattr(exc, "text", "") or str(exc)
    return f"o servidor SSH recusou abrir o canal para {target}: {text}"


# ----------------------------------------------------------------- conexão

def connect(s):
    """Abre uma sessão SSH autenticada, conferindo a chave do host (TOFU).

    Retorna ``(client, chave_vista)``; usada pelo túnel do banco e pelos
    destinos SFTP das cópias externas."""
    policy = _PinnedHostKey(s.get("host_key"))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(policy)
    host, port = s["host"], int(s.get("port") or 22)
    kwargs = dict(hostname=host, port=port, username=s["user"],
                  timeout=settings.CONNECT_TIMEOUT, banner_timeout=settings.CONNECT_TIMEOUT,
                  auth_timeout=settings.CONNECT_TIMEOUT, allow_agent=False, look_for_keys=False)
    if s.get("auth") == "key":
        kwargs["pkey"] = load_private_key(s.get("private_key"), s.get("key_passphrase"))
    else:
        kwargs["password"] = s.get("password") or ""
    try:
        client.connect(**kwargs)
    except HostKeyMismatch:
        client.close()
        raise
    except paramiko.AuthenticationException as e:
        client.close()
        raise TunnelError("Falha na autenticação SSH (usuário, senha ou chave incorretos)") from e
    except socket.gaierror as e:
        client.close()
        raise TunnelError(f"Não foi possível conectar ao servidor SSH {host}:{port}: "
                          f"nome não encontrado ({host})") from e
    except (paramiko.SSHException, OSError) as e:
        client.close()
        if isinstance(e, (socket.timeout, TimeoutError)):
            reason = "tempo esgotado"
        elif isinstance(e, paramiko.ssh_exception.NoValidConnectionsError):
            reason = "conexão recusada (nada escutando nessa porta)"
        else:
            reason = e
        raise TunnelError(f"Não foi possível conectar ao servidor SSH {host}:{port}: {reason}") from e
    transport = client.get_transport()
    transport.set_keepalive(15)
    _enable_tcp_keepalive(transport.sock)
    return client, policy.seen


# --------------------------------------------------------------------- túnel

class Tunnel:
    def __init__(self, ssh, remote_host, remote_port):
        self.ssh = ssh
        self.remote = (remote_host, int(remote_port))
        self.client = None
        self.transport = None
        self.server = None
        self.local_port = None
        self.host_key = None
        self.last_error = None
        self._stop = threading.Event()
        self._accept_thread = None
        self._pipes = set()
        self._pipes_lock = threading.Lock()

    # ------------------------------------------------------------------ abrir
    def start(self):
        self.client, self.host_key = connect(self.ssh)
        self.transport = self.client.get_transport()

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(8)
        self.server.settimeout(0.5)
        self.local_port = self.server.getsockname()[1]
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True,
                                               name="sentinela-tunnel")
        self._accept_thread.start()
        return self

    # ----------------------------------------------------------- encaminhamento
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                sock, addr = self.server.accept()
            except socket.timeout:
                if not self.transport.is_active():
                    self.last_error = self.last_error or DROPPED
                continue
            except OSError:
                break
            sock.settimeout(None)
            try:
                chan = self.transport.open_channel(
                    "direct-tcpip", self.remote, addr, timeout=settings.CONNECT_TIMEOUT)
            except paramiko.ChannelException as e:
                self.last_error = _channel_error(e, *self.remote)
                _close(sock)
                continue
            except Exception as e:
                self.last_error = f"a conexão SSH foi interrompida ({e or type(e).__name__})"
                _close(sock)
                continue
            pair = (sock, chan)
            with self._pipes_lock:
                self._pipes.add(pair)
            threading.Thread(target=self._pipe, args=(pair,), daemon=True,
                             name="sentinela-tunnel-pipe").start()

    def _pipe(self, pair):
        sock, chan = pair
        remote_closed = False
        try:
            while not self._stop.is_set():
                if not self.transport.is_active():
                    self.last_error = self.last_error or DROPPED
                    break
                r, _, _ = select.select([sock, chan], [], [], 0.5)
                if sock in r:
                    data = sock.recv(65536)
                    if not data:
                        break
                    chan.sendall(data)
                if chan in r:
                    data = chan.recv(65536)
                    if not data:
                        remote_closed = True
                        break
                    sock.sendall(data)
        except Exception:
            # Canal fechado pelo transporte (select em fd inválido, EOF, reset...).
            remote_closed = True
        finally:
            # Registra o motivo ANTES de fechar o socket local (o cliente do banco
            # reage ao fechamento e o erro sobe logo em seguida).
            if remote_closed and not self._stop.is_set():
                # O paramiko fecha os canais ANTES de marcar o transporte como
                # inativo; espera um instante para distinguir "o banco encerrou a
                # conexão" de "a sessão SSH caiu".
                for _ in range(20):
                    if not self.transport.is_active():
                        break
                    time.sleep(0.05)
            if not self._stop.is_set() and not self.transport.is_active():
                self.last_error = self.last_error or DROPPED
            # Fecha primeiro o socket local: é ele que libera o pg_dump/mariadb-dump.
            _close(sock)
            _close(chan)
            with self._pipes_lock:
                self._pipes.discard(pair)

    # ------------------------------------------------------------------ fechar
    def close(self):
        self._stop.set()
        if self.server:
            try:
                self.server.shutdown(socket.SHUT_RDWR)  # acorda o accept() bloqueado
            except OSError:
                pass
            _close(self.server)
        if self._accept_thread:
            self._accept_thread.join(2)
        with self._pipes_lock:
            pairs = list(self._pipes)
        for sock, chan in pairs:
            _close(sock)
            _close(chan)
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass


def _close(obj):
    try:
        obj.close()
    except Exception:
        pass


# Tempo máximo (s) sem resposta do servidor SSH antes de considerar a rede caída.
DEAD_PEER_TIMEOUT = 60


def _enable_tcp_keepalive(sock):
    """Detecta queda silenciosa da rede (cabo, firewall descartando pacotes).

    Sem isso, o TCP pode levar ~15 minutos para desistir e o backup ficaria
    parado. Keepalive cobre a conexão ociosa; TCP_USER_TIMEOUT cobre o caso de
    dados enviados que nunca são confirmados."""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, val in (("TCP_KEEPIDLE", 20), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 4),
                         ("TCP_USER_TIMEOUT", DEAD_PEER_TIMEOUT * 1000)):
            if hasattr(socket, opt):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
    except OSError:
        pass


@contextmanager
def open_tunnel(ssh, remote_host, remote_port):
    t = Tunnel(ssh, remote_host, remote_port).start()
    try:
        yield t
    finally:
        t.close()
