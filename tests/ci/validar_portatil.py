"""Valida a versão portátil já extraída, como um usuário faria no Windows:
dois cliques em Sentinela-Demo.exe, painel no ar, backup/restauração pelo painel.

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
        seg = root / "dados" / "logs" / "segundo-plano.log"
        if seg.exists():
            print("---- segundo plano ----")
            print(seg.read_text(encoding="utf-8", errors="replace"))
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

# Atalhos .exe (o mesmo lançador com nomes diferentes)
for exe in ("Sentinela", "Sentinela-Demo", "Parar-Sentinela", "Trocar-Senha", "Descriptografar"):
    check((root / f"{exe}.exe").exists(), f"{exe}.exe na pasta")
check(not list(root.glob("*.bat")), "sem os antigos atalhos .bat")
import shutil  # noqa: E402
sozinho = root.parent / "lancador-sozinho"
sozinho.mkdir(exist_ok=True)
shutil.copy(root / "Sentinela.exe", sozinho / "Sentinela.exe")
r = subprocess.run([str(sozinho / "Sentinela.exe")], capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
check(r.returncode == 1 and "Pasta incompleta" in r.stdout.decode("utf-8", "replace"),
      "Sentinela.exe fora da pasta (ZIP não extraído) explica o que fazer")

py = root / "python" / "python.exe"
r = subprocess.run([str(py), "-c", "import sys, sentinela, cryptography, paramiko, boto3, waitress;"
                    "print(sys.version.split()[0], sys.executable)"], capture_output=True, text=True)
check(r.returncode == 0, f"Python embutido com as bibliotecas: {r.stdout.strip() or r.stderr.strip()}")

# "Dois cliques" em Sentinela-Demo.exe (saída da janela vai para um arquivo).
# Simula também um aluno com acento no nome de usuário (C:\Users\João...): a
# pasta do usuário não pode ser usada pelo PostgreSQL.
fake_profile = Path("C:/Usuários/João/AppData/Local")
fake_profile.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, SENTINELA_NO_BROWSER="1", LOCALAPPDATA=str(fake_profile))
out = open(log, "w", encoding="utf-8")
proc = subprocess.Popen([str(root / "Sentinela-Demo.exe")], cwd=str(root), env=env,
                        stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
text = ""
for _ in range(240):
    text = log.read_text(encoding="utf-8", errors="replace")
    if "ouvindo em" in text or proc.poll() is not None:
        break
    time.sleep(1)
check("ouvindo em" in text, "painel iniciado pelo Sentinela-Demo.exe")
pw = re.search(r"senha: (\S+)", text).group(1)
url = re.search(r"Painel: (http://\S+?)/?\s", text).group(1)
check("Banco de demonstração pronto" in text, "banco de demonstração criado e carregado")
check(str(root / "dados") in text, "dados gravados dentro da pasta portátil")
demo = Path(re.search(r"arquivos do banco: (.+)", text).group(1).strip())
check(str(demo).isascii(), f"banco da demonstração numa pasta sem acento: {demo}")
if not str(root).isascii():
    check("copiando o PostgreSQL" in text, "PostgreSQL copiado para pasta sem acento (pasta portátil tem acento)")

r = subprocess.run([sys.executable, str(here / "smoke.py"), url, "admin", pw, "127.0.0.1",
                    str(root.parent / "disco-externo"), "5433", "loja_demo", "backup_user", "demo123"])
check(r.returncode == 0, "backup, cópia externa, verificação e restauração pelo painel")

backups = list((root / "backups").glob("loja_demo_*.sql.gz.enc"))
check(len(backups) >= 2, f"cópias em {root / 'backups'}: {len(backups)}")
key = (root / "dados" / "sentinela.key").read_bytes()
check(len(key) == 32, "chave mestra íntegra (32 bytes, gravada em modo binário)")

# Descriptografar.exe: arrastar uma cópia para cima do atalho (o Explorer passa
# o caminho como argumento) e sem arquivos (a mais recente)
enc = sorted(backups)[0]
sql = enc.with_name(enc.name.replace(".sql.gz.enc", ".sql"))
r = subprocess.run([str(root / "Descriptografar.exe"), str(enc)], cwd=str(enc.parent),
                   capture_output=True, stdin=subprocess.DEVNULL)
saida = r.stdout.decode("utf-8", "replace")
check(sql.exists() and "OK" in saida, f"Descriptografar.exe com arquivo arrastado gera {sql.name}: "
      + saida.strip().replace("\r\n", " | "))
texto = sql.read_text(encoding="utf-8")
check("PostgreSQL database dump complete" in texto and "São Lourenço do Oeste" in texto,
      "SQL descriptografado completo e com acentos")
sql.unlink()
r = subprocess.run([str(root / "Descriptografar.exe")], capture_output=True,
                   stdin=subprocess.DEVNULL)
novos = list((root / "backups").glob("*.sql"))
check(len(novos) == 1 and "mais recente" in r.stdout.decode("utf-8", "replace"),
      f"Descriptografar.exe sem arquivos recupera a cópia mais recente: {[n.name for n in novos]}")
for n in novos:
    n.unlink()

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
# O PostgreSQL só é copiado para a pasta da demonstração quando a pasta do
# Sentinela tem acento; senão roda direto de ferramentas\pgsql
pg_ctl = next(p for p in (demo.parent / "pgsql" / "bin" / "pg_ctl.exe",
                          root / "ferramentas" / "pgsql" / "bin" / "pg_ctl.exe") if p.exists())


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
proc = subprocess.Popen([str(root / "Sentinela-Demo.exe")], cwd=str(root), env=env,
                        stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
for _ in range(120):
    text = log.read_text(encoding="utf-8", errors="replace")
    if "ouvindo em" in text or proc.poll() is not None:
        break
    time.sleep(1)
check("ouvindo em" in text and "Criando o banco" not in text and "Primeiro acesso" not in text,
      "segunda abertura reaproveita banco, usuário e configuração")
url = re.search(r"Painel: (http://\S+?)/?\s", text).group(1)

# ------------------------------------------------------------ segundo plano
# "Iniciar com o computador" pelo painel: registra na chave Executar do
# usuário (sem administrador), a janela passa a vez para um pythonw sem janela
# no mesmo endereço; depois, desligar e ligar o PC depois da meia-noite.
import http.cookiejar  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import urllib.request  # noqa: E402
import winreg  # noqa: E402

jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(method, path, data=None):
    req = urllib.request.Request(url + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(data).encode() if data is not None else None)
    try:
        with jar.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def up():
    try:
        return call("GET", "/api/me")[0] == 200
    except OSError:
        return False


def wait(cond, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(1)
    return None


def run_key():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            return winreg.QueryValueEx(k, "Sentinela")[0]
    except OSError:
        return None


def pythonw_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pythonw.exe"], capture_output=True, text=True).stdout
    return "pythonw.exe" in out


check(call("POST", "/api/login", {"username": "admin", "password": pw})[0] == 200, "login no painel")
# O teste do MySQL deixou a conexão nele: volta para o banco da demonstração,
# que o segundo plano precisa subir sozinho
demo_conn = {"sgbd": "postgres", "host": "127.0.0.1", "port": "5433", "dbname": "loja_demo",
             "user": "backup_user", "password": "demo123"}
check(call("PUT", "/api/connection", demo_conn)[0] == 200, "conexão de volta ao banco da demonstração")
st = call("GET", "/api/servico")[1]["servico"]
check(st["supported"] and not st["enabled"] and not st["background"], f"segundo plano ainda desativado: {st}")
code, r = call("POST", "/api/servico", {"enabled": True})
check(code == 200 and r.get("handoff"), f"ativar 'Iniciar com o computador' pelo painel: {r}")
cmdline = run_key()
expected = f'"{root}\\python\\pythonw.exe" "{root}\\app\\portatil.py" --servico'
check(cmdline == expected, f"registrado em HKCU\\...\\Run: {cmdline}")
check(wait(lambda: proc.poll() is not None, 90) is not None, "a janela do Sentinela fecha sozinha")
janela = log.read_text(encoding="utf-8", errors="replace")
check("passou a rodar em segundo plano" in janela, "a janela avisa que passou para o segundo plano")
st = wait(lambda: up() and call("GET", "/api/servico")[1]["servico"])
check(bool(st) and st["background"] and st["url"].rstrip("/") == url,
      f"painel no mesmo endereço, agora em segundo plano: {st}")
check(pythonw_running(), "processo sem janela (pythonw.exe)")
check(wait(pg_running, 60), "banco de demonstração ligado pelo segundo plano")

r = subprocess.run([str(root / "Sentinela.exe")], capture_output=True, env=env,
                   stdin=subprocess.DEVNULL, timeout=120)
saida = r.stdout.decode("utf-8", "replace")
check("já está rodando em segundo plano" in saida and url in saida,
      "Sentinela.exe com o segundo plano rodando só abre o painel: " + saida.strip().replace("\r\n", " | "))

# "Desligar o computador"
r = subprocess.run([str(root / "Parar-Sentinela.exe")], capture_output=True, env=env,
                   stdin=subprocess.DEVNULL, timeout=600)
saida = r.stdout.decode("utf-8", "replace")
check("Sentinela encerrado" in saida and not up(), "Parar-Sentinela.exe encerra o segundo plano: "
      + saida.strip().replace("\r\n", " | "))
check(wait(lambda: not pg_running(), 30), "banco de demonstração desligado junto")

# "Ligar depois da meia-noite": o backup agendado ficou para trás
db = sqlite3.connect(root / "dados" / "sentinela.db")
db.execute("UPDATE settings SET value=? WHERE key='next_run_at'", (json.dumps("2020-01-01 00:00:00"),))
db.commit()
db.close()
antes = len(list((root / "backups").glob("loja_demo_*.sql.gz.enc")))
# O Windows executa o valor da chave Executar ao entrar; mesmo comando aqui
boot_env = dict(env, SENTINELA_STARTUP_GRACE="5", SENTINELA_TICK="2")
subprocess.Popen(cmdline, env=boot_env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL)
check(wait(up, 120), "ao 'entrar no Windows', o painel sobe sozinho")
check(call("POST", "/api/login", {"username": "admin", "password": pw})[0] == 200, "login")


def auto_ok():
    bs = call("GET", "/api/backups")[1]["backups"]
    done = [b for b in bs if b["trigger"] == "auto" and b["status"] != "running"]
    return done[0] if done else None


b = wait(auto_ok, 240)
check(bool(b) and b["status"] == "success", f"backup automático atrasado feito sozinho: {b and b['id']}")
check(len(list((root / "backups").glob("loja_demo_*.sql.gz.enc"))) == antes + 1, "nova cópia na pasta backups")
main_log = (root / "dados" / "logs" / "sentinela.log").read_text(encoding="utf-8", errors="replace")
check("Backup automático atrasado" in main_log, "log registra que era o backup da meia-noite perdida")
check((root / "dados" / "logs" / "segundo-plano.log").exists(), "saída do segundo plano em dados\\logs")
check(pythonw_running(), "rodando sem janela (pythonw.exe)")

# Desativar e encerrar pelo painel
code, r = call("POST", "/api/servico", {"enabled": False})
check(code == 200 and not r["servico"]["enabled"] and run_key() is None, "desativar remove da chave Executar")
check(call("POST", "/api/servico/encerrar")[0] == 200, "botão Encerrar")
check(wait(lambda: not up(), 60), "painel encerrado")
check(wait(lambda: not pg_running(), 60), "banco de demonstração desligado ao encerrar")
subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
subprocess.run([str(pg_ctl), "stop", "-D", str(demo), "-m", "fast"], capture_output=True)
print("Versão portátil validada.")
