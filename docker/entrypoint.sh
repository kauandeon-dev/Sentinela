#!/bin/sh
# Ajusta o dono das pastas montadas (no Linux elas costumam nascer como root) e
# roda o Sentinela como usuário sem privilégios.
set -e
if [ "$(id -u)" = "0" ]; then
    for d in /dados /backups /externo; do
        [ -d "$d" ] && chown sentinela:sentinela "$d" 2>/dev/null || true
    done
    exec setpriv --reuid=sentinela --regid=sentinela --init-groups "$@"
fi
exec "$@"
