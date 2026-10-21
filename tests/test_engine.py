import os
import subprocess
import sys
from datetime import timedelta

import pytest

from conftest import MARIA, MARIADB, PG, PSQL, needs_maria, needs_pg


def _configure(env, conn, **policy):
    e = env["engine"]
    e.save_connection(conn)
    e.save_policy({"directory": str(env["backups"]), **policy})
    return e


def _psql(sql):
    return subprocess.run(
        [PSQL, "-h", "localhost", "-U", "backup_user", "-d", "loja_producao", "-w", "-tAc", sql],
        env={**os.environ, "PGPASSWORD": "senha123"}, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _maria(sql):
    return subprocess.run(
        [MARIADB, "-h", "127.0.0.1", "--protocol=TCP", "-u", "backup_user", '-ps3nh@"x',
         "-N", "-B", "loja_producao", "-e", sql],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _lines(env, b):
    return [r["message"] for r in env["storage"].rows(
        "SELECT message FROM log_lines WHERE execution_id=? ORDER BY id", (b["execution_id"],))]


# ------------------------------------------------------------------ política

def test_policy_limits(env):
    e = env["engine"]
    p = e.save_policy({"retention_days": 50, "interval_days": 0, "directory": str(env["backups"])})
    assert p["retention_days"] == 10
    assert p["interval_days"] == 1


def test_directory_must_be_isolated(env):
    e = env["engine"]
    with pytest.raises(ValueError):
        e.save_policy({"directory": str(env["home"] / "bk")})
    with pytest.raises(ValueError):
        e.save_policy({"directory": "relativo/bk"})


def test_password_is_sealed(env):
    e = env["engine"]
    e.save_connection(PG)
    raw = env["storage"].get_setting("connection")
    assert "password" not in raw
    assert "senha123" not in str(raw)
    assert e.get_connection(with_password=True)["password"] == "senha123"


def test_schedule_next_midnight(env):
    e = env["engine"]
    from datetime import datetime
    base = datetime(2026, 7, 8, 14, 30)
    assert e.schedule_next(base) == datetime(2026, 7, 9, 0, 0)
    assert e.schedule_next(base, 3) == datetime(2026, 7, 11, 0, 0)


# ------------------------------------------------------------ backup completo

@needs_pg
@pytest.mark.parametrize("enc,comp", [(True, True), (False, True), (True, False), (False, False)])
def test_pg_backup_and_verify(env, enc, comp):
    e = _configure(env, PG, encryption=enc, compression=comp)
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "success", b["error"]
    assert os.path.exists(b["path"])
    assert b["path"].endswith(".sql" + (".gz" if comp else "") + (".enc" if enc else ""))
    if os.name != "nt":  # no Windows a proteção é por ACL, não por modo
        assert oct(os.stat(b["path"]).st_mode & 0o777) == "0o600"
    if comp:
        assert b["size"] < b["raw_size"]
    content = open(b["path"], "rb").read()
    assert (b"Produto 49999" in content) == (not enc and not comp)
    ok, err = e.verify_backup(bid)
    assert ok, err
    msgs = _lines(env, b)
    assert any("Dump gerado com sucesso" in m for m in msgs)
    assert any("Integridade verificada" in m for m in msgs)


@needs_pg
def test_tampered_backup_fails_verification(env):
    e = _configure(env, PG)
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    data = bytearray(open(b["path"], "rb").read())
    data[len(data) // 2] ^= 0xFF
    open(b["path"], "wb").write(data)
    ok, err = e.verify_backup(bid)
    assert not ok
    assert "SHA-256" in err


@needs_pg
def test_pg_restore(env):
    e = _configure(env, PG)
    before = _psql("SELECT count(*) FROM produtos")
    bid = e.start_backup("manual", wait=True)
    _psql("DELETE FROM produtos WHERE id > 100")
    _psql("CREATE TABLE lixo(x int)")
    assert _psql("SELECT count(*) FROM produtos") == "100"
    e.start_restore(bid, wait=True)
    ex = env["storage"].row("SELECT * FROM executions WHERE kind='restore' ORDER BY id DESC")
    assert ex["status"] == "success"
    assert _psql("SELECT count(*) FROM produtos") == before
    # cópia pré-restauração foi criada
    pre = env["storage"].row("SELECT * FROM backups WHERE trigger='pre-restore'")
    assert pre and pre["status"] == "success"
    _psql("DROP TABLE IF EXISTS lixo")


@needs_pg
def test_connection_failure_is_logged(env):
    e = _configure(env, {**PG, "port": "5999"})
    bid = e.start_backup("auto", wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "error"
    assert "conexão" in b["error"].lower()
    assert not list(env["backups"].glob("*"))
    msgs = _lines(env, b)
    assert msgs[-1] == "Backup abortado — nenhuma cópia foi criada"


@needs_pg
def test_wrong_password(env):
    e = _configure(env, {**PG, "password": "errada"})
    with pytest.raises(RuntimeError):
        e.test_connection()


@needs_maria
def test_mariadb_backup_restore(env):
    e = _configure(env, MARIA)
    assert "MariaDB" in e.test_connection()[0]
    bid = e.start_backup("manual", wait=True)
    b = e.get_backup(bid)
    assert b["status"] == "success", b["error"]
    _maria("DELETE FROM clientes")
    assert _maria("SELECT count(*) FROM clientes") == "0"
    e.start_restore(bid, wait=True)
    assert _maria("SELECT count(*) FROM clientes") == "2"
    assert "São Lourenço do Oeste" in _maria("SELECT cidade FROM clientes WHERE id=1")


# ------------------------------------------------------------------- retenção

@needs_pg
def test_retention(env):
    e = _configure(env, PG, retention_days=3)
    st = env["storage"]
    ids = [e.start_backup("auto", wait=True) for _ in range(3)]
    now = st.now()
    # envelhece artificialmente as cópias
    st.execute("UPDATE backups SET created_at=? WHERE id=?", (st.iso(now - timedelta(days=10)), ids[0]))
    st.execute("UPDATE backups SET created_at=? WHERE id=?", (st.iso(now - timedelta(days=5)), ids[1]))
    removed = e.apply_retention()
    assert removed == 2
    assert not os.path.exists(e.get_backup(ids[0])["path"])
    assert e.get_backup(ids[2])["deleted_at"] is None


@needs_pg
def test_retention_keeps_newest_valid(env):
    e = _configure(env, PG, retention_days=1)
    st = env["storage"]
    bid = e.start_backup("auto", wait=True)
    st.execute("UPDATE backups SET created_at=? WHERE id=?",
               (st.iso(st.now() - timedelta(days=30)), bid))
    assert e.apply_retention() == 0
    assert os.path.exists(e.get_backup(bid)["path"])


@needs_pg
def test_decrypt_cli(env, tmp_path):
    e = _configure(env, PG)
    b = e.get_backup(e.start_backup("manual", wait=True))
    out = tmp_path / "rec.sql"
    subprocess.run([sys.executable, "-m", "sentinela", "decrypt", b["path"], "-o", str(out)],
                   check=True, cwd=os.path.dirname(os.path.dirname(__file__)),
                   env={**os.environ})
    assert b"PostgreSQL database dump complete" in out.read_bytes()


def test_mariadb_preflight_without_mysql_proc_table(env, monkeypatch):
    """Servidor MySQL 8 (sem mysql.proc): nada de alarme falso de permissão."""
    from sentinela import dumpers
    a = dumpers.MariaDBAdapter(MARIA)

    def fake_query(sql):
        raise RuntimeError("ERROR 1146 (42S02): Table 'mysql.proc' doesn't exist")
    monkeypatch.setattr(a, "query", fake_query)
    assert a.preflight() == ([], {})

    def denied(sql):
        raise RuntimeError("ERROR 1142 (42000): SELECT command denied to user")
    monkeypatch.setattr(a, "query", denied)
    warns, expected = a.preflight()
    assert expected == {} and "mysql.proc" in warns[0]


def test_mysqldump_8_gets_column_statistics_off(env, monkeypatch, tmp_path):
    """mysqldump do MySQL 8 contra MariaDB falha em COLUMN_STATISTICS: o Sentinela
    desliga essa consulta; mariadb-dump não recebe a opção."""
    from sentinela import dumpers
    versions = {"/x/mysqldump": "mysqldump  Ver 8.0.39 for Win64 on x86_64 (MySQL Community Server - GPL)",
                "/x/mariadb-dump": "mariadb-dump  Ver 10.19 Distrib 10.11.8-MariaDB, for Linux"}
    monkeypatch.setattr(dumpers, "_tool_versions", dict(versions))
    for tool, expected in (("/x/mysqldump", True), ("/x/mariadb-dump", False)):
        monkeypatch.setattr(dumpers, "_which", lambda *a, _t=tool, **k: _t)
        with dumpers.MariaDBAdapter(MARIA).dump_cmd() as (cmd, _):
            assert ("--column-statistics=0" in cmd) is expected
            assert cmd[-1] == "loja_producao"


def test_which_prefers_first_name_over_path_fallback(env, monkeypatch, tmp_path):
    """Com o MySQL no PATH e o MariaDB instalado (Windows), usa o mariadb-dump."""
    from sentinela import compat, dumpers
    monkeypatch.setattr(compat, "IS_WINDOWS", True)
    monkeypatch.setattr(dumpers.shutil, "which",
                        lambda n: "C:/MySQL/bin/mysqldump.exe" if n == "mysqldump" else None)
    monkeypatch.setattr(dumpers, "_windows_candidates",
                        lambda n: ["C:/Program Files/MariaDB 11.4/bin/mariadb-dump.exe"]
                        if n == "mariadb-dump" else [])
    assert dumpers._which("mariadb-dump", "mysqldump").endswith("mariadb-dump.exe")
    monkeypatch.setenv("SENTINELA_MYSQLDUMP", "D:/meu/mysqldump.exe")
    assert dumpers._which("mariadb-dump", "mysqldump", env="SENTINELA_MYSQLDUMP") == "D:/meu/mysqldump.exe"


def test_windows_candidates_pick_newest_version(env, monkeypatch, tmp_path):
    from sentinela import dumpers
    for v in ("9.6", "16", "17", "12"):
        d = tmp_path / "PostgreSQL" / v / "bin"
        d.mkdir(parents=True)
        (d / "pg_dump.exe").write_text("")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    got = dumpers._windows_candidates("pg_dump")
    assert [os.path.basename(os.path.dirname(os.path.dirname(p))) for p in got] == ["17", "16", "12", "9.6"]


def test_key_and_backups_are_written_in_binary_mode(env, tmp_path):
    """No Windows, os.open sem O_BINARY troca \\n por \\r\\n e corrompe a chave e as cópias."""
    from sentinela import compat
    p = tmp_path / "bin.dat"
    data = bytes(range(256)) * 4
    with os.fdopen(compat.open_private(p), "wb") as f:
        f.write(data)
    assert p.read_bytes() == data
    if os.name == "nt":
        assert compat.O_BINARY
    k = env["engine"].key()
    assert len(k) == 32 and (env["home"] / "sentinela.key").read_bytes() == k


def test_lock_is_exclusive_between_handles(env, tmp_path):
    from sentinela import compat
    p = str(tmp_path / "trava")
    a = os.open(p, os.O_CREAT | os.O_RDWR | compat.O_BINARY, 0o600)
    b = os.open(p, os.O_CREAT | os.O_RDWR | compat.O_BINARY, 0o600)
    try:
        compat.lock_nb(a)
        with pytest.raises(OSError):
            compat.lock_nb(b)
        compat.unlock(a)
        compat.lock_nb(b)
        compat.unlock(b)
    finally:
        os.close(a)
        os.close(b)


def test_mariadb_client_gets_auth_plugin_dir(env, tmp_path, monkeypatch):
    """MySQL 8+ usa caching_sha2_password: o cliente MariaDB precisa achar o plugin
    (senão: "Plugin caching_sha2_password could not be loaded")."""
    from sentinela import compat, dumpers
    ext = ".dll" if compat.IS_WINDOWS else ".so"
    # versão portátil: ferramentas/mariadb/{mariadb-dump.exe, plugin/}
    port = tmp_path / "mariadb"
    (port / "plugin").mkdir(parents=True)
    (port / "plugin" / f"caching_sha2_password{ext}").write_text("")
    a = dumpers.MariaDBAdapter({**MARIA, "host": "127.0.0.1"})
    text = a.defaults_text(str(port / "mariadb-dump.exe"))
    assert f'plugin-dir="{(port / "plugin").resolve().as_posix()}"' in text
    # instalação padrão do Windows: bin/ e lib/plugin/
    inst = tmp_path / "MariaDB 11.4"
    (inst / "bin").mkdir(parents=True)
    (inst / "lib" / "plugin").mkdir(parents=True)
    (inst / "lib" / "plugin" / f"caching_sha2_password{ext}").write_text("")
    assert "lib/plugin" in a.defaults_text(str(inst / "bin" / "mariadb.exe"))
    # sem plugin por perto: não força nada (o cliente usa a pasta dele)
    assert "plugin-dir" not in a.defaults_text(str(tmp_path / "outro" / "mariadb"))


def test_tls_verification_relaxed_only_on_loopback(env):
    from sentinela import dumpers
    local = dumpers.MariaDBAdapter({**MARIA, "host": "127.0.0.1"}).defaults_text()
    assert "[client-mariadb]\nssl-verify-server-cert=0" in local
    remote = dumpers.MariaDBAdapter({**MARIA, "host": "db.empresa.com.br"}).defaults_text()
    assert "ssl-verify-server-cert" not in remote


def test_client_messages_decoded_utf8_or_ansi(env):
    from sentinela import dumpers
    msg = "Não foi possível encontrar o módulo especificado"
    assert dumpers.decode_output(msg.encode("utf-8")) == msg
    assert dumpers.decode_output(msg.encode("cp1252")) == msg
    err = "ERROR 1156 (08S01): Plugin caching_sha2_password could not be loaded: x"
    assert "MySQL 8+" in dumpers.hint_for(err)


def test_decrypt_file_without_panel(env, tmp_path):
    """CLI / Descriptografar.bat: .sql ao lado da cópia, chave do chaveiro,
    e nunca deixa SQL pela metade de um arquivo adulterado."""
    from conftest import fake_backup
    import sentinela.crypto as crypto
    e = env["engine"]
    sql = b"-- PostgreSQL database dump\nSELECT 'acentua\xc3\xa7\xc3\xa3o';\n-- PostgreSQL database dump complete\n"
    _, enc = fake_backup(env, sql)
    _, gz = fake_backup(env, sql, encrypted=False)
    _, plain_enc = fake_backup(env, sql, compressed=False)
    for p in (enc, gz, plain_enc):
        out = e.decrypt_file(str(p))
        assert out == str(p).split(".sql")[0] + ".sql" and open(out, "rb").read() == sql
        os.remove(out)

    # cópia de outra instalação: abre depois de importar a chave dela
    other = os.urandom(32)
    _, foreign = fake_backup(env, sql, key=other, dbname="antiga")
    with pytest.raises(crypto.IntegrityError, match="nenhuma chave mestra"):
        e.decrypt_file(str(foreign))
    e.import_key(other)
    assert open(e.decrypt_file(str(foreign)), "rb").read() == sql

    # adulterado: erro e nada gravado (nem .sql nem .part)
    for p, compressed in ((enc, True), (plain_enc, False)):
        data = bytearray(p.read_bytes())
        data[-20] ^= 1
        p.write_bytes(bytes(data))
        with pytest.raises(crypto.IntegrityError):
            e.decrypt_file(str(p), str(tmp_path / "x.sql"))
        assert not list(tmp_path.glob("x.sql*"))
    with pytest.raises(crypto.IntegrityError, match="não é uma cópia"):
        e.decrypt_file(__file__)


def test_decrypt_cli_several_files(env, tmp_path):
    from conftest import fake_backup
    sql = b"-- dump\n"
    _, a = fake_backup(env, sql, dbname="a")
    _, b = fake_backup(env, sql, dbname="b")
    run = dict(cwd=os.path.dirname(os.path.dirname(__file__)), env={**os.environ},
               capture_output=True, text=True)
    r = subprocess.run([sys.executable, "-m", "sentinela", "decrypt", str(a), str(b)], **run)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("SQL recuperado em") == 2
    assert (a.parent / (a.name.split(".sql")[0] + ".sql")).read_bytes() == sql
    r = subprocess.run([sys.executable, "-m", "sentinela", "decrypt", str(a), "-o", "-"], **run)
    assert r.returncode == 0 and r.stdout == sql.decode()
    r = subprocess.run([sys.executable, "-m", "sentinela", "decrypt", str(a), str(b), "-o", "x"], **run)
    assert r.returncode != 0 and "um arquivo" in r.stderr
