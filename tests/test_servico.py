"""Execução em segundo plano: instância única, início automático, troca da
janela para o segundo plano e o "reinício do computador" (o comando registrado
roda sozinho e faz o backup que ficou para trás)."""
import http.cookiejar
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import PG, needs_pg

ROOT = Path(__file__).resolve().parent.parent
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="systemd do usuário (Linux)")

FAKE_SYSTEMCTL = """#!/bin/sh
# systemctl --user falso: registra as chamadas e cria/remove o link do "enable"
echo "$@" >> "$XDG_CONFIG_HOME/systemctl.log"
wants="$XDG_CONFIG_HOME/systemd/user/default.target.wants"
case "$2" in
  enable)  mkdir -p "$wants" && ln -sf ../sentinela.service "$wants/sentinela.service" ;;
  disable) rm -f "$wants/sentinela.service" ;;
esac
exit 0
"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fake_systemd(tmp_path, monkeypatch):
    """systemctl/loginctl falsos no PATH e config do usuário isolada."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("systemctl", FAKE_SYSTEMCTL), ("loginctl", "#!/bin/sh\nexit 0\n")):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.delenv("SENTINELA_GERENCIADO", raising=False)
    monkeypatch.delenv("SENTINELA_PORTATIL", raising=False)
    return cfg


def _servico(env):
    import importlib
    import sentinela.servico as servico
    importlib.reload(servico)
    return servico


# ------------------------------------------------------------ unidades

def test_single_instance_and_stop_request(env):
    servico = _servico(env)
    assert servico.running_instance() is None
    assert servico.acquire_instance()
    assert servico.acquire_instance()  # idempotente no mesmo processo
    # Outro processo vê a instância e não consegue assumir a pasta
    code = ("import sys; from sentinela import servico; "
            "print(servico.running_instance() is not None, servico.acquire_instance())")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env=os.environ).stdout.split()
    assert out == ["True", "False"]
    stopped = []
    env["storage"].init()
    servico.started("http://127.0.0.1:9/", 9, lambda: stopped.append(1))
    assert json.loads((env["home"] / "painel.json").read_text())["url"] == "http://127.0.0.1:9/"
    assert servico.request_stop()
    for _ in range(50):
        if stopped:
            break
        time.sleep(0.1)
    assert stopped == [1]
    servico.release_instance()
    assert servico.running_instance() is None and not (env["home"] / "painel.json").exists()
    assert not servico.request_stop()


def test_pick_port_skips_busy_port(env):
    servico = _servico(env)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert servico.pick_port("127.0.0.1", busy) != busy
    assert servico.pick_port("127.0.0.1", busy) == busy


def test_managed_installs_are_left_alone(env, monkeypatch):
    servico = _servico(env)
    monkeypatch.setenv("SENTINELA_GERENCIADO", "Docker (reinicia sozinho)")
    st = servico.status()
    assert st["managed"] == "Docker (reinicia sozinho)" and not st["enabled"]
    with pytest.raises(RuntimeError, match="Docker"):
        servico.install()
    assert servico.repair() is False


@linux_only
def test_linux_autostart_unit_launcher_and_repair(env, fake_systemd, monkeypatch):
    servico = _servico(env)
    monkeypatch.setenv("SENTINELA_BACKUP_DIR", str(env["backups"]))
    st = servico.install()
    assert st["enabled"] and not st["other"]
    unit = (fake_systemd / "systemd" / "user" / "sentinela.service").read_text()
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit
    launcher = env["home"] / "sentinela-segundo-plano.pyw"
    assert f"ExecStart={shlex.quote(sys.executable)} {shlex.quote(str(launcher))}" in unit
    src = launcher.read_text()
    assert str(env["home"]) in src and str(env["backups"]) in src and "'--background'" in src
    calls = (fake_systemd / "systemctl.log").read_text()
    assert "--user daemon-reload" in calls and "--user enable sentinela.service" in calls

    # Versão portátil movida de lugar: o comando registrado aponta para um
    # arquivo que não existe mais e é atualizado na próxima abertura.
    old = env["home"].parent / "pasta-antiga" / "portatil.py"
    monkeypatch.setenv("SENTINELA_PORTATIL", str(old))
    servico.install()
    assert servico.status()["enabled"]
    new = env["home"].parent / "pasta-nova" / "portatil.py"
    new.parent.mkdir()
    new.write_text("")
    monkeypatch.setenv("SENTINELA_PORTATIL", str(new))
    st = servico.status()
    assert not st["enabled"] and str(old) in st["other"]
    assert servico.repair() is True
    assert servico.status()["enabled"]
    assert servico.repair() is False  # já está certo

    # Outra instalação que existe de verdade não é sobrescrita sozinha
    monkeypatch.setenv("SENTINELA_PORTATIL", str(old))
    assert servico.repair() is False

    monkeypatch.setenv("SENTINELA_PORTATIL", str(new))
    assert not servico.uninstall()["enabled"]
    assert not (fake_systemd / "systemd" / "user" / "sentinela.service").exists()


