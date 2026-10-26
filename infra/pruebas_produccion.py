"""Pruebas de produccion a-e del contrato de verificacion bancaria.

Corre contra la API local. La ventana del nodo debe estar fijada al dia del
movimiento real de prueba (2026-10-22) por BANK_WINDOW_START/END.
"""

import json
import os
import sys
import time
from pathlib import Path

API = Path(r"C:\Users\MotoShop\Documents\javidevmoto\motoshopData\motoshop-app\api")
sys.path.insert(0, str(API / "src"))
os.chdir(API)

from motoshop_api.auth.users import load_users, get_user_by_username  # noqa: E402
from motoshop_api.auth.jwt import create_access_token  # noqa: E402
import httpx  # noqa: E402

BASE = os.environ.get("PROD_BASE_URL", "http://127.0.0.1:8000")
LOG = API.parent.parent / "logs" / "api_uvicorn.log"
FINAL = {"resuelto", "sin_coincidencia", "ambiguo", "fallido", "expirado"}
REF_ESPERADA = "0092405445"
DIA = "2026-10-22"

load_users(API / "users.yaml")
user = get_user_by_username("admin")
token = create_access_token(
    subject=user.username, role=user.role, tenants_allowed=user.tenants_allowed
)
H = {"Authorization": f"Bearer {token}", "X-Tenant": "motoshop"}


def tam_log() -> int:
    return LOG.stat().st_size if LOG.exists() else 0


def lineas_desde(offset: int) -> list[str]:
    if not LOG.exists():
        return []
    with LOG.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        return f.read().splitlines()


def esperar(client: httpx.Client, job_id: str, limite: float = 300.0) -> tuple[dict, float]:
    t0 = time.time()
    ultimo: dict = {}
    while time.time() - t0 < limite:
        time.sleep(4)
        ultimo = client.get(f"/api/erp/bank/verificaciones/{job_id}", headers=H).json()
        if ultimo.get("estado") in FINAL:
            return ultimo, time.time() - t0
    return ultimo, time.time() - t0


def _n(valor: object) -> object:
    """Cuenta si es lista; si ya viene como numero, lo deja igual."""
    return len(valor) if isinstance(valor, (list, tuple, dict)) else valor


def resumen(job: dict) -> dict:
    return {
        "job_id": job.get("job_id"),
        "estado": job.get("estado"),
        "resultado": job.get("resultado"),
        "error": job.get("error"),
    }


