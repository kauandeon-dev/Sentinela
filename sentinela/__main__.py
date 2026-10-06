"""Linha de comando do Sentinela.

    python -m sentinela serve              inicia o painel web + agendador
    python -m sentinela passwd [usuario]   cria/altera usuário do painel
    python -m sentinela backup             executa um backup agora
    python -m sentinela decrypt ARQ -o SAIDA.sql
                                           recupera o SQL de uma cópia sem o painel
    python -m sentinela sync               envia ao(s) destino(s) externo(s) o que estiver pendente
    python -m sentinela key export -o ARQ  exporta a chave mestra (guarde fora do servidor)
    python -m sentinela key import ARQ     importa a chave de outra instalação (ler cópias antigas)
    python -m sentinela key id             mostra o identificador da chave atual
"""

import argparse
import getpass
import secrets
import sys
import zlib

from werkzeug.security import generate_password_hash

from . import __version__, crypto, engine, settings, storage


def cmd_serve(args):
    from .scheduler import Scheduler
    from .web import create_app

    engine.setup_logging()
    storage.init()
    engine.key()
    engine.recover_interrupted()
    if storage.count_users() == 0:
        pw = secrets.token_urlsafe(12)
        storage.upsert_user("admin", generate_password_hash(pw))
        print("=" * 60)
        print(" Primeiro acesso: usuário 'admin'  senha:", pw)
        print(" Altere com: python -m sentinela passwd admin")
        print("=" * 60)
    print(f" Chave mestra: {settings.KEY_PATH}")
    print("  -> guarde uma cópia FORA do servidor; sem ela as cópias")
    print("     criptografadas não podem ser recuperadas.")

    Scheduler().start()
    app = create_app()
    host, port = args.host or settings.HOST, args.port or settings.PORT
    engine.log.info("Sentinela %s ouvindo em http://%s:%s", __version__, host, port)
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, threaded=True)


def cmd_passwd(args):
    storage.init()
    user = args.username or "admin"
    pw = getpass.getpass(f"Nova senha para '{user}': ")
    if len(pw) < 8:
        sys.exit("A senha deve ter pelo menos 8 caracteres.")
    if pw != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")
    storage.upsert_user(user, generate_password_hash(pw))
    print(f"Senha de '{user}' definida.")


def cmd_backup(args):
    engine.setup_logging()
    storage.init()
    try:
        bid = engine.start_backup("manual", wait=True)
    except (engine.Busy, ValueError) as e:
        sys.exit(f"Backup não iniciado: {e}")
    b = engine.get_backup(bid)
    print(f"{bid}: {b['status']}" + (f" — {b['error']}" if b["error"] else f" — {b['path']}"))
    sys.exit(0 if b["status"] == "success" else 1)


def cmd_decrypt(args):
    key_path = args.key or settings.KEY_PATH
    try:
        key = _read_key(key_path)
    except OSError:
        sys.exit(f"Chave mestra não encontrada em {key_path}")
    if len(key) != crypto.KEY_LEN:
        sys.exit("Chave mestra inválida")
    src = args.file
    compressed = src.endswith(".gz") or src.endswith(".gz.enc")
    encrypted = src.endswith(".enc")
    out = sys.stdout.buffer if args.output == "-" else open(args.output, "wb")
    engine._key = key
    try:
        engine.iter_plaintext(src, compressed, encrypted, out.write)
    except (crypto.IntegrityError, zlib.error) as e:
        sys.exit(f"Erro: {e}")
    finally:
        if out is not sys.stdout.buffer:
            out.close()
    if args.output != "-":
        print(f"SQL recuperado em {args.output}")


def cmd_sync(args):
    from . import replication
    engine.setup_logging()
    storage.init()
    try:
        eid = replication.start_sync("manual", wait=True)
    except engine.Busy as e:
        sys.exit(f"Sincronização não iniciada: {e}")
    if eid is None:
        print("Nada pendente: todas as cópias já estão nos destinos externos.")
        return
    ex = storage.row("SELECT status FROM executions WHERE id=?", (eid,))
    print(f"Sincronização #{eid}: {'concluída' if ex['status'] == 'success' else 'com falhas — veja os logs'}")
    sys.exit(0 if ex["status"] == "success" else 1)


def cmd_key(args):
    storage.init()
    if args.action == "id":
        print(engine.key_id())
    elif args.action == "export":
        if not args.output:
            sys.exit("Informe o arquivo de saída: -o ARQUIVO.key")
        import os
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(engine.key())
        storage.set_setting("key_exported_at", storage.iso(storage.now()))
        print(f"Chave {engine.key_id()} exportada para {args.output}.")
        print("Guarde-a FORA do servidor (pendrive, cofre de senhas). Quem tiver a chave e as "
              "cópias consegue ler os dados.")
    else:
        if not args.file:
            sys.exit("Informe o arquivo da chave: python -m sentinela key import ARQUIVO.key")
        try:
            kid, added = engine.import_key(_read_key(args.file))
        except (OSError, ValueError) as e:
            sys.exit(f"Erro: {e}")
        print(f"Chave {kid} importada para o chaveiro." if added else
              f"A chave {kid} já é a chave atual deste servidor.")


def _read_key(path):
    with open(path, "rb") as f:
        return f.read()


def main():
    p = argparse.ArgumentParser(prog="sentinela", description="Backup automatizado de bancos de dados")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="inicia o painel web e o agendador")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("passwd", help="cria ou altera a senha de um usuário do painel")
    s.add_argument("username", nargs="?")
    s.set_defaults(fn=cmd_passwd)

    s = sub.add_parser("backup", help="executa um backup imediatamente")
    s.set_defaults(fn=cmd_backup)

    s = sub.add_parser("decrypt", help="recupera o SQL de uma cópia (.sql.gz.enc)")
    s.add_argument("file")
    s.add_argument("-o", "--output", required=True, help="arquivo de saída ou '-' para stdout")
    s.add_argument("--key", help="caminho da chave mestra (padrão: a do SENTINELA_HOME)")
    s.set_defaults(fn=cmd_decrypt)

    s = sub.add_parser("sync", help="envia aos destinos externos as cópias pendentes")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("key", help="exporta/importa a chave mestra")
    s.add_argument("action", choices=["export", "import", "id"])
    s.add_argument("file", nargs="?", help="arquivo da chave (import)")
    s.add_argument("-o", "--output", help="arquivo de saída (export)")
    s.set_defaults(fn=cmd_key)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
