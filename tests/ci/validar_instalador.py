"""Valida o Sentinela-Instalador.exe como um usuário faria, num Windows sem
PostgreSQL nem Python: instala (sem administrador), usa (o mesmo roteiro da
versão portátil), ativa o início automático, atualiza por cima com o Sentinela
rodando em segundo plano e desinstala.

Uso: python tests/ci/validar_instalador.py C:\\caminho\\Sentinela-Instalador.exe
"""
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.request
import winreg
from pathlib import Path

installer = Path(sys.argv[1])
here = Path(__file__).resolve().parent
root = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Sentinela"   # pasta padrão, sem administrador
programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Sentinela"
desktop = Path(os.environ["USERPROFILE"]) / "Desktop" / "Sentinela.lnk"
url = "http://127.0.0.1:8080"
PW = "senha-do-instalador-1"


def check(cond, msg):
    print(("OK    " if cond else "FALHA ") + msg, flush=True)
    if not cond:
        for f in (root / "dados" / "logs" / "segundo-plano.log", Path("C:/instalador.log"),
                  Path("C:/janela.txt")):
            if f.exists():
                print(f"---- {f} ----")
                print(f.read_text(encoding="utf-8", errors="replace")[-6000:])
        raise SystemExit(1)


def install(log):
    r = subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        f"/LOG={log}"], timeout=900)
    return r.returncode


def run_key():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            return winreg.QueryValueEx(k, "Sentinela")[0]
    except OSError:
        return None


def procs(name):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return out.count(f'"{name}"')


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


def wait(cond, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(1)
    return None


def servico():
    if not up():
        return None
    call("POST", "/api/login", {"username": "admin", "password": PW})
    return call("GET", "/api/servico")[1].get("servico")


# ---------------------------------------------------------------- instalar
check(install("C:/instalador.log") == 0, f"instalação silenciosa sem administrador em {root}")
for f in ("Sentinela.exe", "Sentinela-Demo.exe", "Parar-Sentinela.exe", "Trocar-Senha.exe",
          "Descriptografar.exe", "python/python.exe", "python/pythonw.exe", "app/portatil.py",
          "ferramentas/pgsql/bin/pg_dump.exe", "LEIA-ME.txt", "unins000.exe"):
    check((root / f).exists(), f"instalado: {f}")
for lnk in ("Sentinela", "Sentinela (demonstração)", "Parar o Sentinela", "Trocar a senha do admin",
            "Descriptografar cópias", "Desinstalar o Sentinela"):
    check((programs / f"{lnk}.lnk").exists(), f"Menu Iniciar: {lnk}")
check(desktop.exists(), "atalho na Área de Trabalho")
with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{4F2A8C61-9B3E-4D7A-A5C2-8E61D0B7F3A9}_is1") as k:
    check(winreg.QueryValueEx(k, "DisplayName")[0] == "Sentinela", "aparece em Aplicativos instalados")

# ----------------------------------------------------- usar (roteiro portátil)
r = subprocess.run([sys.executable, str(here / "validar_portatil.py"), str(root)], timeout=1500)
check(r.returncode == 0, "versão instalada passa no mesmo roteiro da portátil")

# Senha conhecida para o restante (a do primeiro acesso ficou no roteiro acima)
py = root / "python" / "python.exe"
subprocess.run([str(py), "-c", "import os; os.environ['SENTINELA_HOME'] = r'%s'; "
                "from sentinela import storage; from werkzeug.security import generate_password_hash; "
                "storage.init(); storage.upsert_user('admin', generate_password_hash('%s'))"
                % (root / "dados", PW)], check=True)

# ------------------------------- início automático e atualização por cima
env = dict(os.environ, SENTINELA_NO_BROWSER="1")
janela = open("C:/janela.txt", "w", encoding="utf-8")
proc = subprocess.Popen([str(root / "Sentinela-Demo.exe")], cwd=str(root), env=env, stdout=janela,
                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
check(wait(up), "Sentinela-Demo.exe abre o painel")
check(call("POST", "/api/login", {"username": "admin", "password": PW})[0] == 200, "login")
code, r = call("POST", "/api/servico", {"enabled": True})
check(code == 200 and r.get("handoff"), f"ativar 'Iniciar com o computador': {r}")
check(wait(lambda: proc.poll() is not None, 90) is not None, "a janela fecha sozinha")
st = wait(lambda: (lambda v: v and v["background"] and v)(servico()))
check(bool(st), f"rodando em segundo plano: {st}")
reg = run_key()
check(reg == f'"{root}\\python\\pythonw.exe" "{root}\\app\\portatil.py" --servico',
      f"chave Executar aponta para a pasta instalada: {reg}")

antes = st["since"]
check(install("C:/instalador-atualizacao.log") == 0, "atualização por cima com o Sentinela rodando")
st = wait(lambda: (lambda v: v and v["background"] and v["since"] != antes and v)(servico()), 180)
check(bool(st), f"depois de atualizar, volta sozinho em segundo plano (processo novo): {st}")
check(procs("pythonw.exe") >= 1, "processo sem janela (pythonw.exe)")

# Encerrado pelo usuário, com o início automático ativo: abrir o atalho sobe o
# segundo plano direto (sem prender o Sentinela a uma janela)
r = subprocess.run([str(root / "Parar-Sentinela.exe")], capture_output=True, stdin=subprocess.DEVNULL,
                   timeout=600)
check(not up() and "Sentinela encerrado" in r.stdout.decode("utf-8", "replace"), "Parar-Sentinela.exe")
r = subprocess.run([str(root / "Sentinela.exe")], capture_output=True, env=env, stdin=subprocess.DEVNULL,
                   timeout=300)
saida = r.stdout.decode("utf-8", "replace")
check(r.returncode == 0 and "Iniciando o Sentinela em segundo plano" in saida,
      "Sentinela.exe com o início automático ativo sobe o segundo plano: " + saida.strip().replace("\r\n", " | "))
st = wait(lambda: (lambda v: v and v["background"] and v)(servico()))
check(bool(st), "painel no ar em segundo plano")

# --------------------------------------------------------------- desinstalar
backups = list((root / "backups").glob("*.sql.gz.enc"))
subprocess.run([str(root / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=600)
check(wait(lambda: not (root / "unins000.exe").exists(), 300), "desinstalação concluída")
check(not up(), "Sentinela encerrado pelo desinstalador")
check(run_key() is None, "início automático removido")
check(wait(lambda: procs("pythonw.exe") == 0 and procs("postgres.exe") == 0, 60),
      "nenhum processo do Sentinela ou do banco de demonstração ficou rodando")
for d in ("app", "python", "ferramentas", "Sentinela.exe"):
    check(not (root / d).exists(), f"removido: {d}")
check((root / "dados" / "sentinela.key").exists(), "chave mestra e configurações mantidas (dados\\)")
check(len(list((root / "backups").glob("*.sql.gz.enc"))) == len(backups) > 0,
      f"cópias de backup mantidas: {len(backups)}")
check(not programs.exists() and not desktop.exists(), "atalhos removidos")
demo = Path(os.environ["LOCALAPPDATA"]) / "SentinelaDemo"
check(not (demo / "banco").exists(), "banco de demonstração removido")
print("Instalador validado.")
