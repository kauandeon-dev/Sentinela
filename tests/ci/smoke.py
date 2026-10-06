"""Teste de fumaça do Sentinela já em execução (nativo ou em Docker).

Usa só a API, como o painel: login, conexão, backup, verificação, restauração
e destino externo "Outro disco". Uso:
    python tests/ci/smoke.py URL USUARIO SENHA HOST_DO_BANCO PASTA_DESTINO
"""
import http.cookiejar
import json
import sys
import time
import urllib.request

URL, USER, PW, DBHOST, DEST = sys.argv[1:6]
jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(method, path, data=None):
    req = urllib.request.Request(URL + path, method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with jar.open(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait_idle():
    for _ in range(300):
        if not call("GET", "/api/state")[1]["running"]:
            return
        time.sleep(1)
    raise SystemExit("execução não terminou")


def check(cond, msg):
    print(("OK    " if cond else "FALHA ") + msg, flush=True)
    if not cond:
        raise SystemExit(1)


for _ in range(60):
    try:
        if call("GET", "/api/me")[0] == 200:
            break
    except OSError:
        time.sleep(2)
check(call("POST", "/api/login", {"username": USER, "password": PW})[0] == 200, "login")
st, r = call("POST", "/api/connection/test", {"sgbd": "postgres", "host": DBHOST, "port": "5432",
                                               "dbname": "loja_producao", "user": "backup_user",
                                               "password": "senha123"})
check(r.get("ok"), f"teste de conexão: {r}")
check(call("PUT", "/api/connection", {"sgbd": "postgres", "host": DBHOST, "port": "5432",
                                      "dbname": "loja_producao", "user": "backup_user",
                                      "password": "senha123"})[0] == 200, "conexão salva")
st, r = call("POST", "/api/destinations", {"type": "directory", "name": "Disco externo", "path": DEST})
check(st == 201, f"destino externo criado: {r}")
st, r = call("POST", "/api/backups")
check(st == 202, "backup iniciado")
bid = r["id"]
wait_idle()
st, d = call("GET", f"/api/backups/{bid}")
check(d["backup"]["status"] == "success", f"backup concluído: {d['backup'].get('error')}")
check(d["backup"]["verify_ok"] is True, "integridade verificada após o backup")
check(d["replicas"] and d["replicas"][0]["status"] == "success", "cópia externa conferida")
st, r = call("POST", f"/api/backups/{bid}/verify")
check(r["ok"], f"verificação sob demanda: {r}")
st, r = call("POST", f"/api/backups/{bid}/restore")
check(st == 202, "restauração iniciada")
wait_idle()
st, e = call("GET", f"/api/executions/{r['execution']}")
check(e["execution"]["status"] == "success",
      "restauração concluída: " + " | ".join(l["message"] for l in e["execution"]["lines"][-3:]))
print("Teste de fumaça concluído.")
