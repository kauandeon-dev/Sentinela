"""Inicializador da versão portátil do Sentinela.

Roda a partir de uma pasta qualquer (Área de Trabalho, pendrive), sem instalar
nada e sem permissão de administrador. É chamado pelos atalhos .bat:

    Sentinela.bat        python portatil.py            painel do Sentinela
    Sentinela-Demo.bat   python portatil.py --demo     painel + banco de demonstração
    Trocar-Senha.bat     python portatil.py --senha    troca a senha do admin

Estrutura da pasta portátil:

    Sentinela/
      app/            o Sentinela (este arquivo, o pacote sentinela/, demo.sql)
      python/         Python embutido + bibliotecas
      ferramentas/    pgsql/ (pg_dump, psql e o servidor da demonstração) e mariadb/
      dados/          configurações, chave mestra e logs (criada na 1ª execução)
      backups/        cópias locais (criada na 1ª execução)
"""

import argparse
import atexit
import glob
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
TOOLS = ROOT / "ferramentas"
EXE = ".exe" if os.name == "nt" else ""

# Banco de demonstração (PostgreSQL portátil, só aceita conexões deste computador)
DEMO_PORT = int(os.environ.get("SENTINELA_DEMO_PORT", "5433"))
DEMO_CONN = {"sgbd": "postgres", "host": "127.0.0.1", "port": str(DEMO_PORT),
             "dbname": "loja_demo", "user": "backup_user", "password": "demo123"}
DEMO_SUPERUSER_PW = "sentinela-demo"


def say(msg=""):
    print(msg, flush=True)


# ------------------------------------------------------------------ ambiente

def setup_env():
    """Aponta o Sentinela para as pastas e ferramentas da versão portátil."""
    os.environ.setdefault("SENTINELA_HOME", str(ROOT / "dados"))
    os.environ.setdefault("SENTINELA_BACKUP_DIR", str(ROOT / "backups"))
    os.environ.setdefault("PYTHONUTF8", "1")
    tools = (("SENTINELA_PG_DUMP", TOOLS / "pgsql" / "bin" / f"pg_dump{EXE}"),
             ("SENTINELA_PSQL", TOOLS / "pgsql" / "bin" / f"psql{EXE}"),
             ("SENTINELA_MYSQLDUMP", TOOLS / "mariadb" / f"mariadb-dump{EXE}"),
             ("SENTINELA_MYSQL", TOOLS / "mariadb" / f"mariadb{EXE}"))
    for var, path in tools:
        if path.exists():
            os.environ.setdefault(var, str(path))
    # Plugins de login do cliente MariaDB (caching_sha2_password do MySQL 8+)
    plugins = TOOLS / "mariadb" / "plugin"
    if plugins.is_dir():
        os.environ.setdefault("MARIADB_PLUGIN_DIR", str(plugins))
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))


