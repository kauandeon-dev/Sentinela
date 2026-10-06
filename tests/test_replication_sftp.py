"""Cópias externas via SFTP contra um servidor remoto REAL (tests/remote/setup.sh).

Usuário "cofre" (senha CofreSftp#1 ou a chave ed25519 de teste) no servidor
10.77.0.2; /tmp/sentinela-remoto/cheio é um volume de 256 KB (disco cheio).
"""

import hashlib
import os
import subprocess
import threading
import time

import pytest

from conftest import PG, needs_pg
from test_ssh_remote import KEYS, NS, REMOTE, _remote_available

pytestmark = pytest.mark.skipif(not _remote_available(),
                                reason="servidor remoto de teste indisponível (tests/remote/setup.sh)")

FULL = "/tmp/sentinela-remoto/cheio"


def sftp(path, **kw):
    return {"type": "sftp", "name": "Servidor remoto", "host": REMOTE, "port": "22", "user": "cofre",
            "auth": "password", "password": "CofreSftp#1", "path": path, **kw}


@pytest.fixture()
def remote_dir():
    """Pasta exclusiva do teste na home do usuário cofre (limpa no fim)."""
    name = f"sentinela-teste-{os.getpid()}-{time.time_ns()}"
    yield name
    subprocess.run(["rm", "-rf", f"/home/cofre/{name}"])


def _lines(env, eid):
    return [r["level"] + " " + r["message"] for r in env["storage"].rows(
        "SELECT level, message FROM log_lines WHERE execution_id=? ORDER BY id", (eid,))]


def _setup(env, dest):
    from sentinela import replication
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    e.save_connection(PG)
    return e, replication, replication.save_destination(dest)


def _rep(env, bid, did):
    return env["storage"].row("SELECT * FROM replicas WHERE backup_id=? AND dest_id=?", (bid, did))


# --------------------------------------------------------------- caminho feliz

@needs_pg
def test_sftp_replica_with_password_and_tofu(env, remote_dir):
    e, rep, d = _setup(env, sftp(remote_dir))
    assert d["host_key"] is None
    bid = e.start_backup("auto", wait=True)
    b = e.get_backup(bid)
    r = _rep(env, bid, d["id"])
    assert r["status"] == "success", r["error"]
    name = os.path.basename(b["path"])
    remote = f"/home/cofre/{remote_dir}/{name}"
    assert r["remote_path"] == remote
    data = open(remote, "rb").read()
    assert hashlib.sha256(data).hexdigest() == b["sha256"]
    st = os.stat(f"/home/cofre/{remote_dir}")
    assert oct(st.st_mode & 0o777) == "0o700"  # pasta criada só para o usuário
    # TOFU: a chave do servidor foi registrada na 1ª conexão
    fp = rep.get_destination(d["id"])["host_key"]["fingerprint"]
    assert fp.startswith("SHA256:")
    assert rep.rule_321()["offsite"] == 1


@needs_pg
def test_sftp_with_private_key(env, remote_dir):
    key = open(f"{KEYS}/ed25519").read()
    e, rep, d = _setup(env, sftp(remote_dir, auth="key", private_key=key, password=""))
    bid = e.start_backup("auto", wait=True)
    assert _rep(env, bid, d["id"])["status"] == "success"


@needs_pg
def test_restore_from_sftp_when_local_lost(env, remote_dir):
    e, rep, d = _setup(env, sftp(remote_dir))
    bid = e.start_backup("manual", wait=True)
    os.unlink(e.get_backup(bid)["path"])
    eid = e.start_restore(bid, wait=True)
    log = _lines(env, eid)
    assert env["storage"].row("SELECT status FROM executions WHERE id=?", (eid,))["status"] == "success", log
    assert any("Cópia recuperada de Servidor remoto" in l for l in log)


# ---------------------------------------------------------------- falhas