@linux_only
def test_linux_without_user_systemd_explains(env, tmp_path, monkeypatch):
    servico = _servico(env)
    bad = tmp_path / "bin"
    bad.mkdir()
    (bad / "systemctl").write_text("#!/bin/sh\necho 'Failed to connect to bus' >&2\nexit 1\n")
    (bad / "systemctl").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bad}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    with pytest.raises(RuntimeError, match="deploy/sentinela.service"):
        servico.install()
    assert not (tmp_path / "cfg" / "systemd" / "user" / "sentinela.service").exists()


def test_scheduler_retries_failed_auto_backup_then_waits_next_day(env, monkeypatch):
    from sentinela import scheduler, settings
    e, st = env["engine"], env["storage"]
    st.init()
    e.save_connection({**PG, "port": "1", "password": "x"})  # nada escuta na porta 1
    st.set_setting("next_run_at", "2020-01-01 00:00:00")
    s = scheduler.Scheduler(tick=1)
    for attempt in range(1, settings.AUTO_RETRIES + 1):
        s.step()
        assert int(st.get_setting("auto_retries")) == attempt
        retry = e.next_run_at()
        assert 9 <= (retry - st.now()).total_seconds() / 60 <= 10
        st.set_setting("next_run_at", "2020-01-01 00:00:00")
    s.step()  # última tentativa: volta para o horário normal
    assert int(st.get_setting("auto_retries")) == 0
    nxt = e.next_run_at()
    assert nxt.hour == 0 and nxt.minute == 0 and nxt > st.now()
    fails = st.rows("SELECT status FROM backups WHERE trigger='auto'")
    assert [f["status"] for f in fails] == ["error"] * (settings.AUTO_RETRIES + 1)


def test_scheduler_waits_after_startup(env):
    from sentinela import scheduler
    e, st = env["engine"], env["storage"]
    st.init()
    e.save_connection(dict(PG))
    st.set_setting("next_run_at", "2020-01-01 00:00:00")
    scheduler.Scheduler(tick=1, grace=3600).step()
    assert not st.rows("SELECT id FROM backups")


def test_web_servico_endpoints(env, monkeypatch):
    import importlib
    import sentinela.web as web
    from werkzeug.security import generate_password_hash
    servico = _servico(env)
    importlib.reload(web)
    env["storage"].upsert_user("admin", generate_password_hash("senha-forte-123"))
    c = web.create_app().test_client()
    assert c.get("/api/servico").status_code == 401
    c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"})
    st = c.get("/api/servico").get_json()["servico"]
    assert set(st) >= {"supported", "enabled", "managed", "background", "how"}
    assert c.get("/api/state").get_json()["servico"] == st
    monkeypatch.setenv("SENTINELA_GERENCIADO", "Docker (reinicia sozinho)")
    r = c.post("/api/servico", json={"enabled": True})
    assert r.status_code == 400 and "Docker" in r.get_json()["error"]
    assert c.post("/api/servico/encerrar").status_code == 409  # nenhuma instância
    env["engine"].save_connection(dict(PG))
    health = c.get("/api/state").get_json()["health"]
    assert any(h["title"] == "Inicia com o computador" and h["state"] == "ok" for h in health)
    monkeypatch.delenv("SENTINELA_GERENCIADO")
    if servico.status()["supported"]:
        health = c.get("/api/state").get_json()["health"]
        assert any(h["title"] == "Backups só com o Sentinela aberto" for h in health)


# ---------------------------------------------------- de ponta a ponta

class Panel:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.jar = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, data=None, timeout=30):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.jar.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def up(self):
        try:
            return self.call("GET", "/api/me", timeout=2)[0] == 200
        except OSError:
            return False


