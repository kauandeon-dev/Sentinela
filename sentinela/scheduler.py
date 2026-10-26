"""Agendador: dispara os backups automáticos e a limpeza por retenção."""

import logging
import threading
import time
from datetime import timedelta

from . import engine, notify, replication, settings, storage
from .storage import now

log = logging.getLogger("sentinela")


class Scheduler(threading.Thread):
    def __init__(self, tick=None, grace=None):
        super().__init__(daemon=True, name="sentinela-scheduler")
        self.tick = tick or settings.SCHEDULER_TICK
        # Logo após ligar o computador a rede e o banco podem ainda não estar
        # prontos: o backup atrasado espera alguns segundos antes de rodar.
        self.grace = settings.STARTUP_GRACE if grace is None else grace
        self._born = time.monotonic()
        self._stop = threading.Event()
        self._last_housekeeping = 0.0

    def stop(self):
        self._stop.set()

    def run(self):
        log.info("Agendador iniciado (verificação a cada %ss)", self.tick)
        if engine.next_run_at() is None:
            engine.schedule_next()
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:
                log.exception("Erro no agendador")
            self._stop.wait(self.tick)

    def step(self):
        if time.monotonic() - self._born < self.grace:
            return
        current = now()
        nxt = engine.next_run_at()
        if nxt is None:
            nxt = engine.schedule_next(current)

        if current >= nxt:
            if not engine.connection_ready():
                # Sem conexão configurada: apenas reagenda.
                engine.schedule_next(current, engine.interval_days())
            elif not engine.is_busy():
                late = (current - nxt).total_seconds()
                if late > 3600:
                    log.info("Backup automático atrasado (agendado para %s, o computador estava "
                             "desligado ou o Sentinela fechado) — executando agora", nxt)
                ok = False
                try:
                    bid = engine.start_backup("auto", wait=True)
                    ok = (engine.get_backup(bid) or {}).get("status") == "success"
                except engine.Busy:
                    return  # tenta de novo no próximo ciclo
                except Exception as e:
                    log.error("Backup automático não pôde ser iniciado: %s", e)
                self._after_auto(ok)

        # Manutenção a cada hora: retenção, logs antigos, envios pendentes para
        # os destinos externos, reenvio de avisos que falharam e alerta de atraso.
        if time.monotonic() - self._last_housekeeping > 3600:
            self._last_housekeeping = time.monotonic()
            self.housekeeping()

    def _after_auto(self, ok):
        """Sucesso: próximo no horário normal. Falha: nova tentativa em alguns
        minutos (rede ou banco que ainda não subiram, queda passageira), até
        ``AUTO_RETRIES`` vezes; depois, só no próximo horário."""
        tries = int(storage.get_setting("auto_retries") or 0)
        if ok or tries >= settings.AUTO_RETRIES:
            storage.set_setting("auto_retries", 0)
            engine.schedule_next(now(), engine.interval_days())
            return
        tries += 1
        storage.set_setting("auto_retries", tries)
        retry = now() + timedelta(minutes=settings.AUTO_RETRY_MINUTES)
        storage.set_setting("next_run_at", storage.iso(retry))
        log.info("Backup automático falhou — nova tentativa às %s (%d de %d)",
                 retry.strftime("%H:%M"), tries, settings.AUTO_RETRIES)

    def housekeeping(self):
        if engine.is_busy():
            self._last_housekeeping -= 3300  # tenta de novo em ~5 min
            return
        for name, fn in (("retenção", engine.apply_retention),
                         ("limpeza de logs", engine.prune_exec_logs),
                         ("sincronização das cópias externas",
                          lambda: replication.start_sync("auto", wait=True)),
                         ("reenvio de avisos", notify.retry_failed),
                         ("verificação de atraso", engine.check_late)):
            try:
                fn()
            except engine.Busy:
                pass
            except Exception:
                log.exception("Falha na manutenção (%s)", name)
