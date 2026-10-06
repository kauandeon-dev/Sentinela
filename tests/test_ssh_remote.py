"""Bateria de testes do túnel SSH contra um servidor remoto REAL e isolado.

O ambiente é criado por ``tests/remote/setup.sh`` (namespace de rede Linux):
o PostgreSQL e o MariaDB do "servidor remoto" (10.77.0.2) escutam somente em
127.0.0.1 dentro do namespace — a única forma de alcançá-los é pelo túnel SSH.
Sem o ambiente, os testes são ignorados.
"""

import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

NS = "sentinela-remoto"
BASE = "/tmp/sentinela-remoto"
KEYS = f"{BASE}/keys"
MARIA_SOCK = f"{BASE}/maria/maria.sock"
REMOTE = "10.77.0.2"
DB_PASS = "Remota#2026"


def _remote_available():
    try:
        socket.create_connection((REMOTE, 22), timeout=1).close()
    except OSError:
        return False
    return os.path.exists(f"{KEYS}/ed25519") and os.path.exists(MARIA_SOCK)


pytestmark = pytest.mark.skipif(not _remote_available(),
                                reason="servidor remoto de teste indisponível (tests/remote/setup.sh)")


# ----------------------------------------------------------------- utilidades

def key(name):
    # Lida também na coleta (parametrize): sem o ambiente remoto, devolve vazio
    # e os testes são ignorados pelo skipif do módulo.
    try:
        with open(f"{KEYS}/{name}") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def ssh_pw(user="tunel", password="SenhaSsh#1", **kw):
    return {"enabled": True, "host": REMOTE, "port": "22", "user": user,
            "auth": "password", "password": password, **kw}


def ssh_key(name="ed25519", user="tunel", passphrase=None, **kw):
    d = {"enabled": True, "host": REMOTE, "port": "22", "user": user,
         "auth": "key", "private_key": key(name), **kw}
    if passphrase:
        d["key_passphrase"] = passphrase
    return d


RPG = {"sgbd": "postgres", "host": "localhost", "port": "5432", "dbname": "loja_remota",
       "user": "backup_user", "password": DB_PASS}
RMARIA = {"sgbd": "mariadb", "host": "localhost", "port": "3306", "dbname": "loja_remota",
          "user": "backup_user", "password": DB_PASS}


def setup(env, conn, ssh, **policy):
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"]), **policy})
    e.save_connection({**conn, "ssh": ssh})
    return e