def _wait(cond, timeout=60, step=0.5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return None


@linux_only
@needs_pg
def test_window_to_background_then_reboot_runs_missed_backup(env, fake_systemd, tmp_path):
    """Fluxo do usuário: abre o Sentinela numa janela, configura, ativa "Iniciar
    com o computador" (passa para o segundo plano na hora, mesmo endereço),
    desliga o PC (encerra) e liga de novo depois da meia-noite: o comando
    registrado sobe o Sentinela sozinho e o backup atrasado roda."""
    port = _free_port()
    run_env = dict(os.environ, SENTINELA_STARTUP_GRACE="2", SENTINELA_TICK="1")
    log = open(tmp_path / "janela.log", "w")
    win = subprocess.Popen([sys.executable, "-m", "sentinela", "serve", "--port", str(port)],
                           cwd=ROOT, env=run_env, stdout=log, stderr=subprocess.STDOUT)
    try:
        text = _wait(lambda: (lambda t: "ouvindo em" in t and t)(
            (tmp_path / "janela.log").read_text()), 30)
        assert text, (tmp_path / "janela.log").read_text()
        pw = re.search(r"senha: (\S+)", text).group(1)
        p = Panel(f"http://127.0.0.1:{port}")
        assert p.call("POST", "/api/login", {"username": "admin", "password": pw})[0] == 200
        assert p.call("PUT", "/api/policy", {"directory": str(env["backups"])})[0] == 200
        assert p.call("PUT", "/api/connection", PG)[0] == 200
        st = p.call("GET", "/api/servico")[1]["servico"]
        assert st["running"] and not st["background"] and not st["enabled"]

        # Segunda abertura com a janela aberta: recusa e aponta o endereço
        r = subprocess.run([sys.executable, "-m", "sentinela", "serve"], cwd=ROOT, env=run_env,
                           capture_output=True, text=True, timeout=30)
        assert r.returncode != 0 and f"127.0.0.1:{port}" in r.stderr

        code, r = p.call("POST", "/api/servico", {"enabled": True})
        assert code == 200 and r["handoff"] and r["servico"]["enabled"]
        assert win.wait(30) == 0  # a janela sai sozinha
        st = _wait(lambda: p.up() and p.call("GET", "/api/servico")[1]["servico"], 60)
        assert st and st["background"] and st["url"] == f"http://127.0.0.1:{port}/", st
        assert (env["home"] / "logs" / "segundo-plano.log").exists()

        # "Desliga o computador" (encerra) ...
        assert p.call("POST", "/api/servico/encerrar")[0] == 200
        assert _wait(lambda: not p.up(), 30) is not None and not p.up()
        assert _wait(lambda: subprocess.run(
            [sys.executable, "-m", "sentinela", "servico", "status"], cwd=ROOT, env=run_env,
            capture_output=True, text=True).stdout.startswith("Rodando:           não"), 15)

        # ... e liga depois da meia-noite: o backup agendado ficou para trás
        db = sqlite3.connect(env["home"] / "sentinela.db")
        db.execute("UPDATE settings SET value=? WHERE key='next_run_at'", (json.dumps("2020-01-01 00:00:00"),))
        db.commit()
        db.close()
        unit = (fake_systemd / "systemd" / "user" / "sentinela.service").read_text()
        exec_start = re.search(r"^ExecStart=(.+)$", unit, re.M).group(1)
        boot = subprocess.Popen(shlex.split(exec_start), env=run_env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            assert _wait(p.up, 60)
            assert p.call("POST", "/api/login", {"username": "admin", "password": pw})[0] == 200
            b = _wait(lambda: next((x for x in p.call("GET", "/api/backups")[1]["backups"]
                                    if x["trigger"] == "auto" and x["status"] != "running"), None), 120)
            assert b and b["status"] == "success", b
            seg = (env["home"] / "logs" / "sentinela.log").read_text()
            assert "Backup automático atrasado" in seg
            assert p.call("GET", "/api/state")[1]["next_run_at"] > "2020"
        finally:
            subprocess.run([sys.executable, "-m", "sentinela", "servico", "parar"], cwd=ROOT,
                           env=run_env, timeout=120)
            assert boot.wait(30) == 0
    finally:
        if win.poll() is None:
            win.kill()
        for _ in range(3):  # o processo de segundo plano da troca
            subprocess.run([sys.executable, "-m", "sentinela", "servico", "parar"], cwd=ROOT,
                           env=run_env, capture_output=True, timeout=120)
