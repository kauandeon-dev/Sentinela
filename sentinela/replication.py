"""Cópias externas e a regra 3-2-1.

    3 cópias dos dados  — o banco em produção + a cópia local + ao menos 1 externa
    2 mídias diferentes — a cópia local e a externa não podem estar no mesmo disco
    1 fora do local     — ao menos um destino fora do prédio (SFTP/S3 em outro lugar)

Depois de cada backup verificado, a cópia é enviada a cada destino ativo,
lida de volta e conferida pelo SHA-256. Envios que falharem são retomados a
cada hora pelo agendador; a retenção apaga também as cópias externas; e, se a
cópia local sumir ou estiver corrompida, a restauração busca uma cópia
externa íntegra automaticamente.
"""

import hashlib
import json
import os
import socket
import time
import uuid
from pathlib import Path

from . import crypto, destinations as D, engine, notify, settings, storage
from .storage import iso, now

log = engine.log

# Ordem de preferência para buscar uma cópia (o mais rápido primeiro).
FETCH_ORDER = {"directory": 0, "sftp": 1, "s3": 2}
MANIFEST_VERSION = 1


# ================================================================ configuração

def get_destinations(with_secrets=False):
    out = []
    for d in storage.get_setting("destinations", []) or []:
        d = dict(d)
        if with_secrets:
            for f in D.SECRETS.get(d["type"], ()):
                d[f] = crypto.unseal(engine.key(), d.get(f + "_sealed", ""))
        out.append(d)
    return out


def get_destination(did, with_secrets=False):
    for d in get_destinations(with_secrets):
        if d["id"] == did:
            return d
    return None


FIELDS = {
    "directory": ("path",),
    "sftp": ("host", "port", "user", "auth", "path"),
    "s3": ("endpoint", "region", "bucket", "prefix", "access_key"),
}


def _apply(d, data, seal):
    """Copia os campos do formulário para ``d`` (segredos vazios mantêm o salvo)."""
    if data.get("type") in D.TYPES and not d.get("type"):
        d["type"] = data["type"]
    t = d["type"]
    if "name" in data:
        d["name"] = str(data["name"] or "").strip()[:60]
    for f in ("enabled", "offsite"):
        if f in data:
            d[f] = bool(data[f])
    for f in FIELDS[t]:
        if f in data:
            d[f] = str(data[f] if data[f] is not None else "").strip()
    for f in D.SECRETS.get(t, ()):
        if data.get(f):
            if seal:
                d[f + "_sealed"] = crypto.seal(engine.key(), data[f])
            else:
                d[f] = data[f]
    if t == "sftp":
        if d.get("auth") not in ("password", "key"):
            d["auth"] = "password"
        d["port"] = d.get("port") or "22"
        if not str(d["port"]).isdigit():
            raise ValueError("Porta SFTP inválida")
        if data.get("reset_host_key"):
            d["host_key"] = None
    return d


def _validate(d, secrets_open=False):
    t = d["type"]
    if not d.get("name"):
        d["name"] = {"directory": "Disco externo", "sftp": f"SFTP {d.get('host', '')}",
                     "s3": f"S3 {d.get('bucket', '')}"}[t].strip()
    if t == "directory":
        d["path"] = validate_dir(d.get("path"))
    elif t == "sftp":
        if not d.get("host") or not d.get("user"):
            raise ValueError("Informe o servidor e o usuário SFTP")
        has_key = d.get("private_key") if secrets_open else d.get("private_key_sealed")
        if d["auth"] == "key" and not has_key:
            raise ValueError("Cole a chave privada SSH do destino")
    elif t == "s3":
        if not d.get("bucket"):
            raise ValueError("Informe o bucket")
        has = d.get("secret_key") if secrets_open else d.get("secret_key_sealed")
        if not d.get("access_key") or not has:
            raise ValueError("Informe a chave de acesso e a chave secreta")


