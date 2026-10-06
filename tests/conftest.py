import importlib
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isola SENTINELA_HOME e diretório de backup por teste."""
    home = tmp_path / "home"
    backups = tmp_path / "backups"
    monkeypatch.setenv("SENTINELA_HOME", str(home))
    monkeypatch.setenv("SENTINELA_BACKUP_DIR", str(backups))
    import sentinela.settings as s
    importlib.reload(s)
    import sentinela.storage as st
    importlib.reload(st)
    import sentinela.crypto as c
    importlib.reload(c)
    import sentinela.dumpers as d
    importlib.reload(d)
    import sentinela.engine as e
    importlib.reload(e)
    e._key = None
    # sem esperas entre tentativas de envio aos destinos externos
    monkeypatch.setattr(s, "REPLICA_BACKOFF", [0])
    return {"home": home, "backups": backups, "engine": e, "storage": st}


def tool(*names):
    """Acha um cliente do banco como o Sentinela acha (PATH ou, no Windows, as
    pastas de instalação padrão). None se não houver."""
    from sentinela import dumpers
    try:
        return dumpers._which(*names)
    except dumpers.ToolNotFound:
        return None


PSQL = tool("psql")
MARIADB = tool("mariadb", "mysql")


def _pg_available():
    if not tool("pg_dump") or not PSQL:
        return False
    p = subprocess.run([PSQL, "-h", "localhost", "-U", "backup_user", "-d", "loja_producao",
                        "-w", "-tAc", "select 1"], env={**os.environ, "PGPASSWORD": "senha123"},
                       capture_output=True)
    return p.returncode == 0


def _maria_available():
    if not tool("mariadb-dump", "mysqldump") or not MARIADB:
        return False
    p = subprocess.run([MARIADB, "-h", "127.0.0.1", "--protocol=TCP", "-u", "backup_user",
                        "-ps3nh@\"x", "loja_producao", "-e", "select 1"], capture_output=True)
    return p.returncode == 0


PG = {"sgbd": "postgres", "host": "localhost", "port": "5432", "dbname": "loja_producao",
      "user": "backup_user", "password": "senha123"}
MARIA = {"sgbd": "mariadb", "host": "127.0.0.1", "port": "3306", "dbname": "loja_producao",
         "user": "backup_user", "password": 's3nh@"x'}

needs_pg = pytest.mark.skipif(not _pg_available(), reason="PostgreSQL de teste indisponível")
needs_maria = pytest.mark.skipif(not _maria_available(), reason="MariaDB de teste indisponível")


# ------------------------------------------------- serviços falsos para avisos e S3

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class SmtpSink:
    """Servidor SMTP de teste (aiosmtpd) que guarda as mensagens recebidas."""

    def __init__(self, user=None, password=None):
        from aiosmtpd.controller import Controller
        from aiosmtpd.smtp import AuthResult
        self.messages = []
        self.port = free_port()
        sink = self

        class Handler:
            async def handle_DATA(self, server, session, envelope):
                sink.messages.append({"from": envelope.mail_from, "to": envelope.rcpt_tos,
                                      "raw": envelope.original_content or envelope.content})
                return "250 OK"

        def auth(server, session, envelope, mechanism, data):
            ok = user and data.login.decode() == user and data.password.decode() == password
            return AuthResult(success=bool(ok), handled=False)

        kw = {}
        if user:
            kw = dict(authenticator=auth, auth_require_tls=False)
        self.ctl = Controller(Handler(), hostname="127.0.0.1", port=self.port, **kw)

    def start(self):
        self.ctl.start()
        return self

    def stop(self):
        self.ctl.stop()

    def text(self):
        import email
        from email import policy
        out = []
        for m in self.messages:
            msg = email.message_from_bytes(m["raw"], policy=policy.default)
            out.append(str(msg["Subject"]) + "\n" + msg.get_content())
        return out


class HttpMock:
    """API do Telegram e webhooks falsos.

    /bot<TOKEN_BOM>/sendMessage  → ok (chat "000" → 400 chat not found)
    /bot<outro>/sendMessage      → 401
    /hook                        → 200        /hook500 → 500
    """
    TOKEN = "123:TOKEN-BOM"

    def __init__(self):
        self.calls = []
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                mock.calls.append((self.path, body))
                if self.path.startswith("/bot"):
                    token = self.path[4:].split("/")[0]
                    if token != mock.TOKEN:
                        return self._send(401, {"ok": False, "description": "Unauthorized"})
                    if str(body.get("chat_id")) == "000":
                        return self._send(400, {"ok": False, "description": "Bad Request: chat not found"})
                    return self._send(200, {"ok": True, "result": {}})
                if self.path == "/hook500":
                    return self._send(500, {"error": "boom"})
                return self._send(200, {"ok": True})

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()

    def telegram(self):
        return [b for p, b in self.calls if p.startswith("/bot")]

    def hooks(self):
        return [b for p, b in self.calls if p.startswith("/hook")]


@pytest.fixture()
def http_mock(monkeypatch):
    m = HttpMock()
    monkeypatch.setenv("SENTINELA_TELEGRAM_API", m.url)
    import sentinela.settings as s
    monkeypatch.setattr(s, "TELEGRAM_API", m.url)
    yield m
    m.stop()


@pytest.fixture(scope="session")
def s3_server():
    try:
        from moto.server import ThreadedMotoServer
        import boto3  # noqa: F401
    except ImportError:
        pytest.skip("moto/boto3 não instalados")
    port = free_port()
    srv = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    srv.start()
    yield f"http://127.0.0.1:{port}"
    srv.stop()


@pytest.fixture()
def s3(s3_server):
    """Um bucket novo por teste."""
    import uuid
    import boto3
    bucket = "sentinela-" + uuid.uuid4().hex[:10]
    client = boto3.client("s3", endpoint_url=s3_server, region_name="us-east-1",
                          aws_access_key_id="teste", aws_secret_access_key="segredo")
    client.create_bucket(Bucket=bucket)
    return {"endpoint": s3_server, "bucket": bucket, "client": client,
            "dest": {"type": "s3", "name": "Nuvem S3", "endpoint": s3_server, "bucket": bucket,
                     "prefix": "sentinela", "access_key": "teste", "secret_key": "segredo",
                     "region": "us-east-1"}}