def rpsql(sql):
    """Executa SQL no PostgreSQL do servidor remoto (por dentro do namespace)."""
    p = subprocess.run(["ip", "netns", "exec", NS, "psql", "-h", "127.0.0.1", "-U", "backup_user",
                        "-d", "loja_remota", "-w", "-X", "-tAc", sql],
                       env={**os.environ, "PGPASSWORD": DB_PASS}, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


def rmaria(sql):
    p = subprocess.run(["mariadb", f"--socket={MARIA_SOCK}", "-uroot", "--default-character-set=utf8mb4",
                        "-N", "-B", "loja_remota", "-e", sql], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


def pg_fingerprint():
    """Estado completo do banco PG remoto (contagens + hashes de conteúdo)."""
    return rpsql("""
      SELECT (SELECT count(*) FROM clientes) || ':' ||
             (SELECT md5(string_agg(c::text, '|' ORDER BY id)) FROM clientes c) || ':' ||
             (SELECT count(*) FROM ordens_servico) || ':' ||
             (SELECT md5(string_agg(o::text, '|' ORDER BY id)) FROM ordens_servico o) || ':' ||
             (SELECT count(*) FROM eventos) || ':' ||
             (SELECT sum(('x' || substr(md5(e::text), 1, 8))::bit(32)::bigint) FROM eventos e) || ':' ||
             (SELECT total_cliente(1)) || ':' || (SELECT count(*) FROM resumo)""")


def maria_fingerprint():
    return rmaria("""
      SELECT CONCAT((SELECT COUNT(*) FROM clientes), ':',
                    (SELECT MD5(GROUP_CONCAT(id, nome, HEX(cidade) ORDER BY id)) FROM clientes), ':',
                    (SELECT COUNT(*) FROM radacct), ':',
                    (SELECT SUM(CRC32(CONCAT_WS('|', radacctid, username, acctinputoctets,
                                                acctoutputoctets, acctstarttime))) FROM radacct), ':',
                    (SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='loja_remota'), ':',
                    (SELECT COUNT(*) FROM information_schema.views WHERE table_schema='loja_remota'), ':',
                    (SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema='loja_remota'), ':',
                    (SELECT SUM(total) FROM v_consumo))""")


def lines(env, execution_id):
    return [r["message"] for r in env["storage"].rows(
        "SELECT message FROM log_lines WHERE execution_id=? ORDER BY id", (execution_id,))]


def backup_ok(e, trigger="manual"):
    bid = e.start_backup(trigger, wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "success", b["error"]
    return b


def last_restore(env):
    return env["storage"].row("SELECT * FROM executions WHERE kind='restore' ORDER BY id DESC")


def remote_ssh_sessions(user="tunel"):
    out = subprocess.run(["pgrep", "-fc", f"sshd: {user}"], capture_output=True, text=True).stdout
    return int(out.strip() or 0)


# ============================================================ autenticação

def test_password_auth(env):
    e = setup(env, RPG, ssh_pw())
    version, fp = e.test_connection()
    assert version.startswith("PostgreSQL")
    assert fp.startswith("SHA256:")


@pytest.mark.parametrize("name,passphrase", [
    ("ed25519", None), ("rsa", None), ("rsa_pem", None), ("ecdsa", None),
    ("ed25519_senha", "frase-da-chave"), ("rsa_pem_senha", "frase-da-chave"),
])
def test_key_types(env, name, passphrase):
    e = setup(env, RPG, ssh_key(name, passphrase=passphrase))
    assert e.test_connection()[0].startswith("PostgreSQL")


@pytest.mark.parametrize("name", ["ed25519_senha", "rsa_pem_senha"])
def test_protected_key_requires_passphrase(env, name):
    with pytest.raises(ValueError) as ex:
        env["engine"].save_connection({**RPG, "ssh": ssh_key(name)})
    assert "protegida" in str(ex.value)


@pytest.mark.parametrize("name", ["ed25519_senha", "rsa_pem_senha"])
def test_wrong_passphrase(env, name):
    with pytest.raises(ValueError) as ex:
        env["engine"].save_connection({**RPG, "ssh": ssh_key(name, passphrase="errada")})
    assert "senha da chave" in str(ex.value).lower()


def test_key_with_windows_line_endings(env):
    d = ssh_key("ed25519")
    d["private_key"] = d["private_key"].replace("\n", "\r\n")
    e = setup(env, RPG, d)
    assert e.test_connection()[0].startswith("PostgreSQL")


def test_key_with_surrounding_whitespace(env):
    d = ssh_key("rsa")
    d["private_key"] = "\n\n   " + d["private_key"].strip() + "   \n\n"
    e = setup(env, RPG, d)
    assert e.test_connection()[0].startswith("PostgreSQL")


@pytest.mark.parametrize("text", [
    "isso não é uma chave",
    "PuTTY-User-Key-File-3: ssh-ed25519\nEncryption: none\nComment: x\nPublic-Lines: 2\nAAAA\nAAAA\n",
])
def test_invalid_key_text(env, text):
    with pytest.raises(ValueError) as ex:
        env["engine"].save_connection({**RPG, "ssh": {**ssh_key(), "private_key": text}})
    assert "chave" in str(ex.value).lower()


def test_public_key_pasted_instead_of_private(env):
    with pytest.raises(ValueError) as ex:
        env["engine"].save_connection({**RPG, "ssh": {**ssh_key(), "private_key": key("ed25519.pub")}})
    assert "pública" in str(ex.value).lower()


@pytest.mark.parametrize("ssh", [
    ssh_key("nao_autorizada"),
    ssh_pw(password="senha-errada"),
    ssh_pw(user="usuario_inexistente"),
    ssh_pw(user="sochave"),  # servidor só aceita chave para este usuário
], ids=["chave-nao-autorizada", "senha-errada", "usuario-inexistente", "senha-desabilitada"])
def test_auth_failures(env, ssh):
    e = setup(env, RPG, ssh)
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert "autenticação SSH" in str(ex.value)
    b = e.get_backup(e.start_backup("auto", wait=True))
    assert b["status"] == "error"
    assert "túnel SSH" in b["error"] and "autenticação" in b["error"]
    assert not list(env["backups"].glob("*"))


def test_secrets_never_stored_in_clear(env):
    setup(env, RPG, {**ssh_key("ed25519_senha", passphrase="frase-da-chave"), "password": "SenhaSsh#1"})
    raw = open(env["home"] / "sentinela.db", "rb").read()
    for needle in (b"PRIVATE KEY", b"frase-da-chave", b"SenhaSsh#1", DB_PASS.encode()):
        assert needle not in raw


# ================================================================== rede

def test_ssh_port_closed(env):
    e = setup(env, RPG, ssh_pw(port="2200"))
    t0 = time.monotonic()
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert time.monotonic() - t0 < 5
    assert "Não foi possível conectar ao servidor SSH" in str(ex.value)


def test_ssh_host_unreachable_times_out(env, monkeypatch):
    monkeypatch.setattr(env["engine"].settings, "CONNECT_TIMEOUT", 3)
    e = setup(env, RPG, ssh_pw(host="10.77.0.99"))
    t0 = time.monotonic()
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert time.monotonic() - t0 < 10
    assert "Não foi possível conectar ao servidor SSH" in str(ex.value)


def test_ssh_hostname_not_resolved(env):
    e = setup(env, RPG, ssh_pw(host="servidor.inexistente.invalid"))
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert "servidor.inexistente.invalid" in str(ex.value)


def test_db_port_closed_on_remote(env):
    e = setup(env, {**RPG, "port": "5439"}, ssh_pw())
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    msg = str(ex.value)
    assert "localhost:5439" in msg and "não conseguiu conectar" in msg
    b = e.get_backup(e.start_backup("auto", wait=True))
    assert b["status"] == "error" and "localhost:5439" in b["error"]


def test_wrong_db_password_through_tunnel(env):
    e = setup(env, {**RPG, "password": "errada"}, ssh_pw())
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert "password authentication failed" in str(ex.value)


def test_forwarding_disabled_on_server(env):
    e = setup(env, RPG, ssh_key(user="semforward"))
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert "não permite" in str(ex.value) and "encaminhamento" in str(ex.value)


def test_permitopen_restriction(env):
    e = setup(env, RPG, ssh_key(user="restrito"))
    assert e.test_connection()[0].startswith("PostgreSQL")
    backup_ok(e)
    e2 = setup(env, RMARIA, ssh_key(user="restrito"))
    with pytest.raises(RuntimeError) as ex:
        e2.test_connection()
    assert "não permite" in str(ex.value)


def test_db_host_resolved_by_remote_server(env):
    # "db.interno" só existe no /etc/hosts do servidor remoto
    e = setup(env, {**RPG, "host": "db.interno"}, ssh_pw())
    assert e.test_connection()[0].startswith("PostgreSQL")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_mariadb_host_variants(env, host):
    e = setup(env, {**RMARIA, "host": host}, ssh_pw())
    assert "MariaDB" in e.test_connection()[0]


# ============================================================ chave do host

def _real_fingerprint():
    out = subprocess.run(["ssh-keygen", "-lf", f"{BASE}/sshd/host_ed25519.pub"],
                         capture_output=True, text=True, check=True).stdout
    return out.split()[1]


def test_tofu_records_real_fingerprint(env):
    e = setup(env, RPG, ssh_pw())
    assert e.get_connection()["ssh"]["host_key"] is None
    b = backup_ok(e)
    hk = e.get_connection()["ssh"]["host_key"]
    assert hk["fingerprint"] == _real_fingerprint()
    assert any(_real_fingerprint() in m for m in lines(env, b["execution_id"]))


def test_host_key_mismatch_blocks_everything(env):
    e = setup(env, RPG, ssh_pw())
    good = backup_ok(e)
    c = env["storage"].get_setting("connection")
    c["ssh"]["host_key"] = {"type": "ssh-ed25519", "fingerprint": "SHA256:falsa",
                            "key": "AAAAC3NzaC1lZDI1NTE5AAAAIFakeFakeFakeFakeFakeFakeFakeFakeFakeFake"}
    env["storage"].set_setting("connection", c)
    with pytest.raises(RuntimeError) as ex:
        e.test_connection()
    assert "mudou" in str(ex.value)
    b = e.get_backup(e.start_backup("auto", wait=True))
    assert b["status"] == "error" and "mudou" in b["error"]
    before = pg_fingerprint()
    e.start_restore(good["id"], wait=True)
    r = last_restore(env)
    assert r["status"] == "error"
    assert any("mudou" in m for m in lines(env, r["id"]))
    assert pg_fingerprint() == before
    e.save_connection({"ssh": {"reset_host_key": True}})
    assert e.get_connection()["ssh"]["host_key"] is None
    backup_ok(e)
    assert e.get_connection()["ssh"]["host_key"]["fingerprint"] == _real_fingerprint()


def test_changing_ssh_host_clears_pinned_key(env):
    e = setup(env, RPG, ssh_pw())
    e.test_connection()
    assert e.get_connection()["ssh"]["host_key"]
    e.save_connection({"ssh": {"port": "2222", "host": "127.0.0.1"}})
    assert e.get_connection()["ssh"]["host_key"] is None


def test_draft_test_then_save_keeps_seen_key(env):
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    # conexão salva aponta para outro servidor; o teste usa o rascunho do formulário
    e.save_connection({**RPG, "ssh": ssh_pw(host="127.0.0.1", port="2222")})
    _, fp = e.test_connection({**RPG, "ssh": ssh_pw()})
    assert fp == _real_fingerprint()
    e.save_connection({**RPG, "ssh": ssh_pw()})
    assert e.get_connection()["ssh"]["host_key"]["fingerprint"] == _real_fingerprint()


# ======================================================= integridade dos dados

def test_postgres_full_roundtrip(env):
    e = setup(env, RPG, ssh_key("ed25519"))
    original = pg_fingerprint()
    b = backup_ok(e)
    assert b["raw_size"] > 100 * 1024 * 1024  # base remota tem ~170 MB
    ok, err = e.verify_backup(b["id"])
    assert ok, err
    # estragos variados no servidor remoto
    rpsql("DELETE FROM ordens_servico WHERE id % 3 = 0")
    rpsql("UPDATE clientes SET cidade = 'ALTERADA'")
    rpsql("DROP VIEW resumo; DROP FUNCTION total_cliente(int)")
    rpsql("TRUNCATE eventos")
    rpsql("CREATE TABLE lixo (x int)")
    e.start_restore(b["id"], wait=True)
    r = last_restore(env)
    assert r["status"] == "success", lines(env, r["id"])
    assert pg_fingerprint() == original
    msgs = lines(env, r["id"])
    assert any("Túnel SSH estabelecido" in m for m in msgs)
    assert any("Cópia pré-restauração criada" in m for m in msgs)
    rpsql("DROP TABLE IF EXISTS lixo")


def test_mariadb_full_roundtrip(env):
    e = setup(env, RMARIA, ssh_key("ecdsa"))
    original = maria_fingerprint()
    assert rmaria("SELECT HEX(cidade) FROM clientes WHERE id=1") == \
        "São Lourenço do Oeste".encode().hex().upper()
    b = backup_ok(e)
    rmaria("DELETE FROM radacct WHERE radacctid % 2 = 0")
    rmaria("UPDATE clientes SET cidade = 'X'")
    rmaria("DROP TRIGGER trg_cli")
    rmaria("DROP VIEW v_consumo")
    rmaria("DROP PROCEDURE sp_total")
    e.start_restore(b["id"], wait=True)
    r = last_restore(env)
    assert r["status"] == "success", lines(env, r["id"])
    assert maria_fingerprint() == original
    assert rmaria("SELECT HEX(cidade) FROM clientes WHERE id=1") == \
        "São Lourenço do Oeste".encode().hex().upper()
    assert any("DEFINER" in m for m in lines(env, r["id"]))
    assert rmaria("CALL sp_total(@n); SELECT @n") == "50000"


@pytest.mark.parametrize("enc,comp", [(True, True), (True, False), (False, True), (False, False)])
def test_all_protection_combos_via_ssh(env, enc, comp):
    e = setup(env, RMARIA, ssh_pw(), encryption=enc, compression=comp)
    b = backup_ok(e)
    ok, err = e.verify_backup(b["id"])
    assert ok, err


def test_cli_decrypt_backup_made_via_ssh(env, tmp_path):
    e = setup(env, RMARIA, ssh_pw())
    b = backup_ok(e)
    out = tmp_path / "recuperado.sql"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(["python3", "-m", "sentinela", "decrypt", b["path"], "-o", str(out)],
                   check=True, cwd=root, capture_output=True)
    sql = out.read_bytes()
    assert b"CREATE TABLE `radacct`" in sql and "São Lourenço".encode() in sql


# =================================================================== robustez

def test_ssh_dropped_mid_dump(env):
    e = setup(env, RPG, ssh_pw(), compression=False)
    before = remote_ssh_sessions()
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("id", e.start_backup("manual", wait=True)))
    t.start()
    # espera o dump começar a gravar e derruba a sessão SSH no servidor
    deadline = time.time() + 30
    while time.time() < deadline:
        parts = list(env["backups"].glob("*.part"))
        if parts and parts[0].stat().st_size > 5 * 1024 * 1024:
            break
        time.sleep(0.05)
    else:
        pytest.fail("dump não começou")
    subprocess.run(["pkill", "-f", "sshd: tunel"], check=False)
    t.join(60)
    b = e.get_backup(result["id"])
    assert b["status"] == "error", "backup interrompido não pode ser marcado como válido"
    assert "conexão SSH caiu" in b["error"]
    assert not list(env["backups"].glob("*.part"))
    assert not list(env["backups"].glob("*.enc"))
    time.sleep(1)
    backup_ok(e)  # o sistema se recupera na execução seguinte
    assert remote_ssh_sessions() <= before


def test_db_connection_killed_mid_dump(env):
    e = setup(env, RPG, ssh_pw(), compression=False, encryption=False)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("id", e.start_backup("manual", wait=True)))
    t.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        parts = list(env["backups"].glob("*.part"))
        if parts and parts[0].stat().st_size > 5 * 1024 * 1024:
            break
        time.sleep(0.05)
    rpsql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
          "WHERE usename='backup_user' AND pid <> pg_backend_pid()")
    t.join(60)
    b = e.get_backup(result["id"])
    assert b["status"] == "error"
    assert "SSH" not in b["error"]  # o túnel estava ok: a culpa é do banco
    assert "terminat" in b["error"]
    assert not list(env["backups"].glob("*.sql*"))


