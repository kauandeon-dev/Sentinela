import os
import time

import pytest
from werkzeug.security import generate_password_hash

from conftest import PG, fake_backup, needs_pg


def _client(env):
    import importlib
    import sentinela.web as web
    importlib.reload(web)
    env["storage"].upsert_user("admin", generate_password_hash("senha-forte-123"))
    return web.create_app().test_client()


def _login(c):
    r = c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"})
    assert r.status_code == 200


def test_requires_login(env):
    c = _client(env)
    assert c.get("/api/state").status_code == 401
    assert c.post("/api/login", json={"username": "admin", "password": "x"}).status_code == 401
    _login(c)
    assert c.get("/api/state").status_code == 200


def test_bruteforce_lock(env):
    c = _client(env)
    for _ in range(5):
        c.post("/api/login", json={"username": "admin", "password": "x"})
    r = c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"})
    assert r.status_code == 429


def test_password_never_returned(env):
    c = _client(env)
    _login(c)
    r = c.put("/api/connection", json={**PG, "password": "segredo!"})
    assert r.status_code == 200
    assert b"segredo" not in r.data
    s = c.get("/api/state").get_json()
    assert s["connection"]["has_password"] is True
    assert "password_sealed" not in s["connection"]


def test_invalid_directory(env):
    c = _client(env)
    _login(c)
    r = c.put("/api/policy", json={"directory": "nao/absoluto"})
    assert r.status_code == 400


@needs_pg
def test_full_flow(env):
    c = _client(env)
    _login(c)
    c.put("/api/policy", json={"directory": str(env["backups"])})
    c.put("/api/connection", json=PG)
    assert c.post("/api/connection/test", json={}).get_json()["ok"]
    r = c.post("/api/backups")
    assert r.status_code == 202
    bid = r.get_json()["id"]
    for _ in range(100):
        b = c.get(f"/api/backups/{bid}").get_json()["backup"]
        if b["status"] != "running":
            break
        time.sleep(0.1)
    assert b["status"] == "success"
    while c.get("/api/state").get_json()["running"]:
        time.sleep(0.1)
    d = c.get(f"/api/backups/{bid}/download")
    assert d.status_code == 200 and d.data[:4] == b"SNTL"
    d.close()  # libera o arquivo (no Windows, arquivo aberto não pode ser apagado)
    assert c.get("/api/logs").get_json()["executions"]
    assert c.get("/api/backups?filter=manual").get_json()["backups"][0]["id"] == bid
    assert c.delete(f"/api/backups/{bid}").status_code == 200
    assert c.get("/api/backups").get_json()["backups"] == []


@needs_pg
def test_live_logs_state_chart_and_health(env):
    c = _client(env)
    _login(c)
    c.put("/api/policy", json={"directory": str(env["backups"])})
    c.put("/api/connection", json=PG)
    s = c.get("/api/state").get_json()
    assert s["current"] is None and s["chart"] == []
    assert any(h["title"] == "Nenhuma cópia válida ainda" for h in s["health"])

    base = c.get("/api/logs").get_json()["last_id"]
    bid = c.post("/api/backups").get_json()["id"]
    cur = c.get("/api/state").get_json()["current"]
    assert cur is None or (cur["kind"] == "backup" and cur["backup_id"] == bid)
    seen, since = [], base
    for _ in range(300):
        t = c.get(f"/api/logs/tail?since={since}").get_json()
        seen += t["lines"]
        assert all(ln["id"] > since for ln in t["lines"])
        since = t["last_id"]
        if not t["running"] and any("Backup concluído" in ln["message"] for ln in seen):
            break
        time.sleep(0.05)
    msgs = [ln["message"] for ln in seen]
    assert msgs[0].startswith("Iniciando backup manual")
    assert "Backup concluído" in msgs[-1] or any("Backup concluído" in m for m in msgs)
    ids = [ln["id"] for ln in seen]
    assert ids == sorted(ids) and len(ids) == len(set(ids))  # sem linhas repetidas

    # nada novo depois do fim
    t = c.get(f"/api/logs/tail?since={since}").get_json()
    assert t["lines"] == [] and t["running"] is False and t["current"] is None

    s = c.get("/api/state").get_json()
    assert [b["id"] for b in s["chart"]] == [bid]
    titles = {h["title"]: h["state"] for h in s["health"]}
    assert titles["Cópia recente disponível"] == "ok"
    assert titles["Integridade verificada"] == "ok"
    assert titles["Criptografia AES-256"] == "ok"