def validate_dir(path):
    """Outro disco: isolado da aplicação e diferente da pasta das cópias locais."""
    p = Path(engine.validate_directory(path))
    primary = Path(engine.get_policy()["directory"]).resolve()
    if p == primary or primary in p.parents or p in primary.parents:
        raise ValueError("O destino precisa ser uma pasta diferente (e fora) da pasta das cópias "
                         "locais — de preferência em outro disco")
    return str(p)


def save_destination(data):
    dests = storage.get_setting("destinations", []) or []
    did = data.get("id")
    if did:
        d = next((x for x in dests if x["id"] == did), None)
        if d is None:
            raise ValueError("Destino não encontrado")
        before = (d.get("host"), str(d.get("port")))
    else:
        if data.get("type") not in D.TYPES:
            raise ValueError("Escolha o tipo de destino")
        d = {"id": "d_" + uuid.uuid4().hex[:8], "type": data["type"], "enabled": True,
             "offsite": data["type"] != "directory", "host_key": None,
             "created_at": iso(now())}
        before = None
    d = _apply(d, data, seal=True)
    if d["type"] == "sftp" and before and before != (d.get("host"), str(d.get("port"))):
        d["host_key"] = None
    if d["type"] == "sftp" and not d.get("host_key"):
        seen = _seen_keys.pop((d.get("host"), str(d.get("port"))), None)
        if seen:
            d["host_key"] = seen
    _validate(d)
    if not did:
        dests.append(d)
    storage.set_setting("destinations", dests)
    log.info("Destino de cópias externas salvo: %s (%s · %s)", d["name"], D.TYPES[d["type"]],
             D.describe(d))
    return d


def delete_destination(did):
    dests = storage.get_setting("destinations", []) or []
    d = next((x for x in dests if x["id"] == did), None)
    if not d:
        raise ValueError("Destino não encontrado")
    storage.set_setting("destinations", [x for x in dests if x["id"] != did])
    log.info("Destino removido: %s (as cópias já enviadas permanecem lá)", d["name"])


_seen_keys = {}  # chaves de host vistas em testes ainda não salvos


def test_destination(data):
    """Testa um destino (do formulário, sem salvar): grava, lê e apaga um arquivo."""
    base = {}
    if data.get("id"):
        base = get_destination(data["id"], with_secrets=True) or {}
    elif data.get("type") not in D.TYPES:
        raise ValueError("Escolha o tipo de destino")
    d = _apply(dict(base) or {"type": data["type"], "host_key": None}, data, seal=False)
    if d["type"] == "sftp" and base and (base.get("host"), str(base.get("port"))) != \
            (d.get("host"), str(d.get("port"))):
        d["host_key"] = None
    _validate(d, secrets_open=True)
    with D.driver(d) as dr:
        summary = dr.test()
        seen = dr.host_key
    fp = None
    if seen:
        fp = seen["fingerprint"]
        _remember_host_key(d, seen)
    return summary, fp


def _remember_host_key(d, seen):
    """TOFU dos destinos SFTP: grava a chave do servidor na 1ª conexão."""
    dests = storage.get_setting("destinations", []) or []
    saved = next((x for x in dests if x["id"] == d.get("id")), None)
    target = (d.get("host"), str(d.get("port")))
    if saved and (saved.get("host"), str(saved.get("port"))) == target:
        if not saved.get("host_key"):
            saved["host_key"] = seen
            storage.set_setting("destinations", dests)
            log.info("Chave do servidor SFTP %s:%s registrada: %s", *target, seen["fingerprint"])
    else:
        _seen_keys[target] = seen


def public(d, primary_medium=None):
    out = {k: v for k, v in d.items() if not k.endswith("_sealed") and k != "host_key"}
    for f in D.SECRETS.get(d["type"], ()):
        out.pop(f, None)
        out["has_" + f] = bool(d.get(f + "_sealed"))
    out["host_key"] = (d.get("host_key") or {}).get("fingerprint")
    out["type_label"] = D.TYPES[d["type"]]
    out["target"] = D.describe(d)
    if d["type"] == "directory" and primary_medium:
        out["same_device"] = D.medium(d) == primary_medium
    return out


# =================================================================== réplicas