def test_no_resource_leaks(env):
    e = setup(env, RMARIA, ssh_pw())
    backup_ok(e)  # aquece
    time.sleep(1)
    threads0 = threading.active_count()
    fds0 = len(os.listdir("/proc/self/fd"))
    sessions0 = remote_ssh_sessions()
    for _ in range(12):
        e.test_connection()
        backup_ok(e)
    time.sleep(2)
    assert threading.active_count() <= threads0 + 1
    assert len(os.listdir("/proc/self/fd")) <= fds0 + 3
    assert remote_ssh_sessions() <= sessions0


def test_scheduler_runs_auto_backup_via_ssh(env):
    from sentinela import scheduler
    e = setup(env, RPG, ssh_pw())
    env["storage"].set_setting("next_run_at", "2020-01-01 00:00:00")
    scheduler.Scheduler(tick=1).step()
    b = env["storage"].row("SELECT * FROM backups ORDER BY created_at DESC LIMIT 1")
    assert b["trigger"] == "auto" and b["status"] == "success", b["error"]
    nxt = e.next_run_at()
    assert nxt > env["storage"].now() and nxt.hour == 0 and nxt.minute == 0


# ======================================================================= API

def _client(env):
    import importlib
    from werkzeug.security import generate_password_hash
    import sentinela.web as web
    importlib.reload(web)
    env["storage"].upsert_user("admin", generate_password_hash("senha-forte-123"))
    c = web.create_app().test_client()
    assert c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"}).status_code == 200
    return c