def main() -> int:
    salida: dict = {"base": BASE, "dia": DIA, "pruebas": {}}
    with httpx.Client(base_url=BASE, timeout=90) as c:
        # (a) modo factura, camino feliz
        off_a = tam_log()
        t0 = time.time()
        r = c.post(
            "/api/erp/bank/verificaciones",
            headers=H,
            json={"factura_id": "7337", "valor": "115000.00"},
        )
        cuerpo = r.json()
        ja = cuerpo.get("job_id")
        fa, da = esperar(c, ja)
        texto_a = json.dumps(fa, ensure_ascii=False)
        cand = (fa.get("resultado") or {}).get("candidato") or {}
        salida["pruebas"]["a"] = {
            "http": r.status_code,
            "job_id": ja,
            "estado": fa.get("estado"),
            "segundos": round(time.time() - t0, 1),
            "pagador": cand.get("pagador_nombre"),
            "valor": cand.get("valor"),
            "referencia": cand.get("referencia"),
            "nitter_presente": "nitter" in cand,
            "cliente": cand.get("cliente_nombre"),
            "nit_comodin_en_respuesta": "222222222" in texto_a,
            "movimientos": _n((fa.get("resultado") or {}).get("movimientos")),
            "candidatos": _n((fa.get("resultado") or {}).get("candidatos")),
            "final": resumen(fa),
            "log_scrape": [ln for ln in lineas_desde(off_a) if ja and ja in ln],
        }

        # El nodo no vuelve a barrer antes de 30 s: sin esta pausa el caso (c)
        # muere con `intervalo_minimo` aunque el contrato este bien.
        time.sleep(35)

        # (b) doble clic: dos POST identicos mientras el job corre
        off_b = tam_log()
        t0 = time.time()
        r1 = c.post(
            "/api/erp/bank/verificaciones",
            headers=H,
            json={"factura_id": "7337", "valor": "115000.00"},
        )
        r2 = c.post(
            "/api/erp/bank/verificaciones",
            headers=H,
            json={"factura_id": "7337", "valor": "115000.00"},
        )
        jb1, jb2 = r1.json().get("job_id"), r2.json().get("job_id")
        fb, db = esperar(c, jb1)
        salida["pruebas"]["b"] = {
            "http": [r1.status_code, r2.status_code],
            "job_id_1": jb1,
            "job_id_2": jb2,
            "mismo_job": jb1 == jb2,
            "estado": fb.get("estado"),
            "segundos": round(time.time() - t0, 1),
            "log_scrape": [ln for ln in lineas_desde(off_b) if jb1 and jb1 in ln],
        }

        time.sleep(35)

        # (c) reintento sobre un job ya terminado
        off_c = tam_log()
        t0 = time.time()
        r3 = c.post(
            "/api/erp/bank/verificaciones",
            headers=H,
            json={"factura_id": "7337", "valor": "115000.00"},
        )
        jc = r3.json().get("job_id")
        fc, dc = esperar(c, jc)
        salida["pruebas"]["c"] = {
            "http": r3.status_code,
            "job_id": jc,
            "job_id_nuevo": jc != jb1,
            "estado": fc.get("estado"),
            "segundos": round(time.time() - t0, 1),
            "log_scrape": [ln for ln in lineas_desde(off_c) if jc and jc in ln],
        }

        # (d) nada aplicado: el movimiento sigue PENDIENTE
        movs = c.get(
            "/api/erp/bank/movements",
            headers=H,
            params={"desde": DIA, "hasta": DIA},
        ).json()
        lista = movs if isinstance(movs, list) else movs.get("movimientos", movs.get("items", []))
        objetivo = [
            m
            for m in lista
            if str(m.get("referencia") or "") == REF_ESPERADA
            or str(m.get("id") or "").startswith("7171000c")
        ]
        salida["pruebas"]["d"] = {
            "movimientos": len(lista),
            "objetivo": [
                {
                    "id": m.get("id"),
                    "estado": m.get("estado"),
                    "valor": m.get("valor"),
                    "referencia": m.get("referencia"),
                }
                for m in objetivo
            ],
            "aplicados": [
                {"id": m.get("id"), "referencia": m.get("referencia")}
                for m in lista
                if str(m.get("estado") or "").upper() == "APLICADO"
            ],
            "total": sum(float(m.get("valor") or 0) for m in lista
                         if str(m.get("estado") or "").upper() != "IGNORADO"),
        }

        time.sleep(35)

        # (e) modo pago con un valor que no existe
        off_e = tam_log()
        t0 = time.time()
        r4 = c.post(
            "/api/erp/bank/verificaciones",
            headers=H,
            json={"modo": "pago", "valor": "999999.99"},
        )
        je = r4.json().get("job_id")
        fe, de = esperar(c, je)
        salida["pruebas"]["e"] = {
            "http": r4.status_code,
            "job_id": je,
            "estado": fe.get("estado"),
            "segundos": round(time.time() - t0, 1),
            "final": resumen(fe),
            "log_scrape": [ln for ln in lineas_desde(off_e) if je and je in ln],
        }

        # lineas de interes de toda la corrida
        todo = lineas_desde(off_a)
        salida["qr_duplicado"] = [ln for ln in todo if "qr_duplicado" in ln]
        salida["errores"] = [
            ln for ln in todo if "Traceback" in ln or " ERROR " in ln or "CRITICAL" in ln
        ]

    (LOG.parent.parent / "logs" / "prod_tests_out.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