def test_progress_interval():
    from sentinela import engine
    assert engine._progress_interval(0) == 2
    assert engine._progress_interval(45) == 10
    assert engine._progress_interval(3600) == 60


def test_login_lockout_uses_real_ip_behind_proxy(env, monkeypatch):
    monkeypatch.setenv("SENTINELA_HTTPS", "1")
    c = _client(env)
    for _ in range(5):
        c.post("/api/login", json={"username": "admin", "password": "x"},
               headers={"X-Forwarded-For": "203.0.113.9"})
    blocked = c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"},
                     headers={"X-Forwarded-For": "203.0.113.9"})
    assert blocked.status_code == 429
    other = c.post("/api/login", json={"username": "admin", "password": "senha-forte-123"},
                   headers={"X-Forwarded-For": "198.51.100.7"})
    assert other.status_code == 200  # o administrador em outro IP não é bloqueado


# ----------------------------------------------------- cópias externas e avisos

def test_destinations_api_hides_secrets(env, s3):
    c = _client(env)
    _login(c)
    c.put("/api/policy", json={"directory": str(env["backups"])})
    r = c.post("/api/destinations/test", json=s3["dest"])
    assert r.get_json()["ok"] is True
    r = c.post("/api/destinations/test", json={**s3["dest"], "bucket": "nao-existe-abc"})
    assert r.get_json() == {"ok": False, "error": "Não foi possível acessar o bucket nao-existe-abc: "
                                                 "o bucket (ou objeto) não existe"}
    r = c.post("/api/destinations", json=s3["dest"])
    assert r.status_code == 201 and b"segredo" not in r.data
    did = r.get_json()["destination"]["id"]
    lst = c.get("/api/destinations").get_json()
    assert lst["destinations"][0]["has_secret_key"] and b"segredo" not in c.get("/api/destinations").data
    # editar sem o segredo mantém o salvo; o teste do formulário usa o segredo guardado
    assert c.put(f"/api/destinations/{did}", json={"name": "Nuvem"}).status_code == 200
    assert c.post("/api/destinations/test", json={"id": did, "type": "s3"}).get_json()["ok"]
    assert c.post("/api/destinations", json={"type": "xyz"}).status_code == 400
    assert c.post("/api/destinations/sync", json={}).get_json() == {"execution": None}
    assert c.delete(f"/api/destinations/{did}").status_code == 200
    assert c.get("/api/destinations").get_json()["destinations"] == []


@needs_pg
def test_backup_detail_lists_replicas_and_state_has_rule(env, s3):
    c = _client(env)
    _login(c)
    c.put("/api/policy", json={"directory": str(env["backups"])})
    c.put("/api/connection", json=PG)
    c.post("/api/destinations", json=s3["dest"])
    bid = c.post("/api/backups").get_json()["id"]
    for _ in range(100):
        if not c.get("/api/state").get_json()["running"]:
            break
        time.sleep(0.2)
    d = c.get(f"/api/backups/{bid}").get_json()
    assert d["replicas"][0]["status"] == "success" and d["replicas"][0]["dest_type"] == "s3"
    assert d["backup"]["local"] is True
    s = c.get("/api/state").get_json()
    assert s["rule321"]["copies"] == 3 and s["rule321"]["offsite"] == 1
    titles = [h["title"] for h in s["health"]]
    assert "Regra 3-2-1" in titles and "Avisos de falha" in titles
    assert "Chave mestra fora do servidor" in titles


def test_notifications_api(env):
    c = _client(env)
    _login(c)
    r = c.put("/api/notifications", json={"telegram": {"enabled": True, "token": "1:SEGREDO", "chat_id": "9"}})
    assert r.status_code == 200 and b"SEGREDO" not in r.data
    g = c.get("/api/notifications").get_json()
    assert g["config"]["telegram"]["has_token"] and g["config"]["active"] == ["telegram"]
    assert c.put("/api/notifications", json={"email": {"enabled": True}}).status_code == 400
    assert c.post("/api/notifications/test", json={"telegram": {"enabled": False}}).status_code == 400


