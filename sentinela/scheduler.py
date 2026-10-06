"""Agendador: dispara os backups automáticos e a limpeza por retenção."""

import logging
import threading
import time

from . import engine, notify, replication, settings
from .storage import now

log = logging.getLogger("sentinela")


class Scheduler(threading.Thread):
    def __init__(self, tick=None):
        super().__init__(daemon=True, name="sentinela-scheduler")
        self.tick = tick or settings.SCHEDULER_TICK
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
                    log.info("Backup automático atrasado (agendado para %s) — executando agora", nxt)
                try:
                    engine.start_backup("auto", wait=True)
                except engine.Busy:
                    return  # tenta de novo no próximo ciclo
                except Exception as e:
                    log.error("Backup automático não pôde ser iniciado: %s", e)
                engine.schedule_next(now(), engine.interval_days())

        # Manutenção a cada hora: retenção, logs antigos, envios pendentes para
        # os destinos externos, reenvio de avisos que falharam e alerta de atraso.
        if time.monotonic() - self._last_housekeeping > 3600:
            self._last_housekeeping = time.monotonic()
            self.housekeeping()

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
