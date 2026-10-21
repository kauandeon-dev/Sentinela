"""Valida a versão portátil já extraída, como um usuário faria no Windows:
dois cliques em Sentinela-Demo.bat, painel no ar, backup/restauração pelo painel.

Uso: python tests/ci/validar_portatil.py "C:\\Pasta Com Espaço\\Sentinela"
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

root = Path(sys.argv[1])
here = Path(__file__).resolve().parent
log = root.parent / "janela-demo.txt"


def check(cond, msg):
    print(("OK    " if cond else "FALHA ") + msg, flush=True)
    if not cond:
        print("---- janela do Sentinela ----")
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(vazia)")
        raise SystemExit(1)


# Ferramentas embutidas rodam sozinhas (sem PostgreSQL/MariaDB instalados no PC)
for exe in ("ferramentas/pgsql/bin/pg_dump.exe", "ferramentas/pgsql/bin/psql.exe",
            "ferramentas/pgsql/bin/postgres.exe", "ferramentas/mariadb/mariadb-dump.exe",
            "ferramentas/mariadb/mariadb.exe"):
    p = root / exe
    if not p.exists() and "mariadb" in exe:
        print(f"AVISO {exe} ausente (pacote sem MariaDB)")
        continue
    r = subprocess.run([str(p), "--version"], capture_output=True, text=True)
    check(r.returncode == 0, f"{exe} --version: {r.stdout.strip() or r.stderr.strip()}")

py = root / "python" / "python.exe"
r = subprocess.run([str(py), "-c", "import sys, sentinela, cryptography, paramiko, boto3, waitress;"
                    "print(sys.version.split()[0], sys.executable)"], capture_output=True, text=True)
check(r.returncode == 0, f"Python embutido com as bibliotecas: {r.stdout.strip() or r.stderr.strip()}")

# "Dois cliques" em Sentinela-Demo.bat (saída da janela vai para um arquivo).
# Simula também um aluno com acento no nome de usuário (C:\Users\João...): a
# pasta do usuário não pode ser usada pelo PostgreSQL.
fake_profile = Path("C:/Usuários/João/AppData/Local")
fake_profile.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, SENTINELA_NO_BROWSER="1", LOCALAPPDATA=str(fake_profile))
out = open(log, "w", encoding="utf-8")
proc = subprocess.Popen(["cmd", "/c", str(root / "Sentinela-Demo.bat")], cwd=str(root), env=env,
                        stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
text = ""
for _ in range(240):
    text = log.read_text(encoding="utf-8", errors="replace")
    if "ouvindo em" in text or proc.poll() is not None:
        break
    time.sleep(1)
check("ouvindo em" in text, "painel iniciado pelo Sentinela-Demo.bat")
pw = re.search(r"senha: (\S+)", text).group(1)
url = re.search(r"Painel: (http://\S+?)/?\s", text).group(1)
check("Banco de demonstração pronto" in text, "banco de demonstração criado e carregado")
check(str(root / "dados") in text, "dados gravados dentro da pasta portátil")
demo = Path(re.search(r"arquivos do banco: (.+)", text).group(1).strip())
check(str(demo).isascii(), f"banco da demonstração numa pasta sem acento: {demo}")
check("copiando o PostgreSQL" in text, "PostgreSQL copiado para pasta sem acento (pasta portátil tem acento)")

r = subprocess.run([sys.executable, str(here / "smoke.py"), url, "admin", pw, "127.0.0.1",
                    str(root.parent / "disco-externo"), "5433", "loja_demo", "backup_user", "demo123"])
check(r.returncode == 0, "backup, cópia externa, verificação e restauração pelo painel")

backups = list((root / "backups").glob("loja_demo_*.sql.gz.enc"))
check(len(backups) >= 2, f"cópias em {root / 'backups'}: {len(backups)}")
key = (root / "dados" / "sentinela.key").read_bytes()
check(len(key) == 32, "chave mestra íntegra (32 bytes, gravada em modo binário)")

# MySQL 8+ local, usuário root SEM senha (login caching_sha2_password): o cliente
# MariaDB embutido precisa do plugin — era o erro "Plugin caching_sha2_password
# could not be loaded".
mysql_port = os.environ.get("MYSQL_TEST_PORT")
if mysql_port:
    maria = root / "ferramentas" / "mariadb" / "mariadb.exe"
    check((root / "ferramentas" / "mariadb" / "plugin" / "caching_sha2_password.dll").exists(),
          "plugin caching_sha2_password.dll incluído no pacote")
    r = subprocess.run([str(sys.executable), str(here / "smoke.py"), url, "admin", pw, "127.0.0.1",
                        str(root.parent / "disco-externo"), mysql_port, "loja_mysql", "root", "",
                        "mariadb"])
    check(r.returncode == 0, "MySQL 8 com root sem senha: conexão, backup, verificação e restauração")
    q = subprocess.run([str(maria), "-h", "127.0.0.1", "-P", mysql_port, "-u", "root",
                        f"--plugin-dir={root / 'ferramentas' / 'mariadb' / 'plugin'}",
                        "--ssl-verify-server-cert=0", "-N", "-B", "loja_mysql", "-e",
                        "SELECT cidade FROM clientes WHERE id=1; SELECT COUNT(*) FROM pedidos; "
                        "SHOW PROCEDURE STATUS WHERE Db='loja_mysql'"],
                       capture_output=True)
    out = q.stdout.decode("utf-8", "replace")
    check(q.returncode == 0 and "São Lourenço do Oeste" in out and "\n5000\n" in out
          and "total_clientes" in out,
          "dados do MySQL intactos após restaurar (acentos, 5000 pedidos, procedure): "
          + (out or q.stderr.decode("utf-8", "replace")).replace("\n", " | "))
    backups_mysql = list((root / "backups").glob("loja_mysql_*.sql.gz.enc"))
    check(len(backups_mysql) >= 2, f"cópias do MySQL: {len(backups_mysql)}")

# Encerrar com Ctrl+Break (como Ctrl+C na janela) deve desligar também o
# PostgreSQL da demonstração
import signal  # noqa: E402
pg_ctl = demo.parent / "pgsql" / "bin" / "pg_ctl.exe"


def pg_running():
    return subprocess.run([str(pg_ctl), "status", "-D", str(demo)], capture_output=True).returncode == 0


check(pg_running(), "PostgreSQL da demonstração rodando")
os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
for _ in range(40):
    if not pg_running():
        break
    time.sleep(0.5)
check(not pg_running(), "ao encerrar o Sentinela, o PostgreSQL da demonstração também é desligado")
subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)

# Segunda abertura: reaproveita o banco e a configuração (sem recriar nada)
out = open(log, "w", encoding="utf-8")
proc = subprocess.Popen(["cmd", "/c", str(root / "Sentinela-Demo.bat")], cwd=str(root), env=env,
                        stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
for _ in range(120):
    text = log.read_text(encoding="utf-8", errors="replace")
    if "ouvindo em" in text or proc.poll() is not None:
        break
    time.sleep(1)
check("ouvindo em" in text and "Criando o banco" not in text and "Primeiro acesso" not in text,
      "segunda abertura reaproveita banco, usuário e configuração")
subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
subprocess.run([str(pg_ctl), "stop", "-D", str(demo), "-m", "fast"], capture_output=True)
print("Versão portátil validada.")
