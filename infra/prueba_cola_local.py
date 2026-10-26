"""Evidencia en vivo del modo cola (F0/F1) de la verificacion bancaria.

Levanta una instancia **aparte** de la API en `127.0.0.1:8010` con
`BANK_DISPATCH_MODE=queue` y un **portal falso** (no abre sesion del banco, no
usa Playwright). La API de produccion (`:8000`) y el ERP no se tocan.

Que prueba, de punta a punta por HTTP:
  1. El plano de control exige `X-Node-Token` (401 sin token).
  2. El POST devuelve 202 en milisegundos y **no** levanta hilos de scrape.
  3. El agente reclama el job, raspa con el portal falso y publica el estado.
  4. "Sesion cerrada por otro dispositivo" no es fallo: vuelve a `en_cola` con
     el codigo estable, y se puede retomar.
  5. Dos agentes a la vez: el candado por cuenta deja pasar a uno solo.

Escribe jobs de prueba en `app_bank_verification_jobs` y candados/nodos de
prueba, y los borra al final (incluso si el script falla).

Uso:
    cd motoshop-app/api
    $env:PYTHONPATH = "src;..\\..\\infra"
    .\\.venv\\Scripts\\python.exe ..\\..\\infra\\prueba_cola_local.py

Sale con codigo 0 solo si todas las comprobaciones pasan.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8010"
TOKEN = "token-prueba-cola-8010"
#: Cliente de MySQL: se puede pisar con la variable `MYSQL_EXE`.
MYSQL_EXE = os.environ.get(
    "MYSQL_EXE",
    r"C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\mysql.exe",
)

os.environ["BANK_DISPATCH_MODE"] = "queue"
os.environ["BANK_NODE_TOKEN"] = TOKEN
os.environ["BANK_API_URL"] = BASE
os.environ["BANK_NODE_ID"] = "PRUEBA-8010"

from motoshop_api.erp.bankreconciliation import scraper as scraper_mod  # noqa: E402
from motoshop_api.erp.bankreconciliation import worker as worker_mod  # noqa: E402

LLAMADAS = {"n": 0}
MODO = {"valor": "ok"}


class ScraperFalso:
    """Portal falso: cero movimientos, o sesion cerrada por otro dispositivo."""

    def scrape(self, config):
        LLAMADAS["n"] += 1
        if MODO["valor"] == "sesion_cerrada":
            raise scraper_mod.BankScrapeError(
                scraper_mod.CODIGO_SESION_CERRADA, "prueba: cuenta abierta en otro equipo"
            )
        ahora = datetime.datetime.now()
        return scraper_mod.ScrapeResult(
            tenant=config.tenant,
            cuenta="PRUEBA",
            ventana=(ahora - datetime.timedelta(hours=2), ahora),
            paginas=0,
            movimientos=(),
            leido_en=ahora,
        )


worker_mod.BankVerificationWorker._scraper_por_defecto = (
    lambda self, pedir_codigo: ScraperFalso()
)

from motoshop_api.auth.deps import get_current_user  # noqa: E402
from motoshop_api.auth.users import User  # noqa: E402
from motoshop_api.erp import guards  # noqa: E402
from motoshop_api.main import app  # noqa: E402


class TenantFalso:
    id = "masvital"


# El middleware de rutas (`require_route_module`) valida el JWT antes de las
# dependencias del handler: se reemplaza por un usuario admin de prueba.
USUARIO_FALSO = User(
    username="prueba_cola",
    hashed_password="x",
    email="prueba@local",
    role="admin",
    tenants_allowed=["masvital"],
    allowed_modules=None,
)
app.dependency_overrides[get_current_user] = lambda: USUARIO_FALSO
app.dependency_overrides[guards.require_erp_tenant] = lambda: TenantFalso()
app.dependency_overrides[guards.require_erp_collections_write] = lambda: None

import uvicorn  # noqa: E402
from node_agent import AgenteNodo, PlanoDeControl  # noqa: E402

resultados: list[tuple[bool, str]] = []


def chequear(ok: bool, texto: str) -> None:
    resultados.append((ok, texto))
    print(("  OK   " if ok else "  FALLA") + f" {texto}")


def http(metodo: str, ruta: str, cuerpo: dict | None = None, token: str | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Node-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        crudo = exc.read() or b"{}"
        try:
            return exc.code, json.loads(crudo)
        except Exception:
            return exc.code, {"crudo": crudo.decode(errors="replace")}


def hilos_de_verificacion() -> list[str]:
    return [t.name for t in threading.enumerate() if "banco-verificacion" in t.name]


def arrancar_servidor() -> uvicorn.Server:
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8010, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, name="uvicorn-8010", daemon=True).start()
    for _ in range(120):
        if server.started:
            return server
        time.sleep(0.25)
    raise RuntimeError("uvicorn no arranco en :8010")


def borrar_jobs(ids: list[str]) -> bool:
    if not ids:
        return True
    lista = ",".join(f"'{i}'" for i in ids)
    sql = f"DELETE FROM app_bank_verification_jobs WHERE job_id IN ({lista});"
    mysql = MYSQL_EXE
    proc = subprocess.run(
        [mysql, "--user=root", "--password=", "masvital", "-e", sql],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def jobs_en_cola() -> int:
    mysql = MYSQL_EXE
    proc = subprocess.run(
        [
            mysql,
            "--user=root",
            "--password=",
            "--skip-column-names",
            "masvital",
            "-e",
            "SELECT COUNT(*) FROM app_bank_verification_jobs "
            "WHERE tenant='masvital' AND estado IN ('en_cola','ejecutando');",
        ],
        capture_output=True,
        text=True,
    )
    return int((proc.stdout or "0").strip() or 0)


def locks_actuales() -> list[str]:
    mysql = MYSQL_EXE
    proc = subprocess.run(
        [
            mysql,
            "--user=root",
            "--password=",
            "--skip-column-names",
            "masvital",
            "-e",
            "SELECT node_id FROM app_bank_account_locks WHERE tenant='masvital';",
        ],
        capture_output=True,
        text=True,
    )
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def limpiar_locks_de_prueba() -> bool:
    mysql = MYSQL_EXE
    proc = subprocess.run(
        [
            mysql,
            "--user=root",
            "--password=",
            "masvital",
            "-e",
            "DELETE FROM app_bank_account_locks WHERE node_id LIKE 'PRUEBA%';",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


IDS: list[str] = []


def main() -> int:
    try:
        return cuerpo_de_main()
    finally:
        ok_jobs = borrar_jobs(IDS)
        ok_locks = limpiar_locks_de_prueba()
        print(
            f"\nLIMPIEZA: jobs={'ok' if ok_jobs else 'FALLO'} "
            f"locks={'ok' if ok_locks else 'FALLO'} - borrados {len(IDS)} jobs de prueba"
        )
        for i in IDS:
            print(f"  - {i}")


def cuerpo_de_main() -> int:
    print("== 0. arranque limpio (el agente toma el mas viejo: FIFO) ==")
    limpiar_locks_de_prueba()
    chequear(jobs_en_cola() == 0, f"jobs en_cola al empezar: {jobs_en_cola()}")
    chequear(locks_actuales() == [], f"candados al empezar: {locks_actuales()}")

    print("== 1. plano de control arriba ==")
    server = arrancar_servidor()
    estado, cuerpo = http("GET", "/api/erp/bank/node/status")
    chequear(estado == 401, f"sin token -> 401 (vino {estado})")
    estado, cuerpo = http("GET", "/api/erp/bank/node/status", token=TOKEN)
    chequear(estado == 200, f"con token -> 200 (vino {estado})")
    print(f"       status: {json.dumps(cuerpo)[:160]}")

    print("== 2. POST en modo cola: 202 sin hilos ==")
    t0 = time.monotonic()
    estado, alta = http(
        "POST",
        "/api/erp/bank/verificaciones",
        {"modo": "pago", "valor": "111.11", "nombre_esperado": "PRUEBA COLA"},
    )
    ms = (time.monotonic() - t0) * 1000
    chequear(estado == 202, f"POST -> 202 (vino {estado})")
    chequear(alta.get("estado") == "en_cola", f"estado en_cola (vino {alta.get('estado')})")
    chequear(ms < 1000, f"respondio en {ms:.0f} ms (sin raspar)")
    chequear(hilos_de_verificacion() == [], f"cero hilos de scrape en la API ({hilos_de_verificacion()})")
    chequear(LLAMADAS["n"] == 0, f"el portal falso no se llamo todavia ({LLAMADAS['n']})")
    job1 = alta["job_id"]
    IDS.append(job1)
    print(f"       job1 = {job1}")

    print("== 3. el agente toma el job y publica ==")
    plano = PlanoDeControl(BASE, TOKEN)
    agente = AgenteNodo(plano, node_id="PRUEBA-8010-A", tenants=["masvital"])
    agente.latir_una_vez()
    tomo = agente.ejecutar_una_vez()
    chequear(tomo, "el agente encontro trabajo y lo ejecuto")
    chequear(LLAMADAS["n"] == 1, f"portal falso llamado una vez ({LLAMADAS['n']})")
    estado, detalle = http("GET", f"/api/erp/bank/verificaciones/{job1}")
    chequear(estado == 200, f"GET job1 -> 200 (vino {estado})")
    print(f"       job1 estado = {detalle.get('estado')} error = {detalle.get('error')}")
    chequear(
        detalle.get("estado") not in ("en_cola", "ejecutando", None),
        f"job1 salio de la cola ({detalle.get('estado')})",
    )
    chequear(
        locks_actuales() == [],
        f"el candado quedo liberado en la tabla ({locks_actuales()})",
    )

    print("== 4. sesion cerrada por otro dispositivo: vuelve a la cola ==")
    _, alta2 = http(
        "POST",
        "/api/erp/bank/verificaciones",
        {"modo": "pago", "valor": "222.22", "nombre_esperado": "PRUEBA SESION"},
    )
    job2 = alta2["job_id"]
    IDS.append(job2)
    MODO["valor"] = "sesion_cerrada"
    tomo2 = agente.ejecutar_una_vez()
    chequear(tomo2, "el agente tomo el segundo job")
    _, det2 = http("GET", f"/api/erp/bank/verificaciones/{job2}")
    chequear(det2.get("estado") == "en_cola", f"job2 volvio a en_cola (vino {det2.get('estado')})")
    codigo2 = str(det2.get("error") or "")
    chequear(
        "sesion_cerrada_por_otro_dispositivo" in codigo2,
        f"job2 con el codigo estable (vino {codigo2!r})",
    )
    MODO["valor"] = "ok"

    print("== 4b. el job devuelto a la cola se puede retomar (drenaje) ==")
    chequear(agente.ejecutar_una_vez(), "el agente retomo el job devuelto a la cola")
    _, det2b = http("GET", f"/api/erp/bank/verificaciones/{job2}")
    chequear(
        det2b.get("estado") not in ("en_cola", "ejecutando"),
        f"job2 termino en el reintento ({det2b.get('estado')})",
    )
    chequear(jobs_en_cola() == 0, f"cola vacia antes del paso 5 ({jobs_en_cola()})")

    print("== 5. dos agentes a la vez: uno solo puede ==")
    _, alta3 = http(
        "POST",
        "/api/erp/bank/verificaciones",
        {"modo": "pago", "valor": "333.33", "nombre_esperado": "PRUEBA DOS"},
    )
    job3 = alta3["job_id"]
    IDS.append(job3)
    agente_a = AgenteNodo(PlanoDeControl(BASE, TOKEN), node_id="PRUEBA-A", tenants=["masvital"])
    agente_b = AgenteNodo(PlanoDeControl(BASE, TOKEN), node_id="PRUEBA-B", tenants=["masvital"])
    toma_a = agente_a.reclamar_uno()
    toma_b = agente_b.reclamar_uno()
    chequear(toma_a is not None, f"agente A tomo el job3 ({'si' if toma_a else 'no'})")
    chequear(toma_b is None, f"agente B no pudo tomarlo ({'si pudo: MAL' if toma_b else 'bloqueado'})")
    if toma_a:
        agente_a._correr_job(toma_a)
        _, det3 = http("GET", f"/api/erp/bank/verificaciones/{job3}")
        chequear(
            det3.get("estado") not in ("en_cola", "ejecutando"),
            f"job3 terminado por A ({det3.get('estado')})",
        )
    toma_b2 = agente_b.reclamar_uno()
    chequear(toma_b2 is None, "agente B ya no encuentra trabajo (cola vacia)")

    print("== 6. cierre del servidor de prueba ==")
    server.should_exit = True
    time.sleep(1)
    chequear(True, "uvicorn :8010 cerrado")

    fallas = [t for ok, t in resultados if not ok]
    print("\n== RESUMEN ==")
    print(f"{len(resultados) - len(fallas)}/{len(resultados)} OK")
    print(f"jobs de prueba: {', '.join(IDS)}")
    if fallas:
        print("FALLARON:")
        for f in fallas:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

