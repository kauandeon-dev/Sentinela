"""Caminhos e parâmetros globais, lidos de variáveis de ambiente."""

import os
from pathlib import Path

# Diretório de dados da aplicação (banco SQLite, chave mestra, logs).
# Deve ficar SEPARADO do diretório de backups.
HOME = Path(os.environ.get("SENTINELA_HOME", Path.cwd() / "data")).resolve()

DB_PATH = HOME / "sentinela.db"
KEY_PATH = HOME / "sentinela.key"
# Chaves mestras de outras instalações (importadas para ler cópias antigas).
KEYRING_DIR = HOME / "chaves"
LOG_DIR = HOME / "logs"
EXEC_LOG_DIR = LOG_DIR / "execucoes"
MAIN_LOG = LOG_DIR / "sentinela.log"

DEFAULT_BACKUP_DIR = os.environ.get("SENTINELA_BACKUP_DIR", "/var/backups/sentinela")

HOST = os.environ.get("SENTINELA_BIND", "127.0.0.1")
PORT = int(os.environ.get("SENTINELA_PORT", "8080"))

# Limites da política (definidos no projeto).
RETENTION_MIN, RETENTION_MAX = 1, 10
INTERVAL_MIN, INTERVAL_MAX = 1, 30

# Tempo máximo de conexão ao SGBD (segundos).
CONNECT_TIMEOUT = int(os.environ.get("SENTINELA_CONNECT_TIMEOUT", "30"))

# Intervalo de verificação do agendador (segundos).
SCHEDULER_TICK = int(os.environ.get("SENTINELA_TICK", "30"))

# Cópias externas (regra 3-2-1): tentativas por destino em cada envio e
# espera (s) entre elas. Envios que falharem são retomados a cada hora.
REPLICA_ATTEMPTS = int(os.environ.get("SENTINELA_REPLICA_ATTEMPTS", "3"))
REPLICA_BACKOFF = [float(x) for x in
                   os.environ.get("SENTINELA_REPLICA_BACKOFF", "5,20").split(",") if x.strip()]
# Limite de retomadas automáticas de uma mesma cópia num destino.
REPLICA_MAX_RETRIES = 24
# Tempo máximo (s) de cada operação de rede dos destinos e dos avisos.
NET_TIMEOUT = int(os.environ.get("SENTINELA_NET_TIMEOUT", "20"))

# Avisos: endereço da API do Telegram (alterável para testes) e intervalo
# mínimo (h) entre avisos repetidos do mesmo problema.
TELEGRAM_API = os.environ.get("SENTINELA_TELEGRAM_API", "https://api.telegram.org")
NOTIFY_COOLDOWN_HOURS = 6

# Logs de execução individuais mais antigos que isso são apagados.
EXEC_LOG_KEEP_DAYS = 90


def ensure_dirs():
    for d in (HOME, LOG_DIR, EXEC_LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass
