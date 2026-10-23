"""Prueba de humo post-reinicio del boton de conciliacion.

Corre una sola vez al iniciar sesion (tarea MotoShopPostBootProof), espera la API,
hace UN POST real de verificacion (F05: RC-5 / 100000.00), registra el resultado en
%TEMP%\\postboot-proof.log y se auto-desregistra.

Solo lectura contra el portal bancario: no aplica conciliaciones ni toca ERP.
"""

import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

ROOT = Path(r"C:\Users\MotoShop\Documents\javidevmoto\motoshopData\motoshop-app\api")
LOG = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "postboot-proof.log"
TASK = "MotoShopPostBootProof"
FINAL = {"resuelto", "sin_coincidencia", "ambiguo", "fallido", "expirado"}


def log(msg: str) -> None:
    linea = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def evidencia_entorno() -> None:
    log(f"usuario={os.environ.get('USERNAME')} equipo={os.environ.get('COMPUTERNAME')}")
    try:
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
        )
        vals = {}
        for nombre in ("AutoAdminLogon", "DefaultUserName", "DefaultDomainName"):
            try:
                vals[nombre] = winreg.QueryValueEx(k, nombre)[0]
            except OSError:
                vals[nombre] = None
        log(f"winlogon={json.dumps(vals)}")
    except OSError as exc:
        log(f"winlogon no legible: {exc}")


def esperar_health(intentos: int = 36, pausa: int = 10) -> bool:
    import httpx

    for i in range(intentos):
        try:
            r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
            if r.status_code == 200:
                log(f"health 200 en t+{i * pausa}s")
                return True
        except Exception:
            pass
        time.sleep(pausa)
    log(f"FALLA: health sin responder tras {intentos * pausa}s")
    return False


def probar_boton() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    os.chdir(ROOT)

    import httpx

    from motoshop_api.auth.jwt import create_access_token
    from motoshop_api.auth.users import get_user_by_username, load_users

    load_users(ROOT / "users.yaml")
    user = get_user_by_username("admin")
    token = create_access_token(
        subject=user.username, role=user.role, tenants_allowed=user.tenants_allowed
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}
    payload = {"factura_id": "RC-5", "valor": "100000.00"}

    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        r = client.post("/api/erp/bank/verificaciones", headers=headers, json=payload)
        log(f"POST HTTP {r.status_code} -> {json.dumps(r.json(), ensure_ascii=False)}")
        if r.status_code not in (200, 201, 202):
            return 1
        job_id = r.json()["job_id"]
        final = None
        for _ in range(60):
            time.sleep(4)
            final = client.get(f"/api/erp/bank/verificaciones/{job_id}", headers=headers).json()
            if final.get("estado") in FINAL:
                break
        log(f"job={job_id} final={json.dumps(final, ensure_ascii=False)}")
        sync = client.get("/api/erp/bank/sync-status", headers=headers).json()
        log(f"sync={json.dumps(sync, ensure_ascii=False)}")
        if final and final.get("estado") in ("resuelto", "sin_coincidencia"):
            log("OK: boton responde y termina sin error")
            return 0
        log(f"FALLA: estado final {final.get('estado') if final else None}")
        return 1


def main() -> int:
    log("=== postboot proof inicio ===")
    evidencia_entorno()
    if not esperar_health():
        return 1
    codigo = probar_boton()
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK, "/F"],
        capture_output=True,
        text=True,
    )
    log(f"=== postboot proof fin (code={codigo}); tarea {TASK} desregistrada ===")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
