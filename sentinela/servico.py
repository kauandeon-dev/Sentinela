"""Execução em segundo plano: o Sentinela inicia junto com o computador, sem
janela, e o agendador retoma os backups automáticos — inclusive o que ficou
para trás enquanto o computador estava desligado.

- **Uma instância por pasta de dados.** Uma trava (``painel.lock``) fica
  presa enquanto o processo vive; ``painel.json`` guarda o endereço do painel.
  A segunda abertura só aponta para a que já está rodando.
- **Início automático, sem administrador:**
    Windows  valor "Sentinela" na chave Executar do usuário
             (HKCU\\...\\CurrentVersion\\Run) → ``pythonw``, sem janela, ao entrar
             no Windows
    Linux    serviço systemd do usuário (``~/.config/systemd/user``)
  Docker, a tarefa do Windows (deploy/windows) e o serviço do sistema
  (deploy/sentinela.service) já reiniciam o Sentinela sozinhos: definem
  ``SENTINELA_GERENCIADO`` e o painel só mostra quem cuida disso.
- **Encerrar:** um arquivo de pedido de parada na pasta de dados (``python -m
  sentinela servico parar`` ou o botão do painel); o processo espera o backup
  em andamento terminar.
"""

import _thread
import atexit
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import compat, settings

NAME = "Sentinela"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
UNIT = "sentinela.service"
LAUNCHER = "sentinela-segundo-plano.pyw"

# Variáveis copiadas para o lançador do início automático (o processo iniciado
# pelo sistema não herda o ambiente de quem ativou).
_SKIP_ENV = {"SENTINELA_NO_BROWSER", "SENTINELA_PORTATIL", "SENTINELA_GERENCIADO"}
_EXTRA_ENV = ("MARIADB_PLUGIN_DIR", "TZ", "PGCLIENTENCODING")

BACKGROUND = False      # este processo foi iniciado em segundo plano
handed_off = False      # esta janela passou a vez para o segundo plano
_instance_fd = None
_info = {}


def _lock_path():
    return settings.HOME / "painel.lock"


def _info_path():
    return settings.HOME / "painel.json"


def _stop_path():
    return settings.HOME / "parar.pedido"


# ============================================================ instância única

def acquire_instance(wait=0):
    """Torna este processo a instância do Sentinela desta pasta de dados.

    ``wait`` (s): espera a anterior sair (troca da janela para o segundo plano).
    Retorna False se outra instância continua rodando."""
    global _instance_fd
    if _instance_fd is not None:
        return True
    settings.ensure_dirs()
    deadline = time.monotonic() + wait
    while True:
        fd = os.open(_lock_path(), os.O_CREAT | os.O_RDWR | compat.O_BINARY, 0o600)
        try:
            compat.lock_nb(fd)
        except OSError:
            os.close(fd)
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.5)
            continue
        _instance_fd = fd
        # Registrada antes de qualquer outro atexit (ex.: desligar o banco de
        # demonstração), é a última a rodar: ninguém assume a pasta antes disso.
        atexit.register(release_instance)
        return True


def release_instance():
    global _instance_fd
    if _instance_fd is None:
        return
    try:
        _info_path().unlink()
    except OSError:
        pass
    try:
        compat.unlock(_instance_fd)
        os.close(_instance_fd)
    except OSError:
        pass
    _instance_fd = None


