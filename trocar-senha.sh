#!/usr/bin/env sh
cd "$(dirname "$0")" && docker compose exec -u sentinela sentinela python -m sentinela passwd "${1:-admin}"
