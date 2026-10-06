#!/usr/bin/env bash
# Monta um "servidor remoto" simulado para testar o túnel SSH do Sentinela.
#
# Cria um namespace de rede Linux (sentinela-remoto, IP 10.77.0.2) com:
#   - sshd na porta 22
#   - PostgreSQL e MariaDB escutando SOMENTE em 127.0.0.1 dentro do namespace
#     (inacessíveis a partir do host: o único caminho é o túnel SSH)
#   - usuários SSH com cenários diferentes (senha, chaves, restrições)
#
# Requer root, iproute2, openssh-server, postgresql e mariadb-server instalados.
# Uso:  sudo tests/remote/setup.sh        (idempotente)
#       sudo tests/remote/teardown.sh
set -euo pipefail

NS=sentinela-remoto
BASE=/tmp/sentinela-remoto
KEYS=/tmp/sentinela-remoto/keys
HOST_IP=10.77.0.1
REMOTE_IP=10.77.0.2
PGBIN=$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)
NSX="ip netns exec $NS"

mkdir -p "$BASE" "$KEYS"
chmod 755 "$BASE"

# ------------------------------------------------------------------ rede
if ! ip netns list | grep -qw "$NS"; then
    ip netns add "$NS"
    ip link add srv0 type veth peer name srv1
    ip link set srv1 netns "$NS"
    ip addr add "$HOST_IP/24" dev srv0
    ip link set srv0 up
    $NSX ip addr add "$REMOTE_IP/24" dev srv1
    $NSX ip link set srv1 up
    $NSX ip link set lo up
fi
# /etc/hosts próprio do "servidor remoto" (ip netns exec monta por cima de /etc/hosts)
mkdir -p "/etc/netns/$NS"
printf '127.0.0.1 localhost db.interno\n::1 localhost\n' > "/etc/netns/$NS/hosts"

# --------------------------------------------------------------- usuários
for u in tunel restrito semforward sochave cofre; do
    id "$u" >/dev/null 2>&1 || useradd -m -s /bin/bash "$u"
done
echo 'tunel:SenhaSsh#1'      | chpasswd
echo 'semforward:SenhaSsh#1' | chpasswd
echo 'sochave:SenhaSsh#1'    | chpasswd
echo 'restrito:SenhaSsh#1'   | chpasswd
echo 'cofre:CofreSftp#1'     | chpasswd

# Destinos SFTP (cópias externas, regra 3-2-1): pasta do usuário "cofre" e um
# volume minúsculo (256 KB) para simular disco cheio no servidor remoto.
mkdir -p "$BASE/cheio"
mountpoint -q "$BASE/cheio" || mount -t tmpfs -o size=256k tmpfs "$BASE/cheio"
chown cofre "$BASE/cheio"

