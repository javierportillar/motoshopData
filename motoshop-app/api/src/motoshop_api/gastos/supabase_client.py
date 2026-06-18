"""Cliente HTTP minimalista para Supabase REST (PostgREST).

Sin SDK pesado — usamos httpx directo. Solo necesitamos CRUD sobre una tabla.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from typing import Any

import httpx
from fastapi import HTTPException

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

_TABLE = "gastos_operativos"


def _client() -> httpx.Client:
    """Cliente httpx configurado para Supabase REST.

    Lanza 503 si las credenciales no están seteadas — el resto del API
    funciona sin Supabase (solo la pestaña de Gastos cae).
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=503,
            detail="Supabase no configurado. Setear SUPABASE_URL y SUPABASE_SERVICE_KEY.",
        )
    return httpx.Client(
        base_url=f"{settings.supabase_url}/rest/v1",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        timeout=15.0,
    )


def _handle_response(r: httpx.Response, action: str) -> Any:
    if r.status_code >= 400:
        logger.error("Supabase %s falló: %s %s", action, r.status_code, r.text)
        # No exponemos detalles internos al cliente
        raise HTTPException(
            status_code=502 if r.status_code >= 500 else 400,
            detail=f"Error en Supabase ({action}): {r.status_code}",
        )
    if r.status_code == 204:
        return None
    try:
        return r.json()
    except Exception:
        return None


# ── CRUD ─────────────────────────────────────────────────────────────────────

def list_gastos(
    tenant: str,
    mes: str | None = None,
    categoria: str | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> list[dict]:
    """Lista gastos del tenant. Filtros opcionales.

    fecha_inicio/fecha_fin filtran por mes (YYYY-MM). Útil para el endpoint
    de balance que pide un rango de fechas.
    """
    params: dict[str, str] = {
        "tenant": f"eq.{tenant}",
        "order": "mes.desc,id.desc",
    }
    if mes:
        params["mes"] = f"eq.{mes}"
    if categoria:
        params["categoria"] = f"eq.{categoria}"
    if fecha_inicio:
        # Solo necesitamos meses; el rango se acota a >= mes-de-fecha_inicio
        params["mes"] = f"gte.{fecha_inicio[:7]}"
    if fecha_fin:
        # Si ambos están seteados, el operador AND se concatena con coma
        key = "mes" if "mes" not in params else "and"
        if key == "and":
            params["and"] = f"(mes.gte.{fecha_inicio[:7]},mes.lte.{fecha_fin[:7]})"
            params.pop("mes", None)
        else:
            params["mes"] = f"lte.{fecha_fin[:7]}"

    with _client() as c:
        r = c.get(f"/{_TABLE}", params=params)
        return _handle_response(r, "list_gastos") or []


def create_gasto(tenant: str, payload: dict, created_by: str | None) -> dict:
    body = {
        "tenant": tenant,
        "mes": payload["mes"],
        "categoria": payload["categoria"],
        "monto": payload["monto"],
        "descripcion": payload.get("descripcion"),
        "created_by": created_by,
    }
    with _client() as c:
        r = c.post(f"/{_TABLE}", json=body)
        data = _handle_response(r, "create_gasto")
        if not data:
            raise HTTPException(status_code=502, detail="Supabase no devolvió el registro creado")
        return data[0] if isinstance(data, list) else data


def update_gasto(tenant: str, gasto_id: int, payload: dict) -> dict:
    body = {k: v for k, v in payload.items() if v is not None}
    if not body:
        raise HTTPException(status_code=400, detail="Nada para actualizar")
    with _client() as c:
        r = c.patch(
            f"/{_TABLE}",
            json=body,
            params={"id": f"eq.{gasto_id}", "tenant": f"eq.{tenant}"},
        )
        data = _handle_response(r, "update_gasto")
        if not data:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")
        return data[0] if isinstance(data, list) else data


def delete_gasto(tenant: str, gasto_id: int) -> None:
    with _client() as c:
        r = c.delete(
            f"/{_TABLE}",
            params={"id": f"eq.{gasto_id}", "tenant": f"eq.{tenant}"},
        )
        _handle_response(r, "delete_gasto")


# ── Helpers de prorrateo (para balance) ─────────────────────────────────────


def gastos_prorrateados_por_dia(
    tenant: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> dict[str, float]:
    """Prorratea los gastos mensuales del rango entre los días calendario
    del mes correspondiente. Retorna dict {YYYY-MM-DD: monto_diario}.

    Ejemplo: un gasto de $300.000 en 2026-06 (30 días) → $10.000/día para
    cada día del rango que caiga en junio.

    Si los datos no están todo el mes (ej: rango parcial), igual prorratea
    sobre TODOS los días del mes — no compresión. La lógica financiera es:
    "el arriendo del mes son 300k, no importa qué días miremos del mes".
    """
    if not settings.supabase_url:
        return {}

    try:
        rows = list_gastos(tenant=tenant, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    except HTTPException:
        # Si Supabase falla, no romper el balance — solo devolver vacío
        logger.warning("No se pudieron cargar gastos; balance sin gastos operativos")
        return {}

    # Sumar por mes
    total_por_mes: dict[str, float] = {}
    for r in rows:
        mes = r["mes"]
        total_por_mes[mes] = total_por_mes.get(mes, 0.0) + float(r["monto"])

    # Prorratear por día calendario del mes
    out: dict[str, float] = {}
    for mes, total in total_por_mes.items():
        year, month = mes.split("-")
        days = monthrange(int(year), int(month))[1]
        diario = total / days
        for d in range(1, days + 1):
            fecha = f"{mes}-{str(d).zfill(2)}"
            if fecha_inicio <= fecha <= fecha_fin:
                out[fecha] = round(out.get(fecha, 0.0) + diario, 2)

    return out
