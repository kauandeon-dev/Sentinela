"""Avisos de falha: e-mail (SMTP), Telegram e webhook (Slack, Discord, Teams...).

Cada aviso é gravado na tabela ``notifications`` com o resultado de cada canal.
Os que falharem (servidor de e-mail fora do ar, sem internet...) são
reenviados automaticamente pelo agendador.
"""

import json
import logging
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import __version__, crypto, settings, storage
from .storage import iso, now

log = logging.getLogger("sentinela")

EVENTS = {
    "backup_failed": "Backup falhou",
    "replica_failed": "Cópia externa falhou",
    "restore_failed": "Restauração falhou",
    "verify_failed": "Verificação de integridade falhou",
    "late": "Backups atrasados",
    "recovered": "Backup voltou a funcionar",
    "success": "Backup concluído",
}
# Ligados por padrão: todas as falhas e a normalização; sucesso só se pedido.
DEFAULT_EVENTS = {k: k != "success" for k in EVENTS}
CHANNELS = {"email": "E-mail", "telegram": "Telegram", "webhook": "Webhook"}
SECRETS = {"email": ("password",), "telegram": ("token",), "webhook": ()}

DEFAULT = {
    "email": {"enabled": False, "host": "", "port": "587", "security": "starttls",
              "user": "", "password_sealed": "", "sender": "", "recipients": ""},
    "telegram": {"enabled": False, "token_sealed": "", "chat_id": ""},
    "webhook": {"enabled": False, "url": "", "format": "generic"},
    "events": dict(DEFAULT_EVENTS),
}

MAX_RETRIES = 3


class NotifyError(Exception):
    pass


# ====================================================================== config