def replicas_of(bid):
    return storage.rows("SELECT * FROM replicas WHERE backup_id=? ORDER BY id", (bid,))


def _upsert(bid, d, **kw):
    cur = storage.row("SELECT * FROM replicas WHERE backup_id=? AND dest_id=?", (bid, d["id"]))
    if cur is None:
        storage.execute(
            "INSERT INTO replicas(backup_id, dest_id, dest_name, status, created_at) VALUES(?,?,?,?,?)",
            (bid, d["id"], d["name"], kw.get("status", "error"), iso(now())))
    kw.setdefault("dest_name", d["name"])
    sets = ", ".join(f"{k}=?" for k in kw)
    storage.execute(f"UPDATE replicas SET {sets} WHERE backup_id=? AND dest_id=?",
                    (*kw.values(), bid, d["id"]))


def manifest(b):
    return json.dumps({
        "sentinela": MANIFEST_VERSION,
        "backup_id": b["id"], "file": os.path.basename(b["path"]),
        "sgbd": b["sgbd"], "dbname": b["dbname"], "trigger": b["trigger"],
        "created_at": b["created_at"], "finished_at": b["finished_at"],
        "size": b["size"], "raw_size": b["raw_size"], "sha256": b["sha256"],
        "compressed": bool(b["compressed"]), "encrypted": bool(b["encrypted"]),
        "key_id": b.get("key_id"), "host": socket.gethostname(),
    }, ensure_ascii=False, indent=2).encode()


def _progress_cb(total):
    state = {"n": 0}

    def cb(n):
        state["n"] += n
        engine._current["bytes"] = state["n"]
    engine._current.update(bytes=0, total=total)
    return cb


def send(elog, b, d, attempts=None):
    """Envia a cópia ``b`` ao destino ``d`` (com segredos abertos), confere e registra.

    Retorna (ok, mensagem de erro)."""
    attempts = attempts or settings.REPLICA_ATTEMPTS
    name = os.path.basename(b["path"])
    where = f'{d["name"]} ({D.TYPES[d["type"]]} · {D.describe(d)})'
    elog("INFO", f"Enviando cópia para {where}")
    if engine._current.get("kind") in ("backup", "replicate"):
        engine._set_current(stage="replicacao", dest=d["name"])
    last = None
    prev = (storage.row("SELECT attempts FROM replicas WHERE backup_id=? AND dest_id=?",
                        (b["id"], d["id"])) or {}).get("attempts") or 0
    for i in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            with D.driver(d) as dr:
                if dr.host_key:
                    _remember_host_key(d, dr.host_key)
                remote = dr.put(b["path"], name, _progress_cb(b["size"]))
                # Confere lendo de volta: o que está no destino é idêntico ao local?
                h = hashlib.sha256()
                dr.get(name, h.update, _progress_cb(b["size"]))
                if h.hexdigest() != b["sha256"]:
                    dr.delete(name)
                    raise D.DestinationError("o SHA-256 da cópia no destino não confere "
                                             "(transferência corrompida) — arquivo removido")
                dr.put_bytes(manifest(b), name + ".json")
                dr.put_bytes(f"{b['sha256']}  {name}\n".encode(), name + ".sha256")
            dur = time.monotonic() - t0
            _upsert(b["id"], d, status="success", remote_name=name, remote_path=remote,
                    size=b["size"], sha256=b["sha256"], attempts=prev + i,
                    uploaded_at=iso(now()), verified_at=iso(now()), verify_ok=1, error=None,
                    deleted_at=None)
            rate = engine.fmt_size(b["size"] / max(dur, 0.001))
            elog("OK", f"Cópia externa em {d['name']} conferida (SHA-256 confere) · "
                       f"{engine.fmt_size(b['size'])} em {engine.fmt_duration(dur)} · {rate}/s")
            return True, None
        except D.DestinationError as e:
            last = str(e)
        except Exception as e:  # erro inesperado do driver
            last = f"{type(e).__name__}: {e}"
            log.exception("Erro inesperado no envio para %s", d["name"])
        if i < attempts:
            wait = settings.REPLICA_BACKOFF[min(i - 1, len(settings.REPLICA_BACKOFF) - 1)] \
                if settings.REPLICA_BACKOFF else 0
            elog("WARN", f"Tentativa {i}/{attempts} para {d['name']} falhou: {last}"
                         + (f" — nova tentativa em {engine.fmt_duration(wait)}" if wait else ""))
            time.sleep(wait)
    _upsert(b["id"], d, status="error", remote_name=name, attempts=prev + attempts, error=last)
    elog("ERRO", f"Cópia externa em {d['name']} falhou: {last}")
    return False, last