def free_port(start=8080, tries=20):
    """Primeira porta livre a partir de 8080 (outro programa pode estar nela)."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"Nenhuma porta livre entre {start} e {start + tries - 1}.")


def open_browser_when_ready(url):
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "api/me", timeout=2).close()
            break
        except OSError:
            time.sleep(0.5)
    if not os.environ.get("SENTINELA_NO_BROWSER"):
        webbrowser.open(url)


# ------------------------------------------------------- banco de demonstração

def pg_bin():
    """Binários do servidor PostgreSQL: os da pasta portátil ou, fora do Windows,
    os instalados no sistema (útil para testar)."""
    candidates = [TOOLS / "pgsql" / "bin"]
    if os.environ.get("SENTINELA_PG_BIN"):
        candidates.insert(0, Path(os.environ["SENTINELA_PG_BIN"]))
    candidates += [Path(p) for p in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)]
    for c in candidates:
        if (c / f"initdb{EXE}").exists() and (c / f"pg_ctl{EXE}").exists():
            return c
    raise SystemExit("O servidor PostgreSQL da demonstração não foi encontrado em "
                     f"{TOOLS / 'pgsql' / 'bin'}. Baixe de novo a versão portátil completa.")


def _writable(path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".teste-escrita"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def demo_dir():
    """Pasta do banco de demonstração.

    No Windows, o PostgreSQL não funciona em caminhos com acento (ex.:
    C:\\Users\\João): a criação do banco falha com "invalid byte sequence for
    encoding UTF8". Por isso usamos a primeira pasta SEM acento e gravável entre
    %LOCALAPPDATA%, %ProgramData% e %PUBLIC% — sempre num disco local NTFS (o
    PostgreSQL também não funciona bem em pendrive FAT32/exFAT)."""
    if os.environ.get("SENTINELA_DEMO_DIR"):
        return Path(os.environ["SENTINELA_DEMO_DIR"])
    if os.name != "nt":
        return ROOT / "demo"
    for var in ("LOCALAPPDATA", "PROGRAMDATA", "PUBLIC"):
        base = os.environ.get(var)
        if base and base.isascii() and _writable(Path(base) / "SentinelaDemo"):
            return Path(base) / "SentinelaDemo"
    fallback = Path(os.environ.get("SystemDrive", "C:") + "\\") / "SentinelaDemo"
    if _writable(fallback):
        return fallback
    raise SystemExit("Não encontrei uma pasta sem acento e com permissão de escrita para o banco "
                     "de demonstração. Defina SENTINELA_DEMO_DIR (ex.: D:\\SentinelaDemo).")


def ascii_pg_bin(binp, base):
    """Se a pasta portátil tem acento, copia o PostgreSQL (uma vez) para a pasta
    da demonstração, que é sem acento — senão o servidor não inicia no Windows."""
    if os.name != "nt" or str(binp).isascii():
        return binp
    src = binp.parent
    dest = base / "pgsql"
    stamp = dest / "versao.txt"
    version = subprocess.run([str(binp / f"pg_ctl{EXE}"), "--version"], capture_output=True,
                             text=True).stdout.strip()
    if not stamp.exists() or stamp.read_text(encoding="utf-8", errors="replace") != version:
        say("A pasta tem acento no nome: copiando o PostgreSQL da demonstração para "
            f"{dest} (só na primeira vez)...")
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        for part in ("bin", "lib", "share"):
            shutil.copytree(src / part, dest / part)
        stamp.write_text(version, encoding="utf-8")
    return dest / "bin"


def _psql(binp, sql=None, file=None, db="postgres"):
    cmd = [str(binp / f"psql{EXE}"), "-h", "127.0.0.1", "-p", str(DEMO_PORT), "-U", "postgres",
           "-d", db, "-X", "-q", "-tA", "-v", "ON_ERROR_STOP=1"]
    cmd += ["-f", str(file)] if file else ["-c", sql]
    env = dict(os.environ, PGPASSWORD=DEMO_SUPERUSER_PW, PGCLIENTENCODING="UTF8")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"Erro no banco de demonstração: {r.stderr.strip()}")
    return r.stdout.strip()


def start_demo():
    base = demo_dir()
    base.mkdir(parents=True, exist_ok=True)
    binp = ascii_pg_bin(pg_bin(), base)
    data = base / "banco"
    log = base / "banco.log"

    if not (data / "PG_VERSION").exists():
        say("Criando o banco de demonstração (só na primeira vez, leva alguns segundos)...")
        pwfile = base / "senha.tmp"
        pwfile.write_text(DEMO_SUPERUSER_PW, encoding="ascii")
        try:
            r = subprocess.run([str(binp / f"initdb{EXE}"), "-D", str(data), "-U", "postgres",
                                "-A", "scram-sha-256", f"--pwfile={pwfile}", "-E", "UTF8",
                                "--locale=C"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        finally:
            pwfile.unlink(missing_ok=True)
        if r.returncode:
            raise SystemExit("Não foi possível criar o banco de demonstração:\n"
                             + (r.stderr or r.stdout).strip())

    pg_ctl = str(binp / f"pg_ctl{EXE}")
    running = subprocess.run([pg_ctl, "status", "-D", str(data)], capture_output=True).returncode == 0
    if not running:
        opts = f"-p {DEMO_PORT} -c listen_addresses=127.0.0.1"
        if os.name != "nt":
            opts += f" -c unix_socket_directories='{base}'"
        say(f"Iniciando o PostgreSQL de demonstração (porta {DEMO_PORT})...")
        # Sem capture_output: no Windows o postgres herdaria o pipe de saída e o
        # pg_ctl nunca "terminaria" para o Python. A saída do servidor vai para o log.
        r = subprocess.run([pg_ctl, "start", "-D", str(data), "-l", str(log), "-w", "-t", "90",
                            "-o", opts], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        if r.returncode:
            tail = ""
            try:
                tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
            except OSError:
                pass
            raise SystemExit("O PostgreSQL de demonstração não iniciou "
                             f"(a porta {DEMO_PORT} pode estar em uso):\n{tail}")
    # O banco de demonstração pertence à versão portátil: ao sair, é desligado
    # (inclusive se tinha ficado ligado de uma execução anterior).
    _stop_on_exit(pg_ctl, data)

    if _psql(binp, "SELECT 1 FROM pg_database WHERE datname='loja_demo'") != "1":
        say("Carregando os dados de exemplo (clientes, produtos e pedidos)...")
        _psql(binp, file=APP / "demo.sql")
    return binp


def stop_demo(pg_ctl, data):
    subprocess.run([pg_ctl, "stop", "-D", str(data), "-m", "fast", "-w", "-t", "20"],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_console_handler = None  # referência mantida viva para o Windows chamar


def _stop_on_exit(pg_ctl, data):
    done = threading.Event()

    def stop(*_):
        if not done.is_set():
            done.set()
            stop_demo(pg_ctl, data)
    atexit.register(stop)
    if os.name == "nt":
        # Fechar a janela (X), sair da sessão ou desligar o PC não gera Ctrl+C:
        # o Windows avisa o processo e dá alguns segundos antes de encerrá-lo.
        try:
            import ctypes
            from ctypes import wintypes
            global _console_handler
            HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

            def on_console_event(event):
                if event in (2, 5, 6):  # CTRL_CLOSE, CTRL_LOGOFF, CTRL_SHUTDOWN
                    stop()
                return False  # deixa o Windows seguir com o encerramento
            _console_handler = HANDLER(on_console_event)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)
        except Exception:
            pass


def configure_demo_connection():
    """Na primeira vez, já deixa o Sentinela apontado para o banco de demonstração."""
    from sentinela import engine, storage
    storage.init()
    if not engine.connection_ready():
        engine.save_connection(dict(DEMO_CONN))
        say("Conexão do Sentinela configurada para o banco de demonstração.")


# ----------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="Sentinela portátil")
    p.add_argument("--demo", action="store_true", help="sobe também um banco de demonstração")
    p.add_argument("--senha", action="store_true", help="troca a senha do usuário admin")
    args = p.parse_args()

    # Ctrl+C sempre encerra de forma limpa (mesmo se o processo foi iniciado com
    # o sinal ignorado) e SIGTERM também desliga o banco de demonstração.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if hasattr(signal, "SIGBREAK"):  # Ctrl+Break no Windows
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    setup_env()
    from sentinela import __main__ as cli
    from sentinela import compat
    compat.utf8_console()

    if args.senha:
        sys.argv = ["sentinela", "passwd", "admin"]
        cli.main()
        return

    say("=" * 64)
    say(" SENTINELA — versão portátil")
    say(f" Pasta: {ROOT}")
    say("=" * 64)
    if args.demo:
        start_demo()
        c = DEMO_CONN
        say("")
        say(" Banco de demonstração pronto:")
        say(f"   PostgreSQL · host {c['host']} · porta {c['port']} · banco {c['dbname']}")
        say(f"   usuário {c['user']} · senha {c['password']}")
        say(f"   arquivos do banco: {demo_dir() / 'banco'}")
        configure_demo_connection()

    port = int(os.environ.get("SENTINELA_PORT") or free_port())
    url = f"http://127.0.0.1:{port}/"
    say("")
    say(f" Painel: {url}  (abre sozinho no navegador)")
    say(" Deixe esta janela aberta enquanto usa o Sentinela.")
    say(" Para encerrar: feche esta janela ou pressione Ctrl+C.")
    say("")
    threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    sys.argv = ["sentinela", "serve", "--port", str(port)]
    try:
        cli.main()
    except KeyboardInterrupt:
        say("Encerrando...")


if __name__ == "__main__":
    main()