def get_config(key=None):
    """Configuração atual. Com ``key`` (chave mestra), inclui os segredos abertos."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    saved = storage.get_setting("notifications", {}) or {}
    for k, v in saved.items():
        if isinstance(v, dict) and k in cfg:
            cfg[k].update(v)
    if key is not None:
        for ch, names in SECRETS.items():
            for n in names:
                cfg[ch][n] = crypto.unseal(key, cfg[ch].get(n + "_sealed", ""))
    return cfg


def merge(cfg, data, key, seal):
    """Aplica os campos do formulário em ``cfg``. Segredos vazios mantêm o salvo.

    ``seal=True`` guarda os segredos selados (para salvar); ``False`` os deixa
    abertos (para um teste de envio sem salvar)."""
    for ch in CHANNELS:
        d = data.get(ch)
        if not isinstance(d, dict):
            continue
        c = cfg[ch]
        for f, v in d.items():
            if f in SECRETS[ch]:
                if v:
                    if seal:
                        c[f + "_sealed"] = crypto.seal(key, str(v))
                    else:
                        c[f] = str(v)
            elif f == "enabled":
                c[f] = bool(v)
            elif f in DEFAULT[ch] and not f.endswith("_sealed"):
                c[f] = str(v if v is not None else "").strip()
    if isinstance(data.get("events"), dict):
        for k in EVENTS:
            if k in data["events"]:
                cfg["events"][k] = bool(data["events"][k])
    _validate(cfg)
    return cfg


def _validate(cfg):
    e = cfg["email"]
    if e["security"] not in ("starttls", "ssl", "none"):
        e["security"] = "starttls"
    if e["enabled"]:
        if not e["host"]:
            raise ValueError("Informe o servidor SMTP")
        if not str(e["port"]).isdigit():
            raise ValueError("Porta SMTP inválida")
        if not recipients(e):
            raise ValueError("Informe pelo menos um destinatário de e-mail")
        bad = [r for r in recipients(e) if "@" not in r]
        if bad:
            raise ValueError(f"Endereço de e-mail inválido: {bad[0]}")
    t = cfg["telegram"]
    if t["enabled"] and not t["chat_id"]:
        raise ValueError("Informe o chat_id do Telegram")
    w = cfg["webhook"]
    if w["format"] not in ("generic", "slack", "discord", "teams"):
        w["format"] = "generic"
    if w["enabled"] and not w["url"].startswith(("http://", "https://")):
        raise ValueError("A URL do webhook deve começar com http:// ou https://")


def save(data, key):
    cfg = merge(get_config(), data, key, seal=True)
    # nunca persiste segredos abertos
    for ch, names in SECRETS.items():
        for n in names:
            cfg[ch].pop(n, None)
    if cfg["telegram"]["enabled"] and not cfg["telegram"]["token_sealed"]:
        raise ValueError("Informe o token do bot do Telegram")
    storage.set_setting("notifications", cfg)
    log.info("Configuração de avisos atualizada (canais ativos: %s)",
             ", ".join(CHANNELS[c] for c in CHANNELS if cfg[c]["enabled"]) or "nenhum")
    return cfg


def public(cfg):
    out = {}
    for ch in CHANNELS:
        c = {k: v for k, v in cfg[ch].items() if not k.endswith("_sealed") and k not in SECRETS[ch]}
        for n in SECRETS[ch]:
            c["has_" + n] = bool(cfg[ch].get(n + "_sealed"))
        out[ch] = c
    out["events"] = dict(cfg["events"])
    out["active"] = [c for c in CHANNELS if cfg[c]["enabled"]]
    return out


def recipients(e):
    return [r.strip() for r in str(e.get("recipients", "")).replace(";", ",").split(",") if r.strip()]


# ===================================================================== envio

def notify(event, title, lines, key, elog=None, dedup=None):
    """Envia um aviso para todos os canais ativos, se o evento estiver ligado.

    ``dedup``: chave que identifica o problema; avisos repetidos com a mesma
    chave dentro de NOTIFY_COOLDOWN_HOURS são suprimidos (evita enxurrada).
    Nunca levanta exceção: falha de aviso não pode derrubar o backup."""
    try:
        cfg = get_config(key)
        active = [c for c in CHANNELS if cfg[c]["enabled"]]
        if not active or not cfg["events"].get(event, False):
            return []
        if dedup:
            since = iso(now() - timedelta(hours=settings.NOTIFY_COOLDOWN_HOURS))
            if storage.row("SELECT 1 FROM notifications WHERE dedup=? AND ts>=? AND ok=1",
                           (dedup, since)):
                if elog:
                    elog("INFO", "Aviso já enviado recentemente para este problema — não repetido")
                return []
        body = "\n".join(lines)
        results = []
        for ch in active:
            ok, err = _deliver(cfg, ch, event, title, body)
            storage.execute(
                "INSERT INTO notifications(ts, event, channel, title, body, ok, error, attempts, dedup) "
                "VALUES(?,?,?,?,?,?,?,1,?)",
                (iso(now()), event, ch, title, body, int(ok), err, dedup))
            results.append((ch, ok, err))
            target = _target(cfg, ch)
            if elog:
                if ok:
                    elog("OK", f"Aviso enviado por {CHANNELS[ch]}{target}")
                else:
                    elog("WARN", f"Falha ao enviar aviso por {CHANNELS[ch]}: {err} — "
                                 "nova tentativa automática em até 1 hora")
            else:
                (log.info if ok else log.warning)(
                    "Aviso '%s' por %s: %s", title, CHANNELS[ch], "enviado" if ok else err)
        return results
    except Exception as e:  # pragma: no cover - proteção final
        log.exception("Erro inesperado ao enviar avisos")
        if elog:
            elog("WARN", f"Erro inesperado ao enviar avisos: {e}")
        return []


def send_test(data, key):
    """Envia uma mensagem de teste pelos canais do formulário (sem salvar)."""
    cfg = merge(get_config(key), data or {}, key, seal=False)
    active = [c for c in CHANNELS if cfg[c]["enabled"]]
    if not active:
        raise ValueError("Ative pelo menos um canal para testar")
    out = []
    for ch in active:
        ok, err = _deliver(cfg, ch, "test", "Teste de aviso",
                           "Se você recebeu esta mensagem, os avisos do Sentinela estão funcionando.")
        out.append({"channel": ch, "label": CHANNELS[ch], "ok": ok, "error": err})
    return out


def retry_failed():
    """Reenvia avisos que falharam nas últimas 24h (no máx. MAX_RETRIES vezes)."""
    from . import engine
    since = iso(now() - timedelta(hours=24))
    pending = storage.rows(
        "SELECT * FROM notifications WHERE ok=0 AND attempts<? AND ts>=? AND event!='test' "
        "ORDER BY id", (MAX_RETRIES, since))
    if not pending:
        return 0
    cfg = get_config(engine.key())
    sent = 0
    for n in pending:
        if not cfg.get(n["channel"], {}).get("enabled"):
            continue
        ok, err = _deliver(cfg, n["channel"], n["event"], n["title"], n["body"] + "\n\n(reenvio)")
        storage.execute("UPDATE notifications SET ok=?, error=?, attempts=attempts+1, retried_at=? "
                        "WHERE id=?", (int(ok), err, iso(now()), n["id"]))
        sent += ok
        (log.info if ok else log.warning)("Reenvio do aviso '%s' por %s: %s", n["title"],
                                          CHANNELS[n["channel"]], "enviado" if ok else err)
    return sent


def _target(cfg, ch):
    if ch == "email":
        r = recipients(cfg["email"])
        return f" para {', '.join(r)}" if len(r) <= 3 else f" para {len(r)} destinatários"
    if ch == "telegram":
        return f" (chat {cfg['telegram']['chat_id']})"
    return ""


def _deliver(cfg, ch, event, title, body):
    try:
        {"email": _email, "telegram": _telegram, "webhook": _webhook}[ch](cfg[ch], event, title, body)
        return True, None
    except NotifyError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _header():
    return f"Sentinela · {socket.gethostname()}"


# ------------------------------------------------------------------- e-mail

def _email(c, event, title, body):
    to = recipients(c)
    if not c.get("host") or not to:
        raise NotifyError("servidor SMTP ou destinatários não configurados")
    msg = EmailMessage()
    icon = "✅" if event in ("recovered", "success", "test") else "⚠️"
    msg["Subject"] = f"{icon} [Sentinela] {title}"
    msg["From"] = c.get("sender") or c.get("user") or f"sentinela@{socket.gethostname()}"
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="sentinela.local")
    msg.set_content(f"{title}\n\n{body}\n\n--\n{_header()} · v{__version__}\n")
    host, port, sec = c["host"], int(c.get("port") or 0), c.get("security", "starttls")
    timeout = settings.NET_TIMEOUT
    try:
        if sec == "ssl":
            s = smtplib.SMTP_SSL(host, port or 465, timeout=timeout,
                                 context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port or 587, timeout=timeout)
        with s:
            s.ehlo()
            if sec == "starttls":
                if not s.has_extn("starttls"):
                    raise NotifyError("o servidor SMTP não oferece STARTTLS "
                                      "(use SSL/TLS na porta 465 ou 'sem criptografia')")
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            if c.get("user"):
                s.login(c["user"], c.get("password") or "")
            refused = s.send_message(msg)
            if refused:
                raise NotifyError(f"destinatários recusados: {', '.join(refused)}")
    except NotifyError:
        raise
    except smtplib.SMTPAuthenticationError as e:
        raise NotifyError("usuário ou senha do SMTP incorretos "
                          "(no Gmail, use uma senha de app)") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise NotifyError(f"destinatários recusados: {', '.join(e.recipients)}") from e
    except smtplib.SMTPSenderRefused as e:
        raise NotifyError(f"remetente recusado pelo servidor: {e.sender}") from e
    except smtplib.SMTPNotSupportedError as e:
        raise NotifyError("o servidor SMTP não aceita autenticação nesta conexão "
                          "(ative STARTTLS ou SSL)") from e
    except ssl.SSLError as e:
        raise NotifyError(f"falha no TLS com o servidor SMTP ({e.reason or e})") from e
    except (socket.timeout, TimeoutError) as e:
        raise NotifyError(f"tempo esgotado ao conectar em {host}:{port}") from e
    except ConnectionRefusedError as e:
        raise NotifyError(f"conexão recusada por {host}:{port}") from e
    except socket.gaierror as e:
        raise NotifyError(f"servidor SMTP não encontrado ({host})") from e
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"erro SMTP: {e}") from e


# ----------------------------------------------------------------- Telegram

def _telegram(c, event, title, body):
    token, chat = c.get("token"), c.get("chat_id")
    if not token or not chat:
        raise NotifyError("token do bot ou chat_id não configurados")
    icon = "✅" if event in ("recovered", "success", "test") else "⚠️"
    text = f"{icon} {title}\n\n{body}\n\n— {_header()}"
    url = f"{settings.TELEGRAM_API.rstrip('/')}/bot{token}/sendMessage"
    try:
        r = _post_json(url, {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
    except urllib.error.HTTPError as e:
        desc = _json_error(e)
        if e.code == 401 or e.code == 404:
            raise NotifyError("token do bot inválido") from e
        if e.code == 400 and "chat not found" in desc.lower():
            raise NotifyError("chat não encontrado — envie /start para o bot e confira o chat_id") from e
        if e.code == 403:
            raise NotifyError("o bot foi bloqueado ou removido do chat") from e
        raise NotifyError(f"o Telegram recusou a mensagem (HTTP {e.code}: {desc})") from e
    if not r.get("ok", False):
        raise NotifyError(f"o Telegram recusou a mensagem: {r.get('description', r)}")


# ------------------------------------------------------------------ webhook

def _webhook(c, event, title, body):
    url = c.get("url")
    if not url:
        raise NotifyError("URL do webhook não configurada")
    fmt = c.get("format", "generic")
    text = f"{title}\n{body}"
    if fmt == "slack":
        payload = {"text": f"*{title}*\n{body}"}
    elif fmt == "discord":
        payload = {"content": text[:1900], "username": "Sentinela"}
    elif fmt == "teams":
        payload = {"text": text.replace("\n", "  \n")}
    else:
        payload = {"source": "sentinela", "host": socket.gethostname(), "event": event,
                   "title": title, "message": body, "ts": iso(now())}
    try:
        _post_json(url, payload)
    except urllib.error.HTTPError as e:
        raise NotifyError(f"o webhook respondeu HTTP {e.code}") from e


def _post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": f"Sentinela/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=settings.NET_TIMEOUT) as r:
            raw = r.read(65536)
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, ConnectionRefusedError):
            raise NotifyError("conexão recusada pelo servidor") from e
        if isinstance(reason, socket.gaierror):
            raise NotifyError("endereço não encontrado (sem DNS/internet?)") from e
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise NotifyError("tempo esgotado") from e
        if isinstance(reason, ssl.SSLError):
            raise NotifyError(f"falha no certificado TLS ({reason})") from e
        raise NotifyError(f"falha de rede: {reason}") from e
    except (socket.timeout, TimeoutError) as e:
        raise NotifyError("tempo esgotado") from e
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {"ok": True}


def _json_error(e):
    try:
        return json.loads(e.read(4096)).get("description", "")
    except Exception:
        return ""