def replicate_backup(elog, b):
    """Chamado ao fim de cada backup: envia para todos os destinos ativos."""
    dests = [d for d in get_destinations(with_secrets=True) if d.get("enabled")]
    if not dests:
        return []
    elog("INFO", f"Regra 3-2-1: enviando para {len(dests)} destino(s) externo(s)")
    results = []
    for d in dests:
        ok, err = send(elog, b, d)
        results.append((d, ok, err))
    r = rule_321()
    sym = lambda ok: "✓" if ok else "✗"  # noqa: E731
    elog("OK" if r["ok"] else "WARN",
         f"Regra 3-2-1: {r['copies']} cópias {sym(r['copies'] >= 3)} · {r['media']} mídias "
         f"{sym(r['media'] >= 2)} · {r['offsite']} fora do local {sym(r['offsite'] >= 1)}")
    return results


def notify_failures(elog, b, results, trigger_label):
    failed = [(d, err) for d, ok, err in results if not ok]
    for d, err in failed:
        notify.notify(
            "replica_failed", f"Cópia externa falhou · {d['name']}",
            [f"Destino: {d['name']} ({D.TYPES[d['type']]} · {D.describe(d)})",
             f"Cópia: {b['id']} · banco {b['dbname']} ({trigger_label})",
             f"Erro: {err}",
             "A cópia local está íntegra. O Sentinela tenta reenviar automaticamente a cada hora."],
            engine.key(), elog, dedup=f"replica:{d['id']}")


# ===================================================== sincronização (retomada)

def pending(manual=False, dest_id=None):
    """Cópias locais válidas que ainda não estão em algum destino ativo."""
    dests = [d for d in get_destinations(with_secrets=True) if d.get("enabled")
             and (dest_id is None or d["id"] == dest_id)]
    if not dests:
        return []
    backups = storage.rows(
        "SELECT * FROM backups WHERE status='success' AND deleted_at IS NULL "
        "AND trigger!='pre-restore' AND path IS NOT NULL ORDER BY created_at DESC")
    work = []
    for d in dests:
        for b in backups:
            r = storage.row("SELECT status, attempts FROM replicas WHERE backup_id=? AND dest_id=?",
                            (b["id"], d["id"]))
            if r and r["status"] in ("success", "deleted", "delete_pending"):
                continue
            if r and not manual and r["attempts"] >= settings.REPLICA_MAX_RETRIES:
                continue
            if not os.path.exists(b["path"]):
                continue
            work.append((b, d))
    return work


def pending_deletes():
    return storage.rows("SELECT * FROM replicas WHERE status='delete_pending'")


def start_sync(trigger="auto", wait=False, dest_id=None):
    """Retoma envios pendentes e exclusões pendentes. Retorna o id da execução
    (ou None se não havia nada a fazer)."""
    manual = trigger == "manual"
    work = pending(manual, dest_id)
    dels = pending_deletes()
    if not work and not dels:
        return None
    engine._acquire()
    try:
        elog = engine.ExecLog("replicate", trigger)
        engine._set_current(reset=True, kind="replicate", trigger=trigger, backup_id=None,
                            execution_id=elog.id, started_at=iso(elog.started), stage="replicacao",
                            bytes=0, total=None)
    except Exception:
        engine._release()
        raise
    if wait:
        try:
            _perform_sync(elog, work, dels, manual)
        finally:
            engine._release()
    else:
        engine._spawn(_perform_sync, elog, work, dels, manual)
    return elog.id


