#!/usr/bin/env bash
# Desmonta o servidor remoto simulado criado por setup.sh.
set -uo pipefail
NS=sentinela-remoto
BASE=/tmp/sentinela-remoto
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)

[ -f "$BASE/sshd/sshd.pid" ] && kill "$(cat "$BASE/sshd/sshd.pid")" 2>/dev/null
[ -f "$BASE/sshd/sshd-local.pid" ] && kill "$(cat "$BASE/sshd/sshd-local.pid")" 2>/dev/null
[ -f "$BASE/maria/maria.pid" ] && kill "$(cat "$BASE/maria/maria.pid")" 2>/dev/null
ip netns exec "$NS" su postgres -c "$PGBIN/pg_ctl -D $BASE/pg -m fast stop" >/dev/null 2>&1
sleep 1
mountpoint -q "$BASE/cheio" && umount "$BASE/cheio"
ip link del srv0 2>/dev/null
ip netns del "$NS" 2>/dev/null
rm -rf "/etc/netns/$NS"
if [ "${1:-}" = "--purge" ]; then rm -rf "$BASE"; fi
echo "Servidor remoto removido."
