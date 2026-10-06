"""Regra 3-2-1: cópias externas (outro disco e S3) e seus cenários de falha."""

import hashlib
import importlib
import json
import os
import shutil
import subprocess
from datetime import timedelta

import pytest

from conftest import PG, SmtpSink, free_port, needs_pg


def _lines(env, eid):
    return [r["level"] + " " + r["message"] for r in env["storage"].rows(
        "SELECT level, message FROM log_lines WHERE execution_id=? ORDER BY id", (eid,))]


def _setup(env, *dests):
    from sentinela import replication
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    e.save_connection(PG)
    saved = [replication.save_destination(d) for d in dests]
    return e, replication, saved


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _s3_get(s3, key):
    return s3["client"].get_object(Bucket=s3["bucket"], Key="sentinela/" + key)["Body"].read()


def _s3_keys(s3):
    r = s3["client"].list_objects_v2(Bucket=s3["bucket"])
    return sorted(o["Key"] for o in r.get("Contents", []))


def _rep(env, bid, did):
    return env["storage"].row("SELECT * FROM replicas WHERE backup_id=? AND dest_id=?", (bid, did))


# ============================================================ caminho feliz

@needs_pg
def test_backup_is_replicated_verified_and_rule_321_met(env, s3, tmp_path):
    disk = tmp_path / "disco-externo"
    e, rep, (dd, ds) = _setup(env, {"type": "directory", "name": "HD externo", "path": str(disk)},
                              s3["dest"])
    bid = e.start_backup("auto", wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "success"
    name = os.path.basename(b["path"])
    local = open(b["path"], "rb").read()

    # outro disco: cópia idêntica + manifesto + .sha256
    assert open(disk / name, "rb").read() == local
    m = json.loads((disk / (name + ".json")).read_text())
    assert m["backup_id"] == bid and m["sha256"] == b["sha256"] and m["key_id"] == e.key_id()
    assert (disk / (name + ".sha256")).read_text() == f"{b['sha256']}  {name}\n"
    assert subprocess.run(["sha256sum", "-c", name + ".sha256"], cwd=disk,
                          capture_output=True).returncode == 0
    # S3
    assert _sha(_s3_get(s3, name)) == b["sha256"]
    assert _s3_keys(s3) == sorted(f"sentinela/{name}{x}" for x in ("", ".json", ".sha256"))
    # registros
    for d in (dd, ds):
        r = _rep(env, bid, d["id"])
        assert r["status"] == "success" and r["verify_ok"] == 1 and r["sha256"] == b["sha256"]
    log = _lines(env, b["execution_id"])
    assert any("Cópia externa em HD externo conferida (SHA-256 confere)" in l for l in log)
    assert any("Cópia externa em Nuvem S3 conferida" in l for l in log)
    # produção + local + 2 externas; o HD está no mesmo disco (tmp) -> as mídias
    # diferentes são o disco local e o S3
    r = rep.rule_321()
    assert r == {**r, "copies": 4, "media": 2, "offsite": 1, "ok": True}
    assert any("Regra 3-2-1: 4 cópias ✓ · 2 mídias ✓ · 1 fora do local ✓" in l for l in log)
    st = {d["name"]: d for d in rep.dest_status()}
    assert st["HD externo"]["same_device"] is True
    assert st["Nuvem S3"]["copies"] == 1 and st["Nuvem S3"]["missing"] == 0


@needs_pg
def test_rule_321_not_met_without_offsite(env, tmp_path):
    e, rep, _ = _setup(env, {"type": "directory", "path": str(tmp_path / "hd")})
    bid = e.start_backup("auto", wait=True)
    r = rep.rule_321()
    assert r["copies"] == 3 and r["offsite"] == 0 and not r["ok"]
    assert any("WARN Regra 3-2-1" in l for l in _lines(env, e.get_backup(bid)["execution_id"]))


def test_destination_validation(env, tmp_path):
    from sentinela import replication as rep
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    with pytest.raises(ValueError, match="diferente"):
        rep.save_destination({"type": "directory", "path": str(env["backups"])})
    with pytest.raises(ValueError, match="diferente"):
        rep.save_destination({"type": "directory", "path": str(env["backups"] / "sub")})
    with pytest.raises(ValueError, match="isolado"):
        rep.save_destination({"type": "directory", "path": str(env["home"] / "x")})
    with pytest.raises(ValueError, match="bucket"):
        rep.save_destination({"type": "s3", "access_key": "a", "secret_key": "b"})
    with pytest.raises(ValueError, match="chave secreta"):
        rep.save_destination({"type": "s3", "bucket": "x"})
    with pytest.raises(ValueError, match="usuário SFTP"):
        rep.save_destination({"type": "sftp", "host": "h"})
    d = rep.save_destination({"type": "s3", "bucket": "b", "access_key": "AK", "secret_key": "SEGREDO-S3"})
    assert "SEGREDO-S3" not in str(env["storage"].get_setting("destinations"))
    assert rep.public(d)["has_secret_key"] and "secret_key" not in rep.public(d)
    # editar sem informar o segredo mantém o anterior
    rep.save_destination({"id": d["id"], "prefix": "novo"})
    assert rep.get_destination(d["id"], with_secrets=True)["secret_key"] == "SEGREDO-S3"


# ============================================== falha 1: disco externo cheio

@pytest.fixture()
def tiny_disk(tmp_path):
    if os.geteuid() != 0:
        pytest.skip("precisa de root para montar um volume pequeno")
    p = tmp_path / "pendrive"
    p.mkdir()
    subprocess.run(["mount", "-t", "tmpfs", "-o", "size=64k", "tmpfs", str(p)], check=True)
    yield p
    subprocess.run(["umount", "-l", str(p)])


@needs_pg
def test_disk_full_destination_fails_cleanly_and_is_retried(env, s3, tiny_disk):
    smtp = SmtpSink().start()
    try:
        from sentinela import notify
        e, rep, (dd, ds) = _setup(env, {"type": "directory", "name": "Pendrive", "path": str(tiny_disk)},
                                  s3["dest"])
        notify.save({"email": {"enabled": True, "host": "127.0.0.1", "port": str(smtp.port),
                               "security": "none", "recipients": "ti@x.com"}}, e.key())
        bid = e.start_backup("auto", wait=True)
        b = e.get_backup(bid)
        # a cópia local continua válida; o S3 recebeu; o pendrive falhou sem deixar lixo
        assert b["status"] == "success"
        assert _rep(env, bid, ds["id"])["status"] == "success"
        r = _rep(env, bid, dd["id"])
        assert r["status"] == "error" and "disco cheio" in r["error"] and r["attempts"] == 3
        assert os.listdir(tiny_disk) == []
        log = _lines(env, b["execution_id"])
        assert any("Tentativa 1/3 para Pendrive falhou" in l for l in log)
        assert any(l.startswith("ERRO Cópia externa em Pendrive falhou") for l in log)
        ex = env["storage"].row("SELECT status FROM executions WHERE id=?", (b["execution_id"],))
        assert ex["status"] == "success"
        # aviso por e-mail da falha da cópia externa
        assert any("Cópia externa falhou · Pendrive" in t and "disco cheio" in t for t in smtp.text())

        # liberou espaço (volume maior): a retomada automática envia
        subprocess.run(["mount", "-o", "remount,size=64m", str(tiny_disk)], check=True)
        eid = rep.start_sync("auto", wait=True)
        assert eid is not None
        assert _rep(env, bid, dd["id"])["status"] == "success"
        assert rep.start_sync("auto", wait=True) is None  # nada mais pendente
        # dentro do intervalo de silêncio, a mesma falha não gera novo e-mail
        assert sum("Cópia externa falhou" in t for t in smtp.text()) == 1
    finally:
        smtp.stop()


# ========================================= falha 2: bucket inexistente / sem rede

@needs_pg
def test_s3_bucket_missing(env, s3):
    e, rep, (ds,) = _setup(env, {**s3["dest"], "bucket": "nao-existe-" + s3["bucket"][-6:]})
    bid = e.start_backup("auto", wait=True)
    r = _rep(env, bid, ds["id"])
    assert r["status"] == "error" and "o bucket (ou objeto) não existe" in r["error"]


@needs_pg
def test_s3_offline_then_back_online(env, s3):
    port = free_port()
    e, rep, (ds,) = _setup(env, {**s3["dest"], "endpoint": f"http://127.0.0.1:{port}"})
    bid = e.start_backup("auto", wait=True)
    r = _rep(env, bid, ds["id"])
    assert r["status"] == "error" and "não foi possível conectar ao endpoint" in r["error"]
    assert rep.rule_321()["ok"] is False
    # a rede voltou (endpoint correto)
    rep.save_destination({"id": ds["id"], "endpoint": s3["endpoint"]})
    rep.start_sync("auto", wait=True)
    assert _rep(env, bid, ds["id"])["status"] == "success"


def test_test_destination_reports_errors(env, s3):
    from sentinela import destinations as D
    from sentinela import replication as rep
    env["engine"].save_policy({"directory": str(env["backups"])})
    summary, fp = rep.test_destination(s3["dest"])
    assert summary.startswith(f"s3://{s3['bucket']}/sentinela/") and fp is None
    assert _s3_keys(s3) == []  # arquivo de teste removido
    with pytest.raises(D.DestinationError, match="não existe"):
        rep.test_destination({**s3["dest"], "bucket": "inexistente-xyz"})


# ===================================== falha 3: cópia local apagada/corrompida

def _psql(sql):
    return subprocess.run(
        ["psql", "-h", "localhost", "-U", "backup_user", "-d", "loja_producao", "-w", "-tAc", sql],
        env={**os.environ, "PGPASSWORD": "senha123"}, capture_output=True, text=True, check=True,
    ).stdout.strip()


@needs_pg
def test_restore_fetches_external_copy_when_local_missing(env, s3):
    e, rep, (ds,) = _setup(env, s3["dest"])
    before = _psql("SELECT count(*) FROM produtos")
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    os.unlink(b["path"])  # desastre: a cópia local sumiu
    _psql("DELETE FROM produtos WHERE id > 10")
    eid = e.start_restore(bid, wait=True)
    log = _lines(env, eid)
    ex = env["storage"].row("SELECT status FROM executions WHERE id=?", (eid,))
    assert ex["status"] == "success", log
    assert any("Cópia local indisponível" in l for l in log)
    assert any("Cópia recuperada de Nuvem S3 e conferida" in l for l in log)
    assert _psql("SELECT count(*) FROM produtos") == before
    assert os.path.exists(b["path"])  # e a cópia local foi recomposta


@needs_pg
def test_corrupted_copies_are_detected_and_skipped(env, s3, tmp_path):
    disk = tmp_path / "hd"
    e, rep, (dd, ds) = _setup(env, {"type": "directory", "name": "HD", "path": str(disk)}, s3["dest"])
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    name = os.path.basename(b["path"])
    # corrompe a cópia local e a do HD (a preferida para buscar)
    for p in (b["path"], disk / name):
        data = bytearray(open(p, "rb").read())
        data[len(data) // 2] ^= 0xFF
        open(p, "wb").write(data)

    ok, err = e.verify_backup(bid)
    assert not ok
    assert "cópia local" in err and "HD: SHA-256 não confere" in err and "Nuvem S3" not in err
    assert _rep(env, bid, dd["id"])["verify_ok"] == 0
    assert _rep(env, bid, ds["id"])["verify_ok"] == 1

    eid = e.start_restore(bid, wait=True)
    log = _lines(env, eid)
    assert env["storage"].row("SELECT status FROM executions WHERE id=?", (eid,))["status"] == "success", log
    assert any("Não foi possível usar a cópia em HD: a cópia externa está corrompida" in l for l in log)
    assert any("Cópia recuperada de Nuvem S3" in l for l in log)
    ok, err = e.verify_backup(bid)
    assert not ok and "HD" in err  # o HD continua corrompido e segue sendo apontado


@needs_pg
def test_restore_fails_clearly_when_every_copy_is_bad(env, s3):
    e, rep, (ds,) = _setup(env, s3["dest"])
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    os.unlink(b["path"])
    name = os.path.basename(b["path"])
    s3["client"].put_object(Bucket=s3["bucket"], Key="sentinela/" + name, Body=b"lixo")
    eid = e.start_restore(bid, wait=True)
    log = _lines(env, eid)
    assert env["storage"].row("SELECT status FROM executions WHERE id=?", (eid,))["status"] == "error"
    assert any("Nenhuma cópia externa íntegra disponível" in l for l in log)


# ======================================= retenção apaga também as cópias externas

@needs_pg
def test_retention_deletes_external_copies_and_retries_when_offline(env, s3):
    e, rep, (ds,) = _setup(env, s3["dest"])
    e.save_policy({"retention_days": 2})
    st = env["storage"]
    old = e.start_backup("auto", wait=True)
    name = os.path.basename(e.get_backup(old)["path"])
    keep = e.start_backup("auto", wait=True)
    st.execute("UPDATE backups SET created_at=? WHERE id=?", (st.iso(st.now() - timedelta(days=5)), old))

    # destino fora do ar no momento da limpeza: exclusão fica pendente
    real = s3["endpoint"]
    rep.save_destination({"id": ds["id"], "endpoint": f"http://127.0.0.1:{free_port()}"})
    assert e.apply_retention() == 1
    assert _rep(env, old, ds["id"])["status"] == "delete_pending"
    assert f"sentinela/{name}" in _s3_keys(s3)

    rep.save_destination({"id": ds["id"], "endpoint": real})
    rep.start_sync("auto", wait=True)
    assert _rep(env, old, ds["id"])["status"] == "deleted"
    assert not [k for k in _s3_keys(s3) if name in k]
    assert _rep(env, keep, ds["id"])["status"] == "success"  # a recente fica


@needs_pg
def test_manual_delete_removes_external_copies(env, s3):
    e, rep, (ds,) = _setup(env, s3["dest"])
    bid = e.start_backup("manual", wait=True)
    e.delete_backup(bid)
    assert _s3_keys(s3) == []
    assert _rep(env, bid, ds["id"])["status"] == "deleted"


# ============================ recuperação de desastre: servidor novo, outra chave

def _reload_home(monkeypatch, home, backups):
    monkeypatch.setenv("SENTINELA_HOME", str(home))
    monkeypatch.setenv("SENTINELA_BACKUP_DIR", str(backups))
    import sentinela.settings as s
    import sentinela.storage as st
    import sentinela.engine as e
    for m in (s, st):
        importlib.reload(m)
    st._initialized = False
    importlib.reload(e)
    e._key = None
    monkeypatch.setattr(s, "REPLICA_BACKOFF", [0])
    return e, st


@needs_pg
def test_disaster_recovery_import_from_destination(env, s3, tmp_path, monkeypatch):
    from sentinela import replication as rep
    e, _, (ds,) = _setup(env, s3["dest"])
    bid = e.start_backup("manual", wait=True)
    old_key = e.key()
    before = _psql("SELECT count(*) FROM produtos")

    # servidor perdido: instalação nova, chave mestra NOVA, nenhum histórico
    e2, st2 = _reload_home(monkeypatch, tmp_path / "novo-home", tmp_path / "novo-backups")
    e2.save_policy({"directory": str(tmp_path / "novo-backups")})
    e2.save_connection(PG)
    assert e2.key() != old_key
    d2 = rep.save_destination(s3["dest"])
    res = rep.import_from(d2["id"])
    assert res == {"found": 1, "imported": 1, "missing_keys": [e2.crypto.key_id(old_key)]}
    b = e2.get_backup(bid)
    assert b["origin"] == "imported" and b["path"] is None
    assert rep.import_from(d2["id"])["imported"] == 0  # idempotente

    # sem a chave antiga: erro claro
    _psql("DELETE FROM produtos WHERE id > 10")
    eid = e2.start_restore(bid, wait=True)
    log = _lines({"storage": st2}, eid)
    assert any("criptografada com outra chave mestra" in l for l in log), log

    # importa a chave exportada do servidor antigo e restaura
    kid, added = e2.import_key(old_key)
    assert added and e2.has_key(kid)
    eid = e2.start_restore(bid, wait=True)
    log = _lines({"storage": st2}, eid)
    assert st2.row("SELECT status FROM executions WHERE id=?", (eid,))["status"] == "success", log
    assert _psql("SELECT count(*) FROM produtos") == before
    # cópias importadas não são apagadas pela retenção
    st2.execute("UPDATE backups SET created_at=? WHERE id=?",
                (st2.iso(st2.now() - timedelta(days=60)), bid))
    e2.apply_retention()
    assert e2.get_backup(bid)["deleted_at"] is None


def test_import_key_validation(env):
    e = env["engine"]
    with pytest.raises(ValueError, match="32 bytes"):
        e.import_key(b"curta")
    assert e.import_key(e.key()) == (e.key_id(), False)


# ============================================================== CLI

@needs_pg
def test_cli_sync_and_key(env, s3, tmp_path):
    e, replication, _ = _setup(env)
    e.start_backup("manual", wait=True)  # sem destinos
    replication.save_destination(s3["dest"])
    root = os.path.dirname(os.path.dirname(__file__))
    run = lambda *a: subprocess.run(["python3", "-m", "sentinela", *a], cwd=root,  # noqa: E731
                                    capture_output=True, text=True, env={**os.environ})
    r = run("sync")
    assert r.returncode == 0 and "concluída" in r.stdout, r.stdout + r.stderr
    assert len(_s3_keys(s3)) == 3
    assert "Nada pendente" in run("sync").stdout
    out = tmp_path / "chave.key"
    r = run("key", "export", "-o", str(out))
    assert r.returncode == 0 and out.read_bytes() == e.key()
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert run("key", "id").stdout.strip() == e.key_id()
    assert "já é a chave atual" in run("key", "import", str(out)).stdout


@needs_pg
def test_scheduler_housekeeping_resumes_pending_copies(env, s3):
    """A manutenção horária do agendador retoma envios que falharam."""
    from sentinela.scheduler import Scheduler
    e, rep, (ds,) = _setup(env, {**s3["dest"], "endpoint": f"http://127.0.0.1:{free_port()}"})
    bid = e.start_backup("auto", wait=True)
    assert _rep(env, bid, ds["id"])["status"] == "error"
    rep.save_destination({"id": ds["id"], "endpoint": s3["endpoint"]})
    Scheduler().housekeeping()
    assert _rep(env, bid, ds["id"])["status"] == "success"
    assert rep.rule_321()["offsite"] == 1