def _perform_sync(elog, work, dels, manual):
    ok_all = True
    try:
        if work:
            elog("INFO", f"Sincronizando cópias externas: {len(work)} envio(s) pendente(s)")
        failures = {}
        for b, d in work:
            if d["id"] in failures:  # destino já falhou nesta rodada: não insiste
                continue
            ok, err = send(elog, b, d, attempts=settings.REPLICA_ATTEMPTS if manual else 1)
            if not ok:
                ok_all = False
                failures[d["id"]] = (d, err, b)
        for d, err, b in failures.values():
            notify_failures(elog, b, [(d, False, err)],
                            "sincronização manual" if manual else "retomada automática")
        if dels:
            elog("INFO", f"Retomando {len(dels)} exclusão(ões) pendente(s) nos destinos")
            for r in dels:
                if not _delete_replica(r, elog):
                    ok_all = False
        elog("OK" if ok_all else "WARN",
             "Sincronização concluída" if ok_all else "Sincronização concluída com pendências")
        elog.finish("success" if ok_all else "error")
    except Exception as e:
        elog("ERRO", f"Falha na sincronização: {e}")
        elog.finish("error")
        log.exception("Erro na sincronização das cópias externas")


# ================================================================== exclusão

def delete_replicas(b, elog=None):
    """Apaga as cópias externas de ``b`` (retenção ou exclusão manual)."""
    for r in storage.rows("SELECT * FROM replicas WHERE backup_id=? AND status IN "
                          "('success','error','delete_pending')", (b["id"],)):
        if r["status"] == "error" and not r["remote_name"]:
            continue
        _delete_replica(r, elog)


def _delete_replica(r, elog=None):
    d = get_destination(r["dest_id"], with_secrets=True)
    if d is None:
        storage.execute("UPDATE replicas SET status='deleted', deleted_at=?, error=? WHERE id=?",
                        (iso(now()), "destino removido da configuração", r["id"]))
        return True
    name = r["remote_name"]
    try:
        with D.driver(d) as dr:
            for n in (name, name + ".json", name + ".sha256"):
                dr.delete(n)
        storage.execute("UPDATE replicas SET status='deleted', deleted_at=?, error=NULL WHERE id=?",
                        (iso(now()), r["id"]))
        msg = f"Cópia externa {name} excluída de {d['name']}"
        (elog("INFO", msg) if elog else log.info(msg))
        return True
    except Exception as e:
        storage.execute("UPDATE replicas SET status='delete_pending', error=? WHERE id=?",
                        (f"exclusão pendente: {e}", r["id"]))
        msg = f"Não foi possível excluir {name} de {d['name']}: {e} — nova tentativa em até 1 hora"
        (elog("WARN", msg) if elog else log.warning(msg))
        return False


# ============================================================ busca e conferência

def fetch_local(elog, b):
    """Traz para o servidor uma cópia externa íntegra de ``b`` (cópia local
    ausente ou corrompida). Retorna o caminho local recuperado."""
    reps = storage.rows("SELECT * FROM replicas WHERE backup_id=? AND status='success'", (b["id"],))
    dests = {d["id"]: d for d in get_destinations(with_secrets=True)}
    reps = [r for r in reps if r["dest_id"] in dests]
    if not reps:
        raise engine.BackupError("Nenhuma cópia externa registrada para esta cópia")
    reps.sort(key=lambda r: FETCH_ORDER.get(dests[r["dest_id"]]["type"], 9))
    directory = Path(engine.get_policy()["directory"])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    errors = []
    for r in reps:
        d = dests[r["dest_id"]]
        name = r["remote_name"]
        target = directory / name
        part = directory / (name + ".fetch.part")
        elog("INFO", f"Buscando a cópia em {d['name']} ({D.TYPES[d['type']]})")
        try:
            h = hashlib.sha256()
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as out:
                def sink(chunk):
                    out.write(chunk)
                    h.update(chunk)
                with D.driver(d) as dr:
                    dr.get(name, sink, _progress_cb(b["size"]))
                out.flush()
                os.fsync(out.fileno())
            if h.hexdigest() != b["sha256"]:
                storage.execute("UPDATE replicas SET verify_ok=0, verified_at=?, error=? WHERE id=?",
                                (iso(now()), "SHA-256 não confere (cópia externa corrompida)", r["id"]))
                raise D.DestinationError("a cópia externa está corrompida (SHA-256 não confere)")
            os.replace(part, target)
            storage.execute("UPDATE backups SET path=?, verified_at=?, verify_ok=1 WHERE id=?",
                            (str(target), iso(now()), b["id"]))
            elog("OK", f"Cópia recuperada de {d['name']} e conferida (SHA-256 confere) → {target}")
            return str(target)
        except Exception as e:
            try:
                part.unlink()
            except OSError:
                pass
            errors.append(f"{d['name']}: {e}")
            elog("WARN", f"Não foi possível usar a cópia em {d['name']}: {e}")
    raise engine.BackupError("Nenhuma cópia externa íntegra disponível — " + "; ".join(errors))


