"""Interface web (API JSON + página única) do Sentinela."""

import os
import shutil
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from werkzeug.security import check_password_hash
from io import BytesIO

from . import (__version__, crypto, destinations, dumpers, engine, notify, replication,
               settings, storage)

STATIC = Path(__file__).parent / "static"

# Proteção simples contra força bruta no login: 5 falhas por IP => 60s de bloqueio.
_fails = {}
MAX_FAILS, LOCK_SECONDS = 5, 60


def create_app():
    storage.init()
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    app.secret_key = crypto.derive(engine.key(), "sentinela/flask-session")
    if os.environ.get("SENTINELA_HTTPS") == "1":
        # Atrás de um proxy HTTPS: usa o IP real do cliente (bloqueio de login por IP).
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("SENTINELA_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=64 * 1024,
    )

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("user"):
                return jsonify(error="Sessão expirada. Entre novamente."), 401
            return fn(*a, **kw)
        return wrapper

    def body():
        return request.get_json(silent=True) or {}

    @app.errorhandler(ValueError)
    def _value_error(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(engine.Busy)
    def _busy(e):
        return jsonify(error=str(e)), 409

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------------ páginas

    @app.get("/")
    def index():
        return send_file(STATIC / "index.html")

    # --------------------------------------------------------------- autenticação

    @app.post("/api/login")
    def login():
        ip = request.remote_addr or "?"
        n, until = _fails.get(ip, (0, 0))
        if until > time.time():
            return jsonify(error=f"Muitas tentativas. Aguarde {int(until - time.time())}s."), 429
        data = body()
        user = storage.get_user(str(data.get("username", "")).strip())
        if not user or not check_password_hash(user["password_hash"], str(data.get("password", ""))):
            n += 1
            _fails[ip] = (0, time.time() + LOCK_SECONDS) if n >= MAX_FAILS else (n, 0)
            engine.log.info("Falha de login para '%s' a partir de %s", data.get("username"), ip)
            return jsonify(error="Usuário ou senha incorretos"), 401
        _fails.pop(ip, None)
        session.clear()
        session.permanent = True
        session["user"] = user["username"]
        engine.log.info("Login de '%s' a partir de %s", user["username"], ip)
        return jsonify(user=user["username"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        return jsonify(user=session.get("user"))

    # ------------------------------------------------------------------- estado

    @app.get("/api/state")
    @login_required
    def state():
        policy = engine.get_policy()
        conn = engine.get_connection()
        visible = storage.rows(
            "SELECT * FROM backups WHERE deleted_at IS NULL ORDER BY created_at DESC")
        ok = [b for b in visible if b["status"] == "success"]
        failed = [b for b in visible if b["status"] == "error"]
        finished = [b for b in visible if b["status"] != "running"]
        interval = engine.interval_days(policy)
        expected = max(1, -(-policy["retention_days"] // interval))  # teto
        disk = None
        try:
            du = shutil.disk_usage(policy["directory"])
            disk = {"total": du.total, "free": du.free}
        except OSError:
            pass
        nxt = engine.next_run_at()
        history = storage.rows(
            "SELECT id, created_at, trigger, status, size, raw_size, duration FROM backups "
            "WHERE status != 'running' ORDER BY created_at DESC LIMIT 14")[::-1]
        return jsonify(
            user=session["user"],
            version=__version__,
            policy=policy,
            connection=_public_conn(conn),
            conn_status=storage.get_setting("last_conn_test"),
            active=engine.connection_ready(conn),
            running=engine.is_busy(),
            next_run_at=storage.iso(nxt) if nxt else None,
            last_backup=_pub(finished[0]) if finished else None,
            failures={"count": len(failed), "last": _pub(failed[0]) if failed else None},
            recent=[_pub(b) for b in visible[:5]],
            storage={"copies": len(ok), "expected": expected,
                     "bytes": sum(b["size"] or 0 for b in ok), "disk": disk,
                     "directory": policy["directory"]},
            key_path=str(settings.KEY_PATH),
            current=_current_view(),
            chart=history,
            rule321=replication.rule_321(),
            destinations=replication.dest_status(),
            notify_channels=notify.public(notify.get_config())["active"],
            key_id=engine.key_id(),
            key_exported_at=storage.get_setting("key_exported_at"),
            health=_health(policy, conn, ok, disk, interval),
            limits={"retention": [settings.RETENTION_MIN, settings.RETENTION_MAX],
                    "interval": [settings.INTERVAL_MIN, settings.INTERVAL_MAX]},
        )

    # ------------------------------------------------------------------ política

    @app.put("/api/policy")
    @login_required
    def put_policy():
        return jsonify(policy=engine.save_policy(body()))

    # ------------------------------------------------------------------- conexão

    @app.put("/api/connection")
    @login_required
    def put_connection():
        return jsonify(connection=_public_conn(engine.save_connection(body())))

    @app.post("/api/connection/test")
    @login_required
    def test_connection():
        try:
            version, host_key = engine.test_connection(body())
        except (RuntimeError, dumpers.ToolNotFound) as e:
            return jsonify(ok=False, error=str(e)), 200
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            return jsonify(ok=False, error=f"{type(e).__name__}: {e}"), 200
        return jsonify(ok=True, version=engine.short_version(version), ssh_host_key=host_key)

    # ------------------------------------------------------------------- backups

    @app.get("/api/backups")
    @login_required
    def list_backups():
        f = request.args.get("filter", "all")
        sql = "SELECT * FROM backups WHERE deleted_at IS NULL"
        args = []
        if f == "auto":
            sql += " AND trigger='auto'"
        elif f == "manual":
            sql += " AND trigger IN ('manual','pre-restore')"
        elif f == "error":
            sql += " AND status='error'"
        sql += " ORDER BY created_at DESC"
        ext = {r["backup_id"]: r["n"] for r in storage.rows(
            "SELECT backup_id, COUNT(*) n FROM replicas WHERE status='success' GROUP BY backup_id")}
        return jsonify(backups=[{**_pub(b), "ext": ext.get(b["id"], 0)}
                                for b in storage.rows(sql, args)])

    @app.post("/api/backups")
    @login_required
    def run_backup():
        bid = engine.start_backup("manual")
        return jsonify(id=bid), 202

    @app.get("/api/backups/<bid>")
    @login_required
    def get_backup(bid):
        b = engine.get_backup(bid)
        if not b:
            return jsonify(error="Cópia não encontrada"), 404
        lines = storage.rows("SELECT id, ts, level, message FROM log_lines WHERE execution_id=? "
                             "ORDER BY id", (b["execution_id"],))
        related = storage.rows(
            "SELECT id, kind, started_at, status FROM executions WHERE backup_id=? AND kind!='backup' "
            "ORDER BY id DESC LIMIT 10", (bid,))
        reps = []
        dests = {d["id"]: d for d in replication.get_destinations()}
        for r in replication.replicas_of(bid):
            d = dests.get(r["dest_id"])
            r["dest_type"] = d["type"] if d else None
            r["dest_type_label"] = destinations.TYPES.get(d["type"]) if d else "destino removido"
            r["dest_target"] = destinations.describe(d) if d else ""
            reps.append(r)
        return jsonify(backup=_pub(b), logs=lines, executions=related, replicas=reps)

    @app.post("/api/backups/<bid>/verify")
    @login_required
    def verify(bid):
        ok, err = engine.verify_backup(bid)
        return jsonify(ok=ok, error=err)

    @app.post("/api/backups/<bid>/restore")
    @login_required
    def restore(bid):
        exec_id = engine.start_restore(bid)
        return jsonify(execution=exec_id), 202

    @app.delete("/api/backups/<bid>")
    @login_required
    def delete(bid):
        engine.delete_backup(bid)
        return jsonify(ok=True)

    @app.get("/api/backups/<bid>/download")
    @login_required
    def download(bid):
        b = engine.get_backup(bid)
        if not b or b["status"] != "success" or b["deleted_at"]:
            return jsonify(error="Arquivo indisponível"), 404
        if not b["path"] or not os.path.exists(b["path"]):
            return jsonify(error="A cópia não está neste servidor. Use \"Trazer para o servidor\" "
                                 "para buscá-la num destino externo."), 404
        engine.log.info("Download da cópia %s por '%s'", bid, session["user"])
        return send_file(b["path"], as_attachment=True, download_name=os.path.basename(b["path"]),
                         mimetype="application/octet-stream")

    @app.post("/api/backups/<bid>/fetch")
    @login_required
    def fetch(bid):
        return jsonify(execution=replication.start_fetch(bid)), 202

    # ------------------------------------------------------- cópias externas (3-2-1)

    @app.get("/api/destinations")
    @login_required
    def list_destinations():
        return jsonify(destinations=replication.dest_status(), rule321=replication.rule_321(),
                       types=destinations.TYPES, pending=len(replication.pending(manual=True)))

    @app.post("/api/destinations")
    @login_required
    def create_destination():
        data = body()
        data.pop("id", None)
        d = replication.save_destination(data)
        return jsonify(destination=replication.public(d)), 201

    @app.put("/api/destinations/<did>")
    @login_required
    def update_destination(did):
        d = replication.save_destination({**body(), "id": did})
        return jsonify(destination=replication.public(d))

    @app.delete("/api/destinations/<did>")
    @login_required
    def remove_destination(did):
        replication.delete_destination(did)
        return jsonify(ok=True)

    @app.post("/api/destinations/test")
    @login_required
    def test_destination():
        try:
            summary, fp = replication.test_destination(body())
        except destinations.DestinationError as e:
            return jsonify(ok=False, error=str(e))
        except ValueError:
            raise
        except Exception as e:
            return jsonify(ok=False, error=f"{type(e).__name__}: {e}")
        return jsonify(ok=True, summary=summary, host_key=fp)

    @app.post("/api/destinations/sync")
    @login_required
    def sync_destinations():
        eid = replication.start_sync("manual", dest_id=body().get("id"))
        return jsonify(execution=eid), 202 if eid else 200

    @app.post("/api/destinations/<did>/import")
    @login_required
    def import_destination(did):
        try:
            return jsonify(replication.import_from(did))
        except destinations.DestinationError as e:
            return jsonify(error=str(e)), 502

    # -------------------------------------------------------------------- avisos

    @app.get("/api/notifications")
    @login_required
    def get_notifications():
        hist = storage.rows("SELECT id, ts, event, channel, title, ok, error, attempts "
                            "FROM notifications ORDER BY id DESC LIMIT 30")
        return jsonify(config=notify.public(notify.get_config()), history=hist,
                       events=notify.EVENTS, channels=notify.CHANNELS)

    @app.put("/api/notifications")
    @login_required
    def put_notifications():
        return jsonify(config=notify.public(notify.save(body(), engine.key())))

    @app.post("/api/notifications/test")
    @login_required
    def test_notifications():
        return jsonify(results=notify.send_test(body(), engine.key()))

    # ------------------------------------------------------------- chave mestra

    @app.post("/api/key/export")
    @login_required
    def export_key():
        user = storage.get_user(session["user"])
        if not user or not check_password_hash(user["password_hash"], str(body().get("password", ""))):
            return jsonify(error="Senha incorreta"), 403
        storage.set_setting("key_exported_at", storage.iso(storage.now()))
        engine.log.info("Chave mestra exportada por '%s'", session["user"])
        return send_file(BytesIO(engine.key()), as_attachment=True,
                         download_name=f"sentinela-{engine.key_id()}.key",
                         mimetype="application/octet-stream")

    # ---------------------------------------------------------------------- logs

    @app.get("/api/executions/<int:eid>")
    @login_required
    def get_execution(eid):
        e = storage.row("SELECT * FROM executions WHERE id=?", (eid,))
        if not e:
            return jsonify(error="Execução não encontrada"), 404
        e["lines"] = storage.rows("SELECT id, ts, level, message FROM log_lines "
                                  "WHERE execution_id=? ORDER BY id", (eid,))
        return jsonify(execution=e)

    @app.get("/api/logs")
    @login_required
    def logs():
        limit = min(int(request.args.get("limit", 20)), 100)
        execs = storage.rows("SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,))
        for e in execs:
            e["lines"] = storage.rows(
                "SELECT id, ts, level, message FROM log_lines WHERE execution_id=? ORDER BY id",
                (e["id"],))
        last = storage.row("SELECT MAX(id) AS m FROM log_lines")["m"] or 0
        return jsonify(executions=execs, last_id=last, running=engine.is_busy())

    @app.get("/api/logs/tail")
    @login_required
    def logs_tail():
        """Linhas novas desde ``since`` (para o terminal ao vivo, estilo tail -f)."""
        since = int(request.args.get("since", 0))
        lines = storage.rows(
            "SELECT id, execution_id, ts, level, message FROM log_lines WHERE id > ? "
            "ORDER BY id LIMIT 2000", (since,))
        ids = sorted({ln["execution_id"] for ln in lines})
        execs = storage.rows(
            f"SELECT * FROM executions WHERE id IN ({','.join('?' * len(ids))}) "
            "OR status = 'running'", ids) if ids else \
            storage.rows("SELECT * FROM executions WHERE status = 'running'")
        last = lines[-1]["id"] if lines else since
        return jsonify(lines=lines, executions=execs, last_id=last, running=engine.is_busy(),
                       current=_current_view())

    @app.get("/api/logs/download")
    @login_required
    def download_logs():
        if not settings.MAIN_LOG.exists():
            return jsonify(error="Nenhum log gravado ainda"), 404
        return send_file(settings.MAIN_LOG, as_attachment=True, download_name="sentinela.log",
                         mimetype="text/plain")

    return app


def _current_view():
    cur = engine.current()
    if not cur:
        return None
    started = cur.get("started_at")
    if started:
        cur["elapsed"] = (storage.now() - datetime.fromisoformat(started)).total_seconds()
    return cur


def _health(policy, conn, ok, disk, interval):
    """Checklist de saúde da proteção exibido no painel."""
    items = []

    def add(state, title, detail):
        items.append({"state": state, "title": title, "detail": detail})

    last_ok = ok[0] if ok else None
    if not engine.connection_ready(conn):
        add("warn", "Conexão não configurada", "Configure o banco para ativar os backups automáticos.")
    elif not last_ok:
        add("warn", "Nenhuma cópia válida ainda", "Faça o primeiro backup para começar a proteção.")
    else:
        age = (storage.now() - datetime.fromisoformat(last_ok["created_at"])).total_seconds() / 86400
        if age <= interval + 1:
            add("ok", "Cópia recente disponível", f"Último backup válido: {last_ok['id']}.")
        else:
            add("err", "Backups atrasados",
                f"A última cópia válida tem {int(age)} dias; o agendamento é a cada {interval} dia(s).")
        if last_ok.get("verify_ok"):
            add("ok", "Integridade verificada", "A cópia mais recente foi lida e conferida por completo.")
        else:
            add("warn", "Integridade não confirmada", "Use \"Verificar integridade\" na cópia mais recente.")
    pre = storage.get_setting("last_preflight") or {}
    if pre.get("warnings"):
        add("warn", "Permissões do usuário de backup", pre["warnings"][0])
    add("ok" if policy["encryption"] else "err", "Criptografia AES-256",
        "Cópias ilegíveis sem a chave mestra." if policy["encryption"]
        else "Desativada: qualquer pessoa com acesso à pasta lê os dados.")
    add("ok" if policy["compression"] else "warn", "Compressão gzip",
        "Economiza espaço em disco." if policy["compression"] else "Desativada: as cópias ocupam mais espaço.")
    ssh = conn.get("ssh") or {}
    if ssh.get("enabled"):
        add("ok" if ssh.get("host_key") else "warn", "Túnel SSH",
            "Chave do servidor registrada e verificada a cada conexão." if ssh.get("host_key")
            else "A chave do servidor será registrada na primeira conexão.")
    if disk:
        avg = (sum(b["size"] or 0 for b in ok) / len(ok)) if ok else 0
        free_ok = not avg or disk["free"] > avg * 5
        add("ok" if free_ok else "warn", "Espaço em disco",
            "Espaço livre suficiente para as próximas cópias." if free_ok
            else "Pouco espaço livre no diretório de backup.")
    r = replication.rule_321()
    if r["destinations"] == 0:
        add("warn", "Regra 3-2-1", "Nenhum destino externo: todas as cópias estão num só lugar. "
            "Adicione um disco externo e um destino fora do local em Cópias externas.")
    elif r["ok"]:
        add("ok", "Regra 3-2-1", f"{r['copies']} cópias · {r['media']} mídias · "
            f"{r['offsite']} fora do local.")
    elif r["backup_id"]:
        miss = []
        if r["copies"] < 3:
            miss.append(f"{3 - r['copies']} cópia(s)")
        if r["media"] < 2:
            miss.append("uma segunda mídia (outro disco)")
        if r["offsite"] < 1:
            miss.append("uma cópia fora do local")
        add("warn", "Regra 3-2-1", "Falta: " + ", ".join(miss) + ".")
    failing = [d for d in replication.dest_status()
               if d.get("enabled") and d["last"] and d["last"]["status"] == "error"]
    for d in failing[:2]:
        add("err", f"Cópia externa falhando · {d['name']}", d["last"]["error"] or "erro desconhecido")
    channels = notify.public(notify.get_config())["active"]
    add("ok" if channels else "warn", "Avisos de falha",
        ("Ativos por " + ", ".join(notify.CHANNELS[c] for c in channels) + ".") if channels
        else "Nenhum canal configurado: uma falha à meia-noite só aparece no painel.")
    exported = storage.get_setting("key_exported_at")
    if policy["encryption"] or exported:
        add("ok" if exported else "warn", "Chave mestra fora do servidor",
            f"Exportada em {datetime.fromisoformat(exported):%d/%m/%Y}." if exported
            else "Exporte a chave e guarde fora do servidor: sem ela, nenhuma cópia "
                 "(nem as externas) pode ser lida.")
    return items


def _public_conn(c):
    out = {k: v for k, v in c.items() if k not in ("password_sealed", "password", "ssh")}
    out["has_password"] = bool(c.get("password_sealed"))
    ssh = c.get("ssh") or {}
    out["ssh"] = {
        "enabled": bool(ssh.get("enabled")),
        "host": ssh.get("host", ""),
        "port": ssh.get("port", "22"),
        "user": ssh.get("user", ""),
        "auth": ssh.get("auth", "password"),
        "has_password": bool(ssh.get("password_sealed")),
        "has_private_key": bool(ssh.get("private_key_sealed")),
        "has_passphrase": bool(ssh.get("key_passphrase_sealed")),
        "host_key": (ssh.get("host_key") or {}).get("fingerprint"),
    }
    out["sgbd_label"] = dumpers.SGBD_LABEL.get(c.get("sgbd"), c.get("sgbd"))
    return out


def _pub(b):
    return {
        "id": b["id"],
        "created_at": b["created_at"],
        "finished_at": b["finished_at"],
        "trigger": b["trigger"],
        "sgbd": b["sgbd"],
        "sgbd_label": dumpers.SGBD_LABEL.get(b["sgbd"], b["sgbd"]),
        "dbname": b["dbname"],
        "status": b["status"],
        "size": b["size"],
        "raw_size": b["raw_size"],
        "duration": b["duration"],
        "error": b["error"],
        "path": b["path"],
        "compressed": bool(b["compressed"]),
        "encrypted": bool(b["encrypted"]),
        "sha256": b["sha256"],
        "verified_at": b["verified_at"],
        "verify_ok": None if b["verify_ok"] is None else bool(b["verify_ok"]),
        "origin": b.get("origin"),
        "key_id": b.get("key_id"),
        "local": bool(b["path"]) and os.path.exists(b["path"]),
    }