def running_instance():
    """Instância rodando nesta pasta de dados: dict (url, pid, background...)
    ou None. Funciona também de outro processo (CLI, atalhos)."""
    if _instance_fd is not None:
        return dict(_info)
    if not _lock_path().exists():
        return None
    fd = os.open(_lock_path(), os.O_RDWR | compat.O_BINARY)
    try:
        compat.lock_nb(fd)
    except OSError:
        try:
            return json.loads(_info_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    else:
        compat.unlock(fd)
        return None
    finally:
        os.close(fd)


def started(url, port, on_stop):
    """Chamado quando o painel está no ar: publica o endereço e passa a atender
    pedidos de parada."""
    from . import storage
    from .storage import iso, now
    _info.update(url=url, port=port, pid=os.getpid(), background=BACKGROUND,
                 started_at=iso(now()), home=str(settings.HOME))
    tmp = _info_path().with_suffix(".tmp")
    fd = compat.open_private(tmp)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(_info, f)
    os.replace(tmp, _info_path())
    storage.set_setting("panel_port", port)
    try:
        _stop_path().unlink()  # pedido antigo, de antes desta execução
    except OSError:
        pass
    threading.Thread(target=_watch_stop, args=(on_stop,), daemon=True,
                     name="sentinela-parada").start()


def _watch_stop(on_stop):
    from . import engine
    while True:
        time.sleep(1)
        if not _stop_path().exists():
            continue
        try:
            _stop_path().unlink()
        except OSError:
            pass
        if engine.is_busy():
            engine.log.info("Encerramento pedido: aguardando a execução em andamento terminar")
            while engine.is_busy():
                time.sleep(1)
        engine.log.info("Sentinela encerrado a pedido")
        on_stop()
        return


def request_stop():
    """Pede à instância desta pasta de dados que encerre. False se nenhuma roda."""
    inst = running_instance()
    if inst is None:
        return False
    _stop_path().write_text(str(time.time()), encoding="ascii")
    return True


def wait_exit(pid, timeout=30):
    """Espera o processo ``pid`` terminar (ex.: antes de apagar os arquivos do
    programa no desinstalador). True se terminou."""
    if not pid:
        return True
    if compat.IS_WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
        if not h:
            return True  # já terminou
        try:
            return k32.WaitForSingleObject(h, int(timeout * 1000)) == 0
        finally:
            k32.CloseHandle(h)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.2)
    return False


def stop_self():
    """Encerra o servidor deste processo (o laço do waitress roda na thread
    principal e sai com KeyboardInterrupt)."""
    _thread.interrupt_main(signal.SIGINT)


def handle_interrupt():
    """Garante o KeyboardInterrupt de ``stop_self`` e do Ctrl+C: um processo
    iniciado em segundo plano pelo shell (ou pelo Windows) pode ter herdado o
    SIGINT ignorado."""
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, signal.default_int_handler)


# ===================================================================== porta

def _port_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not compat.IS_WINDOWS:  # no Windows, SO_REUSEADDR deixaria "roubar" a porta
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host, preferred, wait=0, tries=20):
    """``preferred`` se estiver livre (esperando até ``wait`` s) ou a próxima livre."""
    deadline = time.monotonic() + wait
    while not _port_free(host, preferred):
        if time.monotonic() >= deadline:
            for port in range(preferred + 1, preferred + tries):
                if _port_free(host, port):
                    return port
            raise OSError(f"Nenhuma porta livre entre {preferred} e {preferred + tries - 1}")
        time.sleep(0.5)
    return preferred


def preferred_port():
    """Porta do segundo plano: a definida no ambiente ou a última usada."""
    from . import storage
    if os.environ.get("SENTINELA_PORT"):
        return int(os.environ["SENTINELA_PORT"])
    try:
        return int(storage.get_setting("panel_port") or settings.PORT)
    except (TypeError, ValueError):
        return settings.PORT


# ============================================================ segundo plano

def background_mode():
    """Prepara o processo para rodar sem janela: saída num arquivo de log e,
    no Windows, programas chamados (pg_dump, mariadb-dump...) sem abrir janelas."""
    global BACKGROUND
    if BACKGROUND:
        return
    BACKGROUND = True
    settings.ensure_dirs()
    path = settings.LOG_DIR / "segundo-plano.log"
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            os.replace(path, path.with_suffix(".log.1"))
    except OSError:
        pass
    out = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stderr = out
    if compat.IS_WINDOWS:
        _no_console_windows()


def _no_console_windows():
    """Sem console (pythonw), cada programa de linha de comando chamado abriria
    uma janela preta. CREATE_NO_WINDOW em toda chamada que não escolheu flags."""
    if getattr(subprocess.Popen, "_sentinela_sem_janela", False):
        return
    original = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        original(self, *args, **kwargs)
    subprocess.Popen.__init__ = init
    subprocess.Popen._sentinela_sem_janela = True


def _pythonw():
    exe = Path(sys.executable)
    if compat.IS_WINDOWS:
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def command():
    """Comando que inicia o Sentinela em segundo plano.

    Versão portátil: o próprio portatil.py, que se localiza sozinho (a pasta
    pode mudar de lugar). Demais instalações: um lançador na pasta de dados
    com as variáveis de ambiente atuais."""
    portatil = os.environ.get("SENTINELA_PORTATIL")
    if portatil:
        return [_pythonw(), portatil, "--servico"]
    return [_pythonw(), str(settings.HOME / LAUNCHER)]