def verify_replicas(elog, b):
    """Lê de volta cada cópia externa de ``b`` e confere o SHA-256. Retorna os problemas."""
    problems = []
    dests = {d["id"]: d for d in get_destinations(with_secrets=True)}
    for r in storage.rows("SELECT * FROM replicas WHERE backup_id=? AND status='success'", (b["id"],)):
        d = dests.get(r["dest_id"])
        if not d:
            continue
        try:
            h = hashlib.sha256()
            with D.driver(d) as dr:
                dr.get(r["remote_name"], h.update, _progress_cb(b["size"]))
            ok = h.hexdigest() == b["sha256"]
            err = None if ok else "SHA-256 não confere (cópia externa corrompida ou alterada)"
        except Exception as e:
            ok, err = False, str(e)
        storage.execute("UPDATE replicas SET verified_at=?, verify_ok=?, error=? WHERE id=?",
                        (iso(now()), int(ok), err, r["id"]))
        if ok:
            elog("OK", f"Cópia externa em {d['name']}: SHA-256 confere")
        else:
            elog("ERRO", f"Cópia externa em {d['name']}: {err}")
            problems.append(f"{d['name']}: {err}")
    return problems


# =================================================================== importação

def import_from(did):
    """Procura manifestos de cópias no destino e registra as que não estão no
    histórico (recuperação de desastre: servidor novo, mesmo destino)."""
    d = get_destination(did, with_secrets=True)
    if not d:
        raise ValueError("Destino não encontrado")
    found = imported = 0
    keys = set()
    with D.driver(d) as dr:
        names = set(dr.list())
        for n in sorted(names):
            if not n.endswith(".json"):
                continue
            buf = bytearray()
            try:
                dr.get(n, buf.extend)
                m = json.loads(bytes(buf))
            except Exception:
                continue
            if m.get("sentinela") != MANIFEST_VERSION or not m.get("backup_id") \
                    or not m.get("sha256") or m.get("file") not in names:
                continue
            found += 1
            if storage.row("SELECT 1 FROM backups WHERE id=?", (m["backup_id"],)):
                continue
            storage.execute(
                "INSERT INTO backups(id, trigger, sgbd, dbname, created_at, finished_at, status, "
                "path, raw_size, size, sha256, compressed, encrypted, key_id, origin) "
                "VALUES(?,?,?,?,?,?, 'success', NULL, ?,?,?,?,?,?, 'imported')",
                (m["backup_id"], m.get("trigger") or "auto", m["sgbd"], m["dbname"],
                 m["created_at"], m.get("finished_at"), m.get("raw_size"), m.get("size"),
                 m["sha256"], int(bool(m.get("compressed"))), int(bool(m.get("encrypted"))),
                 m.get("key_id")))
            _upsert(m["backup_id"], d, status="success", remote_name=m["file"],
                    remote_path=m["file"], size=m.get("size"), sha256=m["sha256"],
                    uploaded_at=m.get("finished_at"))
            imported += 1
            if m.get("encrypted") and m.get("key_id"):
                keys.add(m["key_id"])
    missing = sorted(k for k in keys if not engine.has_key(k))
    log.info("Importação de %s: %d cópia(s) encontrada(s), %d registrada(s)", d["name"], found, imported)
    return {"found": found, "imported": imported, "missing_keys": missing}


