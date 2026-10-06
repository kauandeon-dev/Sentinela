"""Avisos de falha: cenários de erro do backup e dos próprios canais de aviso."""

from datetime import timedelta

import pytest

from conftest import PG, HttpMock, SmtpSink, needs_pg

pytest.importorskip("aiosmtpd")


def _lines(env, eid):
    return [r["level"] + " " + r["message"] for r in env["storage"].rows(
        "SELECT level, message FROM log_lines WHERE execution_id=? ORDER BY id", (eid,))]


def _exec_of(env, bid):
    return env["engine"].get_backup(bid)["execution_id"]


def _setup(env, conn=PG, **notif):
    from sentinela import notify
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    e.save_connection(conn)
    notify.save(notif, e.key())
    return e


def _email(port, **kw):
    return {"enabled": True, "host": "127.0.0.1", "port": str(port), "security": "none",
            "sender": "sentinela@empresa.local", "recipients": "ti@empresa.local, dono@empresa.local",
            **kw}


@pytest.fixture()
def smtp():
    s = SmtpSink().start()
    yield s
    s.stop()


# ----------------------------------------------- falha 1: banco fora do ar

@needs_pg
def test_backup_failure_sends_email_telegram_and_webhook(env, smtp, http_mock):
    e = _setup(env, {**PG, "port": "5999"},
               email=_email(smtp.port),
               telegram={"enabled": True, "token": HttpMock.TOKEN, "chat_id": "4242"},
               webhook={"enabled": True, "url": http_mock.url + "/hook", "format": "discord"})
    bid = e.start_backup("auto", wait=True)
    assert e.get_backup(bid)["status"] == "error"

    # e-mail com o erro e a situação da última cópia
    assert len(smtp.messages) == 1
    assert set(smtp.messages[0]["to"]) == {"ti@empresa.local", "dono@empresa.local"}
    txt = smtp.text()[0]
    assert "Backup falhou · loja_producao" in txt
    assert "5999" in txt and "Erro:" in txt
    assert "não existe nenhuma cópia válida" in txt
    # Telegram e Discord
    tg = http_mock.telegram()
    assert len(tg) == 1 and tg[0]["chat_id"] == "4242" and "Backup falhou" in tg[0]["text"]
    hook = http_mock.hooks()
    assert len(hook) == 1 and "Backup falhou" in hook[0]["content"]
    # registrado no log da execução e no histórico de avisos
    log = _lines(env, _exec_of(env, bid))
    assert any(l.startswith("OK Aviso enviado por E-mail para ti@empresa.local") for l in log)
    assert any(l.startswith("OK Aviso enviado por Telegram (chat 4242)") for l in log)
    assert any(l.startswith("OK Aviso enviado por Webhook") for l in log)
    assert env["storage"].row("SELECT COUNT(*) n FROM notifications WHERE ok=1")["n"] == 3


# ------------------------------------- falha 2: servidor de e-mail fora do ar

@needs_pg
def test_smtp_down_is_logged_and_retried_later(env):
    from conftest import free_port
    from sentinela import notify
    port = free_port()
    e = _setup(env, {**PG, "port": "5999"}, email=_email(port))
    bid = e.start_backup("auto", wait=True)
    log = _lines(env, _exec_of(env, bid))
    assert any("Falha ao enviar aviso por E-mail: conexão recusada" in l for l in log), log
    # o backup continua registrado como falha (o aviso não mascara o erro)
    assert log[-1].startswith("WARN Falha ao enviar aviso") or "abortado" in " ".join(log)
    row = env["storage"].row("SELECT * FROM notifications")
    assert row["ok"] == 0 and "conexão recusada" in row["error"]

    # o servidor de e-mail volta: o agendador reenvia
    smtp = SmtpSink()
    smtp.port = port
    from aiosmtpd.controller import Controller
    smtp.ctl = Controller(smtp.ctl.handler, hostname="127.0.0.1", port=port)
    smtp.start()
    try:
        assert notify.retry_failed() == 1
        assert len(smtp.messages) == 1 and "(reenvio)" in smtp.text()[0]
        row = env["storage"].row("SELECT * FROM notifications")
        assert row["ok"] == 1 and row["attempts"] == 2
        assert notify.retry_failed() == 0  # não reenvia de novo
    finally:
        smtp.stop()


# ------------------------------------------- falha 3: senha do SMTP errada

def test_smtp_wrong_password(env):
    from sentinela import notify
    s = SmtpSink(user="sentinela", password="certa").start()
    try:
        cfg = {"email": _email(s.port, user="sentinela", password="errada")}
        r = notify.send_test(cfg, env["engine"].key())
        assert r[0]["ok"] is False
        assert "usuário ou senha do SMTP incorretos" in r[0]["error"]
        cfg["email"]["password"] = "certa"
        r = notify.send_test(cfg, env["engine"].key())
        assert r[0]["ok"] is True and len(s.messages) == 1
    finally:
        s.stop()


def test_starttls_required_but_unsupported(env, smtp):
    from sentinela import notify
    r = notify.send_test({"email": _email(smtp.port, security="starttls")}, env["engine"].key())
    assert not r[0]["ok"] and "não oferece STARTTLS" in r[0]["error"]


# ------------------------------------------------ falha 4: Telegram mal configurado