def _wait_idle(c, timeout=120):
    t0 = time.time()
    while c.get("/api/state").get_json()["running"]:
        assert time.time() - t0 < timeout
        time.sleep(0.2)


def test_api_full_flow_via_ssh(env):
    c = _client(env)
    secret_key = key("ed25519_senha")
    assert c.put("/api/policy", json={"directory": str(env["backups"])}).status_code == 200
    ssh = ssh_key("ed25519_senha", passphrase="frase-da-chave")
    r = c.post("/api/connection/test", json={**RMARIA, "ssh": ssh}).get_json()
    assert r["ok"], r
    assert r["ssh_host_key"] == _real_fingerprint()
    r = c.put("/api/connection", json={**RMARIA, "ssh": ssh})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    state = c.get("/api/state").get_data(as_text=True)
    for leak in (secret_key.strip().splitlines()[1], "frase-da-chave", DB_PASS):
        assert leak not in body and leak not in state
    js = c.get("/api/state").get_json()["connection"]["ssh"]
    assert js["enabled"] and js["has_private_key"] and js["has_passphrase"]
    assert js["host_key"] == _real_fingerprint()

    bid = c.post("/api/backups").get_json()["id"]
    assert c.post("/api/backups").status_code == 409  # já há execução em andamento
    _wait_idle(c)
    b = c.get(f"/api/backups/{bid}").get_json()
    assert b["backup"]["status"] == "success"
    assert any("Túnel SSH estabelecido" in ln["message"] for ln in b["logs"])

    original = maria_fingerprint()
    rmaria("DELETE FROM clientes WHERE id = 2")
    assert c.post(f"/api/backups/{bid}/restore").status_code == 202
    _wait_idle(c)
    assert maria_fingerprint() == original
    logs = c.get("/api/logs").get_json()["executions"]
    kinds = [x["kind"] for x in logs]
    assert "restore" in kinds and kinds.count("backup") >= 2  # original + pré-restauração
    d = c.get(f"/api/backups/{bid}/download")
    assert d.status_code == 200 and d.data[:4] == b"SNTL"


