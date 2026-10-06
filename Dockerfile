# Sentinela em contêiner: roda igual em Linux, Windows (Docker Desktop) e macOS.
# Já traz os clientes do PostgreSQL (versão mais nova, compatível com servidores
# antigos) e do MariaDB/MySQL — não é preciso instalar nada além do Docker.
FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg tzdata mariadb-client \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && apt-get purge -y curl gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sentinela ./sentinela
COPY LICENSE README.md ./

# Usuário sem privilégios; dados da aplicação e cópias em volumes separados.
RUN useradd --uid 1000 --create-home sentinela \
 && install -d -o sentinela -g sentinela -m 700 /dados /backups /externo
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

ENV SENTINELA_HOME=/dados \
    SENTINELA_BACKUP_DIR=/backups \
    SENTINELA_BIND=0.0.0.0 \
    SENTINELA_PORT=8080 \
    TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1

VOLUME ["/dados", "/backups"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/me', timeout=4)"

CMD ["python", "-m", "sentinela", "serve"]