def _write_launcher():
    env = {k: v for k, v in os.environ.items()
           if (k.startswith("SENTINELA_") and k not in _SKIP_ENV) or k in _EXTRA_ENV}
    env["SENTINELA_HOME"] = str(settings.HOME)
    env.pop("SENTINELA_PORT", None)  # a porta preferida fica salva no banco
    root = str(Path(__file__).resolve().parent.parent)
    src = (
        "# Gerado pelo Sentinela ao ativar o início automático: inicia o painel e o\n"
        "# agendador em segundo plano. Desative pelo painel ou com\n"
        "#   python -m sentinela servico desativar\n"
        "import os\nimport sys\n\n"
        f"os.environ.update({env!r})\n"
        f"sys.path.insert(0, {root!r})\n"
        f"os.chdir({root!r})\n"
        "from sentinela.__main__ import main\n\n"
        "sys.argv = ['sentinela', 'serve', '--background']\n"
        "main()\n")
    settings.ensure_dirs()
    path = Path(command()[1])
    fd = compat.open_private(path)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def spawn_background(port=None):
    """Inicia agora o processo de segundo plano, desligado desta janela."""
    cmd = command()
    if not os.environ.get("SENTINELA_PORTATIL"):
        _write_launcher()
    env = dict(os.environ)
    if port:
        env["SENTINELA_PORT"] = str(port)
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              env=env, cwd=str(settings.HOME), close_fds=True)
    if compat.IS_WINDOWS:
        detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:  # sai também do "job" da janela, que o Windows encerra junto com ela
            return subprocess.Popen(cmd, creationflags=detached | 0x01000000, **kw)
        except OSError:
            return subprocess.Popen(cmd, creationflags=detached, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def switch_to_background(port):
    """Troca a janela pelo segundo plano: inicia o processo novo (que espera
    esta instância sair) e encerra esta assim que nenhuma execução estiver em
    andamento. O painel volta no mesmo endereço em poucos segundos."""
    from . import engine

    def run():
        time.sleep(1)  # deixa a resposta chegar ao navegador
        while engine.is_busy():
            time.sleep(1)
        global handed_off
        spawn_background(port)
        handed_off = True
        engine.log.info("Sentinela passou a rodar em segundo plano")
        stop_self()
    threading.Thread(target=run, daemon=True, name="sentinela-troca").start()


# ======================================================= início automático

def managed():
    """Quem já reinicia o Sentinela sozinho (Docker, tarefa do Windows, systemd
    do sistema), ou None."""
    v = os.environ.get("SENTINELA_GERENCIADO")
    if v:
        return v
    if os.path.exists("/.dockerenv"):
        return "Docker (reinicia sozinho)"
    return None


def _same(a, b):
    if a is None or b is None:
        return False
    return a.lower() == b.lower() if compat.IS_WINDOWS else a == b


def _target_exists(cmdline):
    """O script que o comando registrado chama ainda existe? (pasta movida)"""
    try:
        parts = shlex.split(cmdline, posix=not compat.IS_WINDOWS)
    except ValueError:
        return False
    parts = [p.strip('"') for p in parts]
    return len(parts) >= 2 and os.path.exists(parts[0]) and os.path.exists(parts[1])


# ------------------------------------------------------------------ Windows

def _win_read(path, name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _win_install(cmdline):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, cmdline)
    _win_delete(APPROVED_KEY)  # reativa, se tinha sido desativado no Gerenciador de Tarefas


def _win_delete(path):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except OSError:
        pass


def _win_blocked():
    """Desativado pelo usuário na aba Inicializar do Gerenciador de Tarefas."""
    data = _win_read(APPROVED_KEY, NAME)
    return bool(data) and isinstance(data, bytes) and data[0] % 2 == 1


# -------------------------------------------------------------------- Linux

def _unit_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def _unit_text(cmd):
    exec_start = " ".join(shlex.quote(c) for c in cmd).replace("%", "%%")
    return ("# Gerado pelo Sentinela (início automático). Desative pelo painel ou com\n"
            "#   python -m sentinela servico desativar\n"
            "[Unit]\n"
            "Description=Sentinela - backups automáticos de bancos de dados\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={exec_start}\n"
            "Restart=on-failure\n"
            "RestartSec=30\n"
            "UMask=0077\n\n"
            "[Install]\n"
            "WantedBy=default.target\n")


def _systemctl(*args):
    r = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"systemctl {' '.join(args)} falhou")
    return r.stdout


