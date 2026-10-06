#!/usr/bin/env sh
# Inicia o Sentinela em Docker (Linux/macOS) e mostra a senha do primeiro acesso.
set -e
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo "Instale o Docker: https://docs.docker.com/get-docker/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "O Docker não está rodando (ou falta permissão: use sudo)."; exit 1; }
mkdir -p dados backups externo
echo "Preparando e iniciando (a primeira vez demora alguns minutos)..."
docker compose up -d --build
i=0
until docker compose exec -T sentinela python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/me', timeout=2)" >/dev/null 2>&1 \
      || [ $i -ge 60 ]; do i=$((i+1)); sleep 2; done
echo
docker compose logs sentinela 2>/dev/null | grep "Primeiro acesso" || echo "Use a senha que você já definiu."
echo "Painel: http://localhost:8080  (usuário: admin)"
echo "Parar: docker compose stop · Trocar senha: ./trocar-senha.sh"
