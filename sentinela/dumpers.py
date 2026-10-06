"""Adaptadores para os SGBDs suportados (PostgreSQL e MariaDB/MySQL).

Usam os clientes oficiais de linha de comando (pg_dump/psql e
mariadb-dump/mariadb), que precisam estar instalados no servidor.
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager

from . import compat, settings

SGBD_LABEL = {"postgres": "PostgreSQL", "mariadb": "MariaDB (MySQL)"}
DEFAULT_PORT = {"postgres": "5432", "mariadb": "3306"}


class ToolNotFound(Exception):
    pass


# No Windows, os instaladores do PostgreSQL e do MariaDB/MySQL não colocam os
# clientes no PATH: procuramos nas pastas padrão (a versão mais nova primeiro).
_WINDOWS_DIRS = ("PostgreSQL/*/bin", "MariaDB */bin", "MySQL/MySQL Server */bin")


def _version_key(path):
    return [int(x) for x in re.findall(r"\d+", path)]


def _windows_candidates(name):
    roots = {os.environ.get(v) for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")}
    found = []
    for root in filter(None, roots):
        for pattern in _WINDOWS_DIRS:
            found += glob.glob(os.path.join(root, pattern, name + ".exe"))
    return sorted(found, key=_version_key, reverse=True)


def _which(*names, env=None):
    """Acha o cliente pelo nome preferido primeiro (``mariadb-dump`` antes de
    ``mysqldump``), no PATH e, no Windows, nas pastas de instalação padrão — assim
    um ``mysqldump`` do MySQL no PATH não é usado se o MariaDB estiver instalado."""
    if env and os.environ.get(env):
        return os.environ[env]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
        if compat.IS_WINDOWS:
            c = _windows_candidates(n)
            if c:
                return c[0]
    hint = ("Instale o PostgreSQL ou o MariaDB (os clientes vêm junto) ou informe o caminho "
            "nas variáveis SENTINELA_PG_DUMP/SENTINELA_PSQL ou SENTINELA_MYSQLDUMP/SENTINELA_MYSQL."
            if compat.IS_WINDOWS else "Instale o pacote cliente do SGBD.")
    raise ToolNotFound(f"Cliente '{names[0]}' não encontrado no servidor. {hint}")


class Adapter:
    sgbd = ""

    def __init__(self, conn):
        self.host = conn.get("host") or "localhost"
        self.port = str(conn.get("port") or DEFAULT_PORT[self.sgbd])
        self.dbname = conn["dbname"]
        self.user = conn.get("user") or ""
        self.password = conn.get("password") or ""

    @property
    def label(self):
        return SGBD_LABEL[self.sgbd]

    @contextmanager
    def dump_cmd(self):
        raise NotImplementedError

    @contextmanager
    def restore_cmd(self):
        raise NotImplementedError

    @contextmanager
    def query_cmd(self, sql):
        raise NotImplementedError

    def query(self, sql):
        """Executa uma consulta e devolve a saída em texto (erro => RuntimeError)."""
        with self.query_cmd(sql) as (cmd, env):
            p = subprocess.run(
                cmd, env=env, capture_output=True, text=True,
                timeout=settings.CONNECT_TIMEOUT + 5,
            )
        if p.returncode != 0:
            raise RuntimeError(clean_stderr(p.stderr) or f"código de saída {p.returncode}")
        return p.stdout.strip()

    def test(self):
        """Executa uma consulta simples e devolve a versão do servidor."""
        out = self.query("SELECT version()")
        return out.splitlines()[0] if out else ""

    def preflight(self):
        """Confere, antes do dump, se o usuário enxerga tudo o que será copiado.

        Retorna (avisos, esperado) — ``esperado`` traz contagens que serão
        conferidas no dump pronto."""
        return [], {}


class PostgresAdapter(Adapter):
    sgbd = "postgres"

    def _env(self):
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password
        env["PGCONNECT_TIMEOUT"] = str(settings.CONNECT_TIMEOUT)
        env.setdefault("PGAPPNAME", "sentinela")
        return env

    def _conn_args(self):
        return ["-h", self.host, "-p", self.port, "-U", self.user, "-w"]

    @contextmanager
    def dump_cmd(self):
        # Formato texto (SQL puro) com DROP ... IF EXISTS, para que a
        # restauração substitua os objetos existentes.
        cmd = [_which("pg_dump", env="SENTINELA_PG_DUMP"), *self._conn_args(),
               "-d", self.dbname, "--format=plain", "--clean", "--if-exists",
               "--no-owner", "--encoding=UTF8"]
        yield cmd, self._env()

    @contextmanager
    def restore_cmd(self):
        cmd = [_which("psql", env="SENTINELA_PSQL"), *self._conn_args(),
               "-d", self.dbname, "-q", "-X", "-v", "ON_ERROR_STOP=1", "--single-transaction"]
        yield cmd, self._env()

    @contextmanager
    def query_cmd(self, sql):
        cmd = [_which("psql", env="SENTINELA_PSQL"), *self._conn_args(),
               "-d", self.dbname, "-X", "-tA", "-c", sql]
        yield cmd, self._env()


class MariaDBAdapter(Adapter):
    sgbd = "mariadb"

    @contextmanager
    def _defaults_file(self):
        # A senha vai num arquivo temporário (0600) para não aparecer na
        # lista de processos nem em variáveis de ambiente.
        fd, path = tempfile.mkstemp(prefix="sentinela-", suffix=".cnf")
        try:
            with os.fdopen(fd, "w") as f:
                def q(v):
                    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
                f.write(f"[client]\nuser={q(self.user)}\npassword={q(self.password)}\n"
                        f"host={q(self.host)}\nport={int(self.port)}\n")
            yield path
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @contextmanager
    def dump_cmd(self):
        with self._defaults_file() as cnf:
            tool = _which("mariadb-dump", "mysqldump", env="SENTINELA_MYSQLDUMP")
            cmd = [tool, f"--defaults-extra-file={cnf}", "--protocol=TCP",
                   "--single-transaction", "--quick", "--routines", "--triggers",
                   "--events", "--add-drop-table", "--hex-blob"]
            if _is_mysql8_dump(tool):
                # O mysqldump do MySQL 8 consulta COLUMN_STATISTICS, que não existe
                # no MariaDB nem em MySQL antigos: desliga essa consulta.
                cmd.append("--column-statistics=0")
            cmd.append(self.dbname)
            yield cmd, os.environ.copy()

    @contextmanager
    def restore_cmd(self):
        with self._defaults_file() as cnf:
            cmd = [_which("mariadb", "mysql", env="SENTINELA_MYSQL"),
                   f"--defaults-extra-file={cnf}", "--protocol=TCP",
                   f"--connect-timeout={settings.CONNECT_TIMEOUT}", self.dbname]
            yield cmd, os.environ.copy()

    @contextmanager
    def query_cmd(self, sql):
        with self._defaults_file() as cnf:
            cmd = [_which("mariadb", "mysql", env="SENTINELA_MYSQL"),
                   f"--defaults-extra-file={cnf}", "--protocol=TCP",
                   f"--connect-timeout={settings.CONNECT_TIMEOUT}", "-N", "-B", "-D", self.dbname, "-e", sql]
            yield cmd, os.environ.copy()

    def preflight(self):
        """O mariadb-dump OMITE EM SILÊNCIO procedures/functions que o usuário não
        consegue enxergar (sem erro, código 0). Aqui contamos as rotinas direto em
        mysql.proc para conferir o dump depois; sem permissão, avisamos."""
        warnings, expected = [], {}
        try:
            expected["routines"] = int(self.query(
                "SELECT COUNT(*) FROM mysql.proc WHERE db = DATABASE()") or 0)
        except (RuntimeError, ValueError) as e:
            if "doesn't exist" in str(e):
                # MySQL 8 não tem mysql.proc: não há como contar por fora; sem alarme falso.
                return warnings, expected
            warnings.append(
                "Não foi possível conferir procedures/functions: sem permissão de leitura em "
                "mysql.proc. Rotinas criadas por outros usuários podem ficar fora da cópia. "
                "Conceda: GRANT SELECT ON mysql.proc TO 'usuario'@'host'")
        return warnings, expected


_tool_versions = {}


def _is_mysql8_dump(tool):
    if tool not in _tool_versions:
        try:
            out = subprocess.run([tool, "--version"], capture_output=True, text=True,
                                 timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        _tool_versions[tool] = out
    out = _tool_versions[tool]
    m = re.search(r"Ver (\d+)\.", out) or re.search(r"Distrib (\d+)\.", out)
    return "MariaDB" not in out and bool(m) and int(m.group(1)) >= 8


def adapter_for(conn):
    sgbd = conn.get("sgbd")
    if sgbd == "postgres":
        return PostgresAdapter(conn)
    if sgbd == "mariadb":
        return MariaDBAdapter(conn)
    raise ValueError(f"SGBD não suportado: {sgbd}")


# Dicas para erros de permissão comuns (anexadas à mensagem de erro).
PRIVILEGE_HINTS = (
    ("insufficient privileges to SHOW CREATE",
     "o usuário de backup precisa ler o código de procedures/functions criadas por outro usuário: "
     "GRANT SELECT ON mysql.proc TO 'usuario'@'host' (MariaDB até 11.2) ou "
     "GRANT SHOW CREATE ROUTINE ON banco.* TO 'usuario'@'host' (MariaDB 11.3+)"),
    ("Access denied; you need (at least one of) the PROCESS privilege",
     "conceda: GRANT PROCESS ON *.* TO 'usuario'@'host' (ou atualize o cliente mariadb-dump)"),
    ("permission denied for",
     "o usuário do PostgreSQL não tem leitura em todos os objetos: "
     "GRANT pg_read_all_data TO usuario (PostgreSQL 14+) ou use o dono do banco"),
    ("must be owner of",
     "para restaurar no PostgreSQL, use o dono do banco (ou um usuário com os mesmos privilégios)"),
)


def hint_for(message):
    for needle, hint in PRIVILEGE_HINTS:
        if needle.lower() in (message or "").lower():
            return f" — dica: {hint}"
    return ""


def clean_stderr(text, limit=400):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    # Avisos inofensivos dos clientes
    lines = [ln for ln in lines if "Using a password on the command line" not in ln]
    msg = " | ".join(lines[-3:])
    return msg[:limit]