def test_api_test_reports_tunnel_errors(env):
    c = _client(env)
    r = c.post("/api/connection/test", json={**RPG, "ssh": ssh_pw(password="x")}).get_json()
    assert r["ok"] is False and "autenticação SSH" in r["error"]
    r = c.post("/api/connection/test", json={**RPG, "port": "5439", "ssh": ssh_pw()}).get_json()
    assert r["ok"] is False and "localhost:5439" in r["error"]
    r = c.put("/api/connection", json={**RPG, "ssh": {**ssh_key(), "private_key": "lixo"}})
    assert r.status_code == 400
    r = c.put("/api/connection", json={**RPG, "ssh": {"enabled": True, "host": "", "user": ""}})
    assert r.status_code == 400


def test_switch_back_to_direct_connection(env):
    """Desligar o túnel volta para conexão direta (que aqui falha, pois o banco é remoto)."""
    e = setup(env, RPG, ssh_pw())
    backup_ok(e)
    e.save_connection({"host": REMOTE, "ssh": {"enabled": False}})
    with pytest.raises(RuntimeError):
        e.test_connection()
    e.save_connection({"host": "localhost", "ssh": {"enabled": True}})
    backup_ok(e)


@pytest.mark.skipif(not shutil.which("ss"), reason="ss indisponível")
def test_tunnel_listens_only_on_loopback(env):
    from sentinela import tunnel
    ssh = {**ssh_pw(), "host_key": None}
    with tunnel.open_tunnel(ssh, "localhost", 5432) as t:
        out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
        line = [ln for ln in out.splitlines() if f":{t.local_port} " in ln]
        assert line and "127.0.0.1" in line[0]
    out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True).stdout
    assert f":{t.local_port} " not in out