# ------------------------------------------------------------------ chaves
gen() {  # gen <nome> <tipo> [bits] [senha] [formato]
    local name=$1 type=$2 bits=${3:-} pass=${4:-} fmt=${5:-}
    [ -f "$KEYS/$name" ] && return
    local args=(-q -t "$type" -N "$pass" -f "$KEYS/$name" -C "$name@teste")
    [ -n "$bits" ] && args+=(-b "$bits")
    [ -n "$fmt" ] && args+=(-m "$fmt")
    ssh-keygen "${args[@]}"
}
gen ed25519        ed25519
gen rsa            rsa 3072
gen rsa_pem        rsa 2048 "" PEM
gen ecdsa          ecdsa 256
gen ed25519_senha  ed25519 "" "frase-da-chave"
gen rsa_pem_senha  rsa 2048 "frase-da-chave" PEM
gen nao_autorizada ed25519
chmod 644 "$KEYS"/*

auth() {  # auth <usuario> <linhas authorized_keys...>
    local u=$1; shift
    local h; h=$(getent passwd "$u" | cut -d: -f6)
    mkdir -p "$h/.ssh"
    printf '%s\n' "$@" > "$h/.ssh/authorized_keys"
    chown -R "$u:$u" "$h/.ssh"; chmod 700 "$h/.ssh"; chmod 600 "$h/.ssh/authorized_keys"
}
pub() { cat "$KEYS/$1.pub"; }
auth tunel "$(pub ed25519)" "$(pub rsa)" "$(pub rsa_pem)" "$(pub ecdsa)" \
           "$(pub ed25519_senha)" "$(pub rsa_pem_senha)"
auth sochave "$(pub ed25519)"
auth cofre "$(pub ed25519)"
auth semforward "$(pub ed25519)"
# chave que só pode abrir túnel para o PostgreSQL
auth restrito "restrict,port-forwarding,permitopen=\"localhost:5432\" $(pub ed25519)"

# -------------------------------------------------------------------- sshd
mkdir -p /run/sshd "$BASE/sshd"
[ -f "$BASE/sshd/host_ed25519" ] || ssh-keygen -q -t ed25519 -N '' -f "$BASE/sshd/host_ed25519"
cat > "$BASE/sshd/sshd_config" <<EOF
Port 22
ListenAddress 0.0.0.0
HostKey $BASE/sshd/host_ed25519
PidFile $BASE/sshd/sshd.pid
UsePAM yes
PasswordAuthentication yes
PubkeyAuthentication yes
KbdInteractiveAuthentication no
AllowTcpForwarding yes
MaxStartups 50:30:100
MaxSessions 50
Subsystem sftp internal-sftp
Match User semforward
    AllowTcpForwarding no
Match User sochave
    PasswordAuthentication no
EOF
if [ ! -f "$BASE/sshd/sshd.pid" ] || ! kill -0 "$(cat "$BASE/sshd/sshd.pid")" 2>/dev/null; then
    $NSX /usr/sbin/sshd -f "$BASE/sshd/sshd_config"
fi

# sshd "local" (127.0.0.1:2222, fora do namespace), usado por tests/test_ssh.py
sed -e 's/^Port 22$/Port 2222/' -e 's/^ListenAddress 0.0.0.0$/ListenAddress 127.0.0.1/' \
    -e "s#^PidFile .*#PidFile $BASE/sshd/sshd-local.pid#" \
    "$BASE/sshd/sshd_config" > "$BASE/sshd/sshd_local_config"
if [ ! -f "$BASE/sshd/sshd-local.pid" ] || ! kill -0 "$(cat "$BASE/sshd/sshd-local.pid")" 2>/dev/null; then
    /usr/sbin/sshd -f "$BASE/sshd/sshd_local_config"
fi

# -------------------------------------------------------------- PostgreSQL
PGDATA=$BASE/pg
if [ ! -d "$PGDATA" ]; then
    mkdir -p "$PGDATA"; chown postgres "$PGDATA"
    echo pgadmin > "$BASE/pgpass"; chown postgres "$BASE/pgpass"
    su postgres -c "$PGBIN/initdb -D $PGDATA -A scram-sha-256 --pwfile=$BASE/pgpass -E UTF8 >/dev/null"
fi
if ! $NSX su postgres -c "$PGBIN/pg_ctl -D $PGDATA status" >/dev/null 2>&1; then
    $NSX su postgres -c "$PGBIN/pg_ctl -D $PGDATA -l $PGDATA/servidor.log -w \
        -o \"-c listen_addresses=127.0.0.1 -p 5432 -k $PGDATA\" start" >/dev/null
fi
PSQL="$NSX env PGPASSWORD=pgadmin psql -h 127.0.0.1 -U postgres -qtA"
if ! $PSQL -c "select 1 from pg_roles where rolname='backup_user'" | grep -q 1; then
    $PSQL -c "CREATE ROLE backup_user LOGIN PASSWORD 'Remota#2026'"
    $PSQL -c "CREATE DATABASE loja_remota OWNER backup_user ENCODING 'UTF8' TEMPLATE template0"
    $NSX env PGPASSWORD='Remota#2026' psql -h 127.0.0.1 -U backup_user -d loja_remota -q <<'SQL'
CREATE TABLE clientes (id serial PRIMARY KEY, nome text NOT NULL, cidade text, criado_em timestamptz DEFAULT now());
INSERT INTO clientes (nome, cidade) VALUES
  ('Ana Souza', 'São Lourenço do Oeste'), ('João Pereira', 'Chapecó'),
  ('Maria Çedilha', 'Florianópolis'), ('Émile Ñandú', 'Xanxerê');
CREATE TABLE ordens_servico (
  id bigserial PRIMARY KEY, cliente_id int REFERENCES clientes(id),
  descricao text, valor numeric(12,2), aberta_em timestamptz DEFAULT now());
INSERT INTO ordens_servico (cliente_id, descricao, valor)
  SELECT 1 + (g % 4), 'OS ' || g || ' — troca de equipamento / visita técnica ' || md5(g::text), (g % 1000) * 1.37
  FROM generate_series(1, 200000) g;
CREATE VIEW resumo AS SELECT cliente_id, count(*) n, sum(valor) total FROM ordens_servico GROUP BY 1;
CREATE FUNCTION total_cliente(int) RETURNS numeric LANGUAGE sql AS $$ SELECT sum(valor) FROM ordens_servico WHERE cliente_id = $1 $$;
-- tabela grande para teste de volume (~120 MB de dump)
CREATE TABLE eventos (id bigserial PRIMARY KEY, payload text);
INSERT INTO eventos (payload) SELECT repeat(md5(g::text), 20) FROM generate_series(1, 180000) g;
SQL
fi

# ----------------------------------------------------------------- MariaDB
MDATA=$BASE/maria
if [ ! -d "$MDATA/mysql" ]; then
    mkdir -p "$MDATA"; chown mysql:mysql "$MDATA"
    mariadb-install-db --user=mysql --datadir="$MDATA" --auth-root-authentication-method=socket >/dev/null
fi
if ! [ -S "$MDATA/maria.sock" ] || ! mariadb --socket="$MDATA/maria.sock" -uroot -e 'select 1' >/dev/null 2>&1; then
    $NSX setsid mariadbd --user=mysql --datadir="$MDATA" --socket="$MDATA/maria.sock" \
        --port=3306 --bind-address=127.0.0.1 --pid-file="$MDATA/maria.pid" \
        --log-error="$MDATA/maria.err" --skip-log-bin >/dev/null 2>&1 < /dev/null &
    for _ in $(seq 1 30); do
        mariadb --socket="$MDATA/maria.sock" -uroot -e 'select 1' >/dev/null 2>&1 && break
        sleep 1
    done
fi
MY="mariadb --socket=$MDATA/maria.sock -uroot --default-character-set=utf8mb4"
if ! $MY -N -e "select 1 from mysql.user where user='backup_user'" | grep -q 1; then
    $MY <<'SQL'
CREATE DATABASE loja_remota CHARACTER SET utf8mb4;
CREATE USER 'backup_user'@'127.0.0.1' IDENTIFIED BY 'Remota#2026';
CREATE USER 'backup_user'@'localhost' IDENTIFIED BY 'Remota#2026';
GRANT ALL ON loja_remota.* TO 'backup_user'@'127.0.0.1';
GRANT ALL ON loja_remota.* TO 'backup_user'@'localhost';
GRANT PROCESS ON *.* TO 'backup_user'@'127.0.0.1';
GRANT PROCESS ON *.* TO 'backup_user'@'localhost';
GRANT SELECT ON mysql.proc TO 'backup_user'@'127.0.0.1';
GRANT SELECT ON mysql.proc TO 'backup_user'@'localhost';
FLUSH PRIVILEGES;
USE loja_remota;
CREATE TABLE clientes (id INT PRIMARY KEY AUTO_INCREMENT, nome VARCHAR(100), cidade VARCHAR(80));
INSERT INTO clientes (nome, cidade) VALUES ('Ana Souza','São Lourenço do Oeste'),('João Pereira','Chapecó'),('Émile Ñandú','Xanxerê');
CREATE TABLE radacct (radacctid BIGINT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(64), acctinputoctets BIGINT, acctoutputoctets BIGINT, acctstarttime DATETIME);
INSERT INTO radacct (username, acctinputoctets, acctoutputoctets, acctstarttime)
  SELECT CONCAT('cliente', seq), seq * 1024, seq * 2048, NOW() - INTERVAL seq MINUTE FROM seq_1_to_50000;
CREATE TRIGGER trg_cli BEFORE INSERT ON clientes FOR EACH ROW SET NEW.nome = TRIM(NEW.nome);
CREATE VIEW v_consumo AS SELECT username, acctinputoctets + acctoutputoctets AS total FROM radacct;
CREATE PROCEDURE sp_total(OUT n BIGINT) SELECT COUNT(*) INTO n FROM radacct;
SQL
fi

echo "Servidor remoto pronto: ssh ${REMOTE_IP}:22 · PostgreSQL/MariaDB em 127.0.0.1 dentro do namespace ${NS}"
echo "Chaves de teste em ${KEYS}"