def test_telegram_errors(env, http_mock):
    from sentinela import notify
    k = env["engine"].key()
    r = notify.send_test({"telegram": {"enabled": True, "token": "999:ERRADO", "chat_id": "1"}}, k)
    assert r[0]["error"] == "token do bot inválido"
    r = notify.send_test({"telegram": {"enabled": True, "token": HttpMock.TOKEN, "chat_id": "000"}}, k)
    assert "chat não encontrado" in r[0]["error"]
    r = notify.send_test({"telegram": {"enabled": True, "token": HttpMock.TOKEN, "chat_id": "7"}}, k)
    assert r[0]["ok"]


def test_telegram_unreachable(env, monkeypatch):
    from conftest import free_port
    from sentinela import notify, settings
    monkeypatch.setattr(settings, "TELEGRAM_API", f"http://127.0.0.1:{free_port()}")
    r = notify.send_test({"telegram": {"enabled": True, "token": "1:x", "chat_id": "1"}},
                         env["engine"].key())
    assert r[0]["error"] == "conexão recusada pelo servidor"


# --------------------------------------------------- falha 5: webhook com erro

def test_webhook_http_500(env, http_mock):
    from sentinela import notify
    r = notify.send_test({"webhook": {"enabled": True, "url": http_mock.url + "/hook500"}},
                         env["engine"].key())
    assert r[0]["error"] == "o webhook respondeu HTTP 500"


def test_one_channel_failing_does_not_block_others(env, smtp, http_mock):
    from sentinela import notify
    e = env["engine"]
    notify.save({"email": _email(smtp.port),
                 "webhook": {"enabled": True, "url": http_mock.url + "/hook500"}}, e.key())
    res = notify.notify("backup_failed", "Backup falhou · x", ["Erro: teste"], e.key())
    assert sorted((c, ok) for c, ok, _ in res) == [("email", True), ("webhook", False)]
    assert len(smtp.messages) == 1


# ---------------------------------------------------- normalização e atraso

@needs_pg
def test_recovered_notification_after_failure(env, smtp):
    e = _setup(env, {**PG, "port": "5999"}, email=_email(smtp.port))
    e.start_backup("auto", wait=True)
    e.save_connection(PG)
    bid = e.start_backup("auto", wait=True)
    assert e.get_backup(bid)["status"] == "success"
    subjects = [t.splitlines()[0] for t in smtp.text()]
    assert subjects[0].endswith("Backup falhou · loja_producao")
    assert subjects[1].endswith("Backup voltou a funcionar · loja_producao")
    # um terceiro backup bem-sucedido não avisa nada (sucesso desligado por padrão)
    e.start_backup("auto", wait=True)
    assert len(smtp.messages) == 2


def test_late_backups_alert_with_cooldown(env, smtp):
    from sentinela import notify
    e = env["engine"]
    e.save_policy({"directory": str(env["backups"])})
    e.save_connection(PG)
    notify.save({"email": _email(smtp.port)}, e.key())
    st = env["storage"]
    assert e.check_late() is False  # primeira vez: marca o início da proteção
    st.set_setting("first_ready_at", st.iso(st.now() - timedelta(days=5)))
    assert e.check_late() is True
    assert "Backups atrasados" in smtp.text()[0]
    assert "Nenhuma cópia válida foi criada desde" in smtp.text()[0]
    e.check_late()  # dentro do intervalo de silêncio: não repete
    assert len(smtp.messages) == 1


def test_event_disabled_sends_nothing(env, smtp):
    from sentinela import notify
    e = env["engine"]
    notify.save({"email": _email(smtp.port), "events": {"backup_failed": False}}, e.key())
    assert notify.notify("backup_failed", "x", ["y"], e.key()) == []
    assert smtp.messages == []


# ---------------------------------------------------------- configuração

def test_config_validation_and_secrets(env):
    from sentinela import notify
    k = env["engine"].key()
    with pytest.raises(ValueError, match="destinatário"):
        notify.save({"email": {"enabled": True, "host": "smtp.x", "recipients": ""}}, k)
    with pytest.raises(ValueError, match="inválido"):
        notify.save({"email": {"enabled": True, "host": "smtp.x", "recipients": "semarroba"}}, k)
    with pytest.raises(ValueError, match="token"):
        notify.save({"telegram": {"enabled": True, "chat_id": "1"}}, k)
    with pytest.raises(ValueError, match="http"):
        notify.save({"webhook": {"enabled": True, "url": "ftp://x"}}, k)
    with pytest.raises(ValueError, match="Ative"):
        notify.send_test({}, k)
    cfg = notify.save({"email": {"enabled": True, "host": "smtp.x", "recipients": "a@b.c",
                                 "user": "u", "password": "SenhaSecreta!"},
                       "telegram": {"enabled": True, "token": "1:ABC", "chat_id": "5"}}, k)
    raw = str(env["storage"].get_setting("notifications"))
    assert "SenhaSecreta!" not in raw and "1:ABC" not in raw
    pub = notify.public(cfg)
    assert pub["email"]["has_password"] and pub["telegram"]["has_token"]
    assert "password" not in pub["email"] and "token" not in pub["telegram"]
    # salvar de novo sem informar a senha mantém a anterior
    notify.save({"email": {"host": "smtp.y"}}, k)
    assert notify.get_config(k)["email"]["password"] == "SenhaSecreta!"