def test_missing_routine_privilege_fails_loudly_with_hint(env):
    """Sem permissão para ler procedures, o backup FALHA (nunca sai incompleto) e explica o motivo."""
    def grant(action):
        for host in ("127.0.0.1", "localhost"):
            subprocess.run(["mariadb", f"--socket={MARIA_SOCK}", "-uroot", "-e",
                            f"{action} SELECT ON mysql.proc {'FROM' if action == 'REVOKE' else 'TO'} "
                            f"'backup_user'@'{host}'"], capture_output=True)
    rmaria("CREATE DEFINER=`root`@`localhost` PROCEDURE sp_do_root() SELECT 1")
    grant("REVOKE")
    try:
        e = setup(env, RMARIA, ssh_pw())
        b = e.get_backup(e.start_backup("manual", wait=True))
        assert b["status"] == "error"
        assert "SHOW CREATE" in b["error"] and "GRANT SELECT ON mysql.proc" in b["error"]
        assert not list(env["backups"].glob("*"))
    finally:
        grant("GRANT")
        rmaria("DROP PROCEDURE IF EXISTS sp_do_root")


@pytest.mark.slow
def test_silent_network_loss_mid_dump_does_not_hang(env, monkeypatch):
    """Rede some sem aviso (pacotes descartados): o backup precisa falhar em
    tempo limitado, nunca ficar parado para sempre."""
    from sentinela import tunnel
    monkeypatch.setattr(tunnel, "DEAD_PEER_TIMEOUT", 15)
    e = setup(env, RPG, ssh_pw(), compression=False, encryption=False)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("id", e.start_backup("manual", wait=True)),
                         daemon=True)
    t.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        parts = list(env["backups"].glob("*.part"))
        if parts and parts[0].stat().st_size > 5 * 1024 * 1024:
            break
        time.sleep(0.05)
    down = ["ip", "netns", "exec", NS, "ip", "link", "set", "srv1", "down"]
    up = ["ip", "netns", "exec", NS, "ip", "link", "set", "srv1", "up"]
    t0 = time.monotonic()
    subprocess.run(down, check=True)
    try:
        t.join(180)
        elapsed = time.monotonic() - t0
    finally:
        subprocess.run(up, check=True)
        subprocess.run(["ip", "netns", "exec", NS, "ip", "addr", "replace", f"{REMOTE}/24",
                        "dev", "srv1"], check=False)
    assert not t.is_alive(), "backup travou após queda silenciosa da rede"
    assert elapsed < 120
    b = e.get_backup(result["id"])
    assert b["status"] == "error"
    assert "conexão SSH caiu" in b["error"]
    assert not list(env["backups"].glob("*.sql*"))
    time.sleep(2)
    backup_ok(e)  # rede de volta: tudo normal


