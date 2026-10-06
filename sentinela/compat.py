"""Diferenças entre Linux/macOS e Windows, num lugar só.

- Arquivos binários: no Windows, ``os.open`` abre em modo TEXTO por padrão e
  troca todo byte 0x0A por 0x0D 0x0A ao gravar — corromperia a chave mestra e
  as cópias criptografadas. ``open_private`` sempre usa ``O_BINARY``.
- Trava entre processos: ``fcntl.flock`` não existe no Windows; lá usamos
  ``msvcrt.locking``.
- Permissões: ``chmod 0700/0600`` não protege nada no Windows; lá a pasta tem a
  herança de permissões removida e fica acessível só ao usuário atual, ao
  SYSTEM e aos Administradores (``icacls``).
"""

import os
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
O_BINARY = getattr(os, "O_BINARY", 0)


def open_private(path, exclusive=False):
    """Abre ``path`` para escrita binária, só para o dono (0600). Retorna o fd."""
    flags = os.O_WRONLY | os.O_CREAT | O_BINARY | (os.O_EXCL if exclusive else os.O_TRUNC)
    return os.open(path, flags, 0o600)


def private_dir(path):
    """Restringe uma pasta ao usuário do serviço (0700 / ACL equivalente no Windows)."""
    path = str(path)
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        return
    user = os.environ.get("USERNAME")
    if not user:
        return
    domain = os.environ.get("USERDOMAIN")
    who = f"{domain}\\{user}" if domain else user
    # *S-1-5-18 = SYSTEM, *S-1-5-32-544 = Administradores (SIDs não dependem do idioma)
    try:
        subprocess.run(["icacls", path, "/inheritance:r",
                        "/grant:r", f"{who}:(OI)(CI)F",
                        "/grant:r", "*S-1-5-18:(OI)(CI)F",
                        "/grant:r", "*S-1-5-32-544:(OI)(CI)F"],
                       capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


# ------------------------------------------------------- trava entre processos

if IS_WINDOWS:
    import msvcrt

    def lock_nb(fd):
        """Trava exclusiva sem esperar; OSError se outro processo já tem a trava."""
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def unlock(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def lock_nb(fd):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


def utf8_console():
    """O console do Windows usa cp1252/cp850: acentos e símbolos dos logs (· ✓ →)
    gerariam erro de codificação. Força UTF-8, trocando o que não couber."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