def _linux_registered():
    unit = _unit_dir() / UNIT
    if not unit.exists() or not (_unit_dir() / "default.target.wants" / UNIT).exists():
        return None
    for line in unit.read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            return line[len("ExecStart="):].replace("%%", "%")
    return None


# -------------------------------------------------------------------- comum

def _cmdline(cmd):
    if compat.IS_WINDOWS:  # caminhos sempre entre aspas (espaços, acentos)
        return " ".join(c if c.startswith("--") else f'"{c}"' for c in cmd)
    return " ".join(shlex.quote(c) for c in cmd)


def _registered():
    if compat.IS_WINDOWS:
        return _win_read(RUN_KEY, NAME)
    if sys.platform.startswith("linux"):
        return _linux_registered()
    return None


def status():
    """Situação do início automático para o painel e a CLI."""
    inst = running_instance() or {}
    st = {"supported": compat.IS_WINDOWS or sys.platform.startswith("linux"),
          "managed": managed(), "enabled": False, "other": None, "blocked": False,
          "background": bool(inst.get("background")), "url": inst.get("url"),
          "since": inst.get("started_at"), "running": bool(inst)}
    if compat.IS_WINDOWS:
        st["how"] = "Ao entrar no Windows, sem janela (não precisa de administrador)"
    elif st["supported"]:
        st["how"] = "Serviço systemd do usuário (inicia com o computador)"
    else:
        st["how"] = "Use o Docker para iniciar com o computador"
    if st["managed"] or not st["supported"]:
        return st
    reg = _registered()
    if reg:
        mine = _cmdline(command())
        if _same(reg, mine):
            st["enabled"] = True
            st["blocked"] = compat.IS_WINDOWS and _win_blocked()
        else:
            st["other"] = reg
    return st


def install():
    """Ativa o início automático desta instalação (substitui outra registrada)."""
    if managed():
        raise RuntimeError(f"Início automático já é feito por: {managed()}")
    cmd = command()
    if not os.environ.get("SENTINELA_PORTATIL"):
        _write_launcher()
    if compat.IS_WINDOWS:
        _win_install(_cmdline(cmd))
    elif sys.platform.startswith("linux"):
        d = _unit_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / UNIT).write_text(_unit_text(cmd), encoding="utf-8")
        try:
            _systemctl("daemon-reload")
            _systemctl("enable", UNIT)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            (d / UNIT).unlink(missing_ok=True)
            raise RuntimeError(
                f"Não foi possível usar o systemd do usuário ({e}). Em servidores, use o "
                "serviço do sistema: deploy/sentinela.service (veja o README).") from e
        # Inicia no boot mesmo sem ninguém entrar (quando o sistema permite)
        user = os.environ.get("USER") or os.environ.get("LOGNAME")
        if user:
            subprocess.run(["loginctl", "enable-linger", user], capture_output=True, timeout=30)
    else:
        raise RuntimeError("Início automático disponível no Windows e no Linux. Use o Docker.")
    return status()


def uninstall():
    """Desativa o início automático (só se for o desta instalação)."""
    st = status()
    if not st["enabled"]:
        return st
    if compat.IS_WINDOWS:
        _win_delete(RUN_KEY)
        _win_delete(APPROVED_KEY)
    elif sys.platform.startswith("linux"):
        try:
            _systemctl("disable", UNIT)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            (_unit_dir() / "default.target.wants" / UNIT).unlink(missing_ok=True)
        (_unit_dir() / UNIT).unlink(missing_ok=True)
    return status()


def repair():
    """Pasta portátil movida: o comando registrado aponta para um lugar que não
    existe mais. Atualiza para o lugar atual. Retorna True se atualizou."""
    if managed() or not (compat.IS_WINDOWS or sys.platform.startswith("linux")):
        return False
    reg = _registered()
    if not reg or _same(reg, _cmdline(command())) or _target_exists(reg):
        return False
    install()
    return True