# ============================================ completude do dump (MariaDB)

def _ro_user(with_proc):
    sqls = ["DROP USER IF EXISTS 'ro'@'localhost'",
            "CREATE USER 'ro'@'localhost' IDENTIFIED BY 'Ro#2026'",
            "GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT ON loja_remota.* TO 'ro'@'localhost'"]
    if with_proc:
        sqls.append("GRANT SELECT ON mysql.proc TO 'ro'@'localhost'")
    for q in sqls:
        subprocess.run(["mariadb", f"--socket={MARIA_SOCK}", "-uroot", "-e", q], check=True)


def test_routines_verified_when_privilege_present(env):
    _ro_user(with_proc=True)
    e = setup(env, {**RMARIA, "user": "ro", "password": "Ro#2026"}, ssh_pw())
    b = backup_ok(e)
    msgs = lines(env, b["execution_id"])
    assert any("Conferência: 1 procedure(s)/function(s)" in m for m in msgs)
    assert not any(m.startswith("Não foi possível conferir") for m in msgs)


def test_invisible_routines_are_reported_not_silent(env):
    """Sem permissão, o mariadb-dump pula rotinas SEM ERRO; o Sentinela avisa."""
    _ro_user(with_proc=False)
    e = setup(env, {**RMARIA, "user": "ro", "password": "Ro#2026"}, ssh_pw())
    b = backup_ok(e)
    msgs = lines(env, b["execution_id"])
    assert any("Não foi possível conferir procedures/functions" in m for m in msgs)
    import importlib
    import sentinela.web as web
    importlib.reload(web)
    health = web._health(e.get_policy(), e.get_connection(), [b], None, 1)
    assert any(h["title"] == "Permissões do usuário de backup" and h["state"] == "warn" for h in health)


def test_missing_routines_fail_the_backup(env, monkeypatch):
    from sentinela import dumpers
    e = setup(env, RMARIA, ssh_pw())
    monkeypatch.setattr(dumpers.MariaDBAdapter, "preflight", lambda self: ([], {"routines": 5}))
    b = e.get_backup(e.start_backup("manual", wait=True))
    assert b["status"] == "error"
    assert "Dump incompleto" in b["error"] and "5 procedure" in b["error"]
    assert not list(env["backups"].glob("*"))


def test_cli_backup_blocked_while_panel_backup_runs(env):
    """Trava entre processos: `sentinela backup` (cron) não roda junto com o painel."""
    e = setup(env, RPG, ssh_pw(), compression=False)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("id", e.start_backup("manual", wait=True)))
    t.start()
    deadline = time.time() + 30
    while time.time() < deadline and not list(env["backups"].glob("*.part")):
        time.sleep(0.05)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = subprocess.run(["python3", "-m", "sentinela", "backup"], cwd=root, capture_output=True,
                       text=True, env={**os.environ})
    t.join(120)
    assert p.returncode != 0
    assert "Outro processo do Sentinela" in p.stderr
    assert e.get_backup(result["id"])["status"] == "success"
    # terminado o backup do painel, a linha de comando funciona
    p = subprocess.run(["python3", "-m", "sentinela", "backup"], cwd=root, capture_output=True,
                       text=True, env={**os.environ})
    assert p.returncode == 0, p.stderr
    assert ": success" in p.stdout