def test_key_export_requires_password(env):
    c = _client(env)
    _login(c)
    assert c.post("/api/key/export", json={"password": "errada"}).status_code == 403
    r = c.post("/api/key/export", json={"password": "senha-forte-123"})
    assert r.status_code == 200 and r.data == env["engine"].key()
    assert "attachment" in r.headers["Content-Disposition"]
    assert c.get("/api/state").get_json()["key_exported_at"]


def test_connection_password_can_be_cleared(env):
    """root sem senha (MySQL/MariaDB local): campo vazio mantém a senha salva,
    por isso há o pedido explícito "Usuário sem senha"."""
    c = _client(env)
    _login(c)
    c.put("/api/connection", json={**PG, "password": "antiga"})
    assert c.get("/api/state").get_json()["connection"]["has_password"] is True
    c.put("/api/connection", json={**PG, "password": ""})          # vazio: mantém
    assert c.get("/api/state").get_json()["connection"]["has_password"] is True
    c.put("/api/connection", json={**PG, "password": "", "clear_password": True})
    assert c.get("/api/state").get_json()["connection"]["has_password"] is False
    assert env["engine"].get_connection(with_password=True)["password"] == ""


SQL = "-- PostgreSQL database dump\nINSERT INTO clientes VALUES (1, 'São Lourenço do Oeste');\n" \
      "-- PostgreSQL database dump complete\n"


def _sql_link(c, bid, password="senha-forte-123"):
    return c.post(f"/api/backups/{bid}/sql-token", json={"password": password})


@pytest.mark.parametrize("compressed,encrypted", [(True, True), (False, True), (True, False)])
def test_sql_download_plain_with_password_and_single_use_link(env, compressed, encrypted):
    c = _client(env)
    bid, path = fake_backup(env, SQL.encode(), compressed, encrypted)
    assert _sql_link(c, bid).status_code == 401                    # sem login
    _login(c)
    assert _sql_link(c, bid, "errada").status_code == 403          # senha errada
    r = _sql_link(c, bid)
    assert r.status_code == 200
    link = r.get_json()
    assert link["filename"] == os.path.basename(path).split(".sql")[0] + ".sql"
    d = c.get(link["url"])
    assert d.status_code == 200 and d.data.decode() == SQL
    assert d.headers["Content-Disposition"] == f"attachment; filename={link['filename']}"
    assert c.get(link["url"]).status_code == 403                   # link de uso único
    other, _ = fake_backup(env, b"-- outra", True, True)
    t = _sql_link(c, bid).get_json()["url"].split("?t=")[1]
    assert c.get(f"/api/backups/{other}/sql?t={t}").status_code == 403   # preso à cópia
    assert c.get(f"/api/backups/{bid}/sql").status_code == 403


def test_sql_download_link_expires_and_needs_same_user(env, monkeypatch):
    import sentinela.web as web
    c = _client(env)
    _login(c)
    bid, _ = fake_backup(env, SQL.encode())
    url = _sql_link(c, bid).get_json()["url"]
    env["storage"].upsert_user("outro", generate_password_hash("outra-senha-123"))
    c2 = web.create_app().test_client()
    assert c2.post("/api/login", json={"username": "outro", "password": "outra-senha-123"}).status_code == 200
    assert c2.get(url).status_code == 403                          # outro usuário
    monkeypatch.setattr(web, "SQL_TOKEN_TTL", -1)
    url = _sql_link(c, bid).get_json()["url"]
    assert c.get(url).status_code == 403                           # expirado


def test_sql_download_refuses_tampered_missing_or_foreign_key(env):
    c = _client(env)
    _login(c)
    bid, path = fake_backup(env, SQL.encode())
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(bytes(data))
    r = _sql_link(c, bid)
    assert r.status_code == 409 and "SHA-256" in r.get_json()["error"]
    os.remove(path)
    r = _sql_link(c, bid)
    assert r.status_code == 409 and "não está neste servidor" in r.get_json()["error"]
    bid, _ = fake_backup(env, SQL.encode(), key=os.urandom(32))   # cópia de outra instalação
    r = _sql_link(c, bid)
    assert r.status_code == 409 and "outra chave mestra" in r.get_json()["error"]
    assert _sql_link(c, "bk_nao_existe").status_code == 404