def _fails_with(env, dest, text):
    e, rep, d = _setup(env, dest)
    bid = e.start_backup("auto", wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "success"  # a cópia local nunca depende do destino
    r = _rep(env, bid, d["id"])
    assert r["status"] == "error" and text in r["error"], r["error"]
    return e, rep, d, bid


@needs_pg
def test_sftp_wrong_password(env, remote_dir):
    _fails_with(env, sftp(remote_dir, password="errada"),
                "Falha na autenticação SSH (usuário, senha ou chave incorretos)")


@needs_pg
def test_sftp_permission_denied(env):
    _fails_with(env, sftp("/root/backups"), "permissão negada no servidor SFTP")


@needs_pg
def test_sftp_remote_disk_full(env):
    e, rep, d, bid = _fails_with(env, sftp(FULL), "disco cheio ou cota excedida")
    assert [f for f in os.listdir(FULL) if f.endswith(".part")] == []  # sem lixo no destino


@needs_pg
def test_sftp_port_closed(env, remote_dir):
    _fails_with(env, sftp(remote_dir, port="2299"), "conexão recusada")


@needs_pg
def test_sftp_host_key_changed(env, remote_dir):
    e, rep, d = _setup(env, sftp(remote_dir))
    e.start_backup("auto", wait=True)
    # simula servidor trocado (ou ataque man-in-the-middle): chave registrada diferente
    from sentinela import storage
    dests = storage.get_setting("destinations")
    dests[0]["host_key"] = {**dests[0]["host_key"], "key": "AAAAC3NzaC1lZDI1NTE5AAAAIOutra",
                            "fingerprint": "SHA256:outra"}
    storage.set_setting("destinations", dests)
    bid = e.start_backup("auto", wait=True)
    r = _rep(env, bid, d["id"])
    assert r["status"] == "error" and "A chave do servidor SSH mudou" in r["error"]
    assert "Cópias externas" in r["error"]


def test_sftp_destination_test_and_unknown_host(env, remote_dir):
    from sentinela import destinations as D
    from sentinela import replication as rep
    env["engine"].save_policy({"directory": str(env["backups"])})
    summary, fp = rep.test_destination(sftp(remote_dir))
    assert summary.startswith("cofre@10.77.0.2:") and fp.startswith("SHA256:")
    assert os.listdir(f"/home/cofre/{remote_dir}") == []
    with pytest.raises(D.DestinationError, match="nome não encontrado"):
        rep.test_destination(sftp(remote_dir, host="servidor-que-nao-existe.invalid"))


# ------------------------------------------ queda da conexão durante o envio

def test_connection_drop_mid_transfer_is_retried(env, remote_dir, tmp_path):
    """Derruba a sessão SFTP no meio do envio de 300 MB: a tentativa falha com
    mensagem clara e a seguinte conclui com o SHA-256 conferido."""
    from sentinela import replication as rep
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    d = rep.save_destination(sftp(remote_dir))
    d = rep.get_destination(d["id"], with_secrets=True)
    big = tmp_path / "grande.sql.gz.enc"
    h = hashlib.sha256()
    with open(big, "wb") as f:
        for _ in range(300):
            chunk = os.urandom(1024 * 1024)
            h.update(chunk)
            f.write(chunk)
    b = {"id": "bk_teste_queda", "path": str(big), "size": big.stat().st_size, "sha256": h.hexdigest(),
         "sgbd": "postgres", "dbname": "x", "trigger": "manual", "created_at": "2026-01-01 00:00:00",
         "finished_at": "2026-01-01 00:00:01", "raw_size": 1, "compressed": 1, "encrypted": 1,
         "key_id": e.key_id()}
    log = []

    def killer():
        # espera o arquivo começar a chegar e derruba a sessão do usuário cofre
        target = f"/home/cofre/{remote_dir}/grande.sql.gz.enc.part"
        for _ in range(400):
            if os.path.exists(target) and os.path.getsize(target) > 20 * 1024 * 1024:
                subprocess.run(["ip", "netns", "exec", NS, "pkill", "-KILL", "-u", "cofre"])
                return
            time.sleep(0.02)
    t = threading.Thread(target=killer)
    t.start()
    ok, err = rep.send(lambda lvl, msg: log.append(f"{lvl} {msg}"), b, d, attempts=3)
    t.join()
    assert ok, log
    assert any("Tentativa 1/3" in l and ("caiu" in l or "Falha" in l) for l in log), log
    data_sha = hashlib.sha256(open(f"/home/cofre/{remote_dir}/grande.sql.gz.enc", "rb").read()).hexdigest()
    assert data_sha == b["sha256"]
    assert not os.path.exists(f"/home/cofre/{remote_dir}/grande.sql.gz.enc.part")