# ================================================================= regra 3-2-1

def rule_321():
    dests = {d["id"]: d for d in get_destinations() if d.get("enabled")}
    latest = storage.row(
        "SELECT * FROM backups WHERE status='success' AND deleted_at IS NULL "
        "AND trigger!='pre-restore' ORDER BY created_at DESC LIMIT 1")
    out = {"backup_id": latest["id"] if latest else None, "destinations": len(dests),
           "copies": 1, "media": 0, "offsite": 0, "ok": False, "local": False}
    if not latest:
        return out
    media = set()
    if latest["path"] and os.path.exists(latest["path"]):
        out["local"] = True
        out["copies"] += 1
        media.add(primary_medium())
    for r in storage.rows("SELECT * FROM replicas WHERE backup_id=? AND status='success'",
                          (latest["id"],)):
        d = dests.get(r["dest_id"])
        if not d or r["verify_ok"] == 0:
            continue
        out["copies"] += 1
        media.add(D.medium(d))
        if d.get("offsite"):
            out["offsite"] += 1
    out["media"] = len(media)
    out["ok"] = out["copies"] >= 3 and out["media"] >= 2 and out["offsite"] >= 1
    return out


def primary_medium():
    return D.medium({"type": "directory", "path": engine.get_policy()["directory"]})


def dest_status():
    """Situação de cada destino, para o painel."""
    out = []
    pm = primary_medium()
    backups = storage.rows("SELECT id FROM backups WHERE status='success' AND deleted_at IS NULL "
                           "AND trigger!='pre-restore' AND path IS NOT NULL")
    ids = {b["id"] for b in backups}
    for d in get_destinations():
        rows = storage.rows("SELECT * FROM replicas WHERE dest_id=? ORDER BY COALESCE(uploaded_at, created_at) DESC",
                            (d["id"],))
        last = next((r for r in rows if r["status"] in ("success", "error")), None)
        ok_ids = {r["backup_id"] for r in rows if r["status"] == "success"}
        p = public(d, pm)
        p.update(
            copies=len([r for r in rows if r["status"] == "success"]),
            bytes=sum(r["size"] or 0 for r in rows if r["status"] == "success"),
            missing=len(ids - ok_ids) if d.get("enabled") else 0,
            last={"status": last["status"], "at": last["uploaded_at"] or last["created_at"],
                  "error": last["error"], "backup_id": last["backup_id"]} if last else None,
            pending_deletes=len([r for r in rows if r["status"] == "delete_pending"]),
        )
        out.append(p)
    return out


def start_fetch(bid, wait=False):
    """Traz para o servidor uma cópia que só existe (íntegra) nos destinos externos."""
    b = engine.get_backup(bid)
    if not b or b["status"] != "success" or b["deleted_at"]:
        raise ValueError("Cópia indisponível")
    if not storage.rows("SELECT 1 FROM replicas WHERE backup_id=? AND status='success'", (bid,)):
        raise ValueError("Esta cópia não tem cópias externas")
    engine._acquire()
    try:
        elog = engine.ExecLog("replicate", "manual", bid, b["sgbd"], b["dbname"])
        engine._set_current(reset=True, kind="replicate", trigger="manual", backup_id=bid,
                            execution_id=elog.id, started_at=iso(elog.started), stage="busca",
                            bytes=0, total=b["size"])
    except Exception:
        engine._release()
        raise

    def run():
        try:
            elog("INFO", f"Trazendo a cópia {bid} de um destino externo para o servidor")
            fetch_local(elog, b)
            elog.finish("success")
        except Exception as e:
            elog("ERRO", str(e))
            elog.finish("error")
    if wait:
        try:
            run()
        finally:
            engine._release()
    else:
        engine._spawn(run)
    return elog.id
