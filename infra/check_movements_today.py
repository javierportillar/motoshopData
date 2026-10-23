"""Chequeo reproducible de las transferencias del dia (conciliacion bancaria).

Consulta ``GET /api/erp/bank/movements`` con autenticacion local (JWT del usuario
admin + ``X-Tenant``) y muestra los movimientos cuya fecha coincide con el dia
LOCAL de la maquina.

Por que la ventana es ancha: la API guarda fechas en UTC y este nodo vive en
UTC-5, asi que "hoy" local cae en dos dias UTC distintos. Consultar con la fecha
UTC pelada devuelve cero filas y parece que la ingesta fallo. Por eso se pide
``hoy - margen`` .. ``hoy + margen`` y se filtra por fecha local.

Uso:

    python infra\\check_movements_today.py
    python infra\\check_movements_today.py --tenant motoshop --margen-dias 2
    python infra\\check_movements_today.py --json

Solo lectura: no aplica conciliaciones ni escribe en el ERP.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parent
PROJECT = INFRA.parent
API_DIR = PROJECT / "motoshop-app" / "api"


def _cliente(base_url: str, tenant: str):
    """Devuelve (client, headers) con JWT local, sin red ni credenciales."""
    sys.path.insert(0, str(API_DIR / "src"))
    os.chdir(API_DIR)
    from motoshop_api.auth.jwt import create_access_token
    from motoshop_api.auth.users import get_user_by_username, load_users

    load_users(API_DIR / "users.yaml")
    usuario = get_user_by_username("admin")
    token = create_access_token(
        subject=usuario.username,
        role=usuario.role,
        tenants_allowed=usuario.tenants_allowed,
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": tenant}

    import httpx

    return httpx.Client(base_url=base_url, timeout=60), headers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transferencias del dia (solo lectura)")
    parser.add_argument("--tenant", default="motoshop")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--fecha",
        default="",
        help="dia local a chequear (YYYY-MM-DD). Por defecto, hoy.",
    )
    parser.add_argument(
        "--margen-dias",
        type=int,
        default=1,
        help="dias de margen a cada lado de la fecha (por el desfase UTC)",
    )
    parser.add_argument("--json", action="store_true", help="salida JSON cruda")
    args = parser.parse_args(argv)

    hoy = dt.date.fromisoformat(args.fecha) if args.fecha else dt.date.today()
    desde = (hoy - dt.timedelta(days=args.margen_dias)).isoformat()
    hasta = (hoy + dt.timedelta(days=args.margen_dias)).isoformat()
    params = {"desde": desde, "hasta": hasta}

    client, headers = _cliente(args.base_url, args.tenant)
    with client:
        r = client.get("/api/erp/bank/movements", headers=headers, params=params)
        if r.status_code != 200:
            print(f"ERROR HTTP {r.status_code}: {r.text[:800]}", file=sys.stderr)
            return 1
        datos = r.json()
        movimientos = datos.get("movimientos", datos)
        del_dia = [m for m in movimientos if str(m.get("fecha")) == hoy.isoformat()]
        sync = client.get("/api/erp/bank/sync-status", headers=headers).json()

    if args.json:
        print(
            json.dumps(
                {
                    "hoy_local": hoy.isoformat(),
                    "ventana": params,
                    "total_ventana": len(movimientos),
                    "del_dia": del_dia,
                    "sync": sync,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"dia local={hoy.isoformat()} ventana={desde}..{hasta} tenant={args.tenant}")
    print(f"movimientos en la ventana={len(movimientos)}  del dia={len(del_dia)}")
    total = 0.0
    for m in del_dia:
        valor = float(m.get("valor") or 0)
        total += valor
        print(
            "  {fecha}  {valor:>12}  {estado:<16} ref={referencia}  {pagador}".format(
                fecha=m.get("fecha"),
                valor=f"{valor:,.2f}",
                estado=str(m.get("estado") or ""),
                referencia=m.get("referencia"),
                pagador=(m.get("pagadorNombre") or "")[:34],
            )
        )
    print(f"TOTAL del dia={total:,.2f}")
    print(
        "sync: ultimaIngestaAt={} nodo={} scraper={} ventana={}".format(
            sync.get("ultimaIngestaAt"),
            sync.get("nodo"),
            sync.get("scraperHabilitado"),
            sync.get("ventana"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
