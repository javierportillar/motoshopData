"""Verificaciones de pago estampadas sobre una venta, en Supabase.

El nodo guarda los movimientos del banco en su MySQL, pero **la verificación de
una venta no pertenece al nodo**: es un dato compartido entre dispositivos y
entre tenants. Por eso vive en Supabase y no en la base de cada PC.

Tres garantías:

* **Degradación limpia**: si el nodo no tiene las credenciales de Supabase, la
  lectura devuelve vacío y la escritura informa `False`. La pantalla de ventas
  sigue funcionando, sin el chip de verificado.
* **Idempotencia**: la clave es `(tenant, cod_clase, num_documento)`. Volver a
  verificar la misma venta actualiza la fila, no acumula historia.
* **Nada de secretos**: acá sólo viajan datos del movimiento que el portal ya
  mostró (pagador, referencia, importe, fecha). Nunca credenciales.

El esquema vive en `infra/supabase/migrations/20261027_001_bank_invoice_verifications.sql`.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

TABLA = "bank_invoice_verifications"
ESTADOS = ("verificado", "sin_coincidencia", "ambiguo")

#: Tope de filas por consulta: una pantalla mira un día, no un año.
_LIMITE = 500


class VerificacionVentaError(Exception):
    """La verificación no se pudo leer o guardar (Supabase no disponible)."""


def configurado() -> bool:
    """¿Este proceso tiene credenciales de Supabase para guardar verificaciones?"""
    return bool(settings.supabase_url and settings.supabase_service_key)


def _cliente() -> httpx.Client:
    if not configurado():
        raise VerificacionVentaError("Supabase no configurado en este nodo")
    return httpx.Client(
        base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1",
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )


def _json_de_fila(fila: dict[str, Any]) -> dict[str, Any]:
    """Fila de Supabase → JSON de la API (el importe viaja como texto)."""
    return {
        "cod_clase": fila.get("cod_clase") or "",
        "num_documento": fila.get("num_documento") or "",
        "fecha_venta": fila.get("fecha_venta") or "",
        "valor": str(fila.get("valor") or ""),
        "estado": fila.get("estado") or "",
        "pagador": fila.get("pagador") or "",
        "referencia": fila.get("referencia") or "",
        "fecha_movimiento": fila.get("fecha_movimiento") or "",
        "job_id": fila.get("job_id") or "",
        "verificado_por": fila.get("verificado_por") or "",
        "verificado_at": fila.get("verificado_at") or "",
    }


def listar(tenant: str, fecha: str) -> list[dict[str, Any]]:
    """Verificaciones de ese día para el tenant (vacío si Supabase no está)."""
    if not configurado():
        return []
    params = {
        "select": (
            "cod_clase,num_documento,fecha_venta,valor,estado,pagador,"
            "referencia,fecha_movimiento,job_id,verificado_por,verificado_at"
        ),
        "tenant": f"eq.{tenant}",
        "fecha_venta": f"eq.{fecha}",
        "order": "num_documento.asc",
        "limit": str(_LIMITE),
    }
    try:
        with _cliente() as cliente:
            respuesta = cliente.get(f"/{TABLA}", params=params)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.warning(
            "Verificaciones de venta: Supabase no respondió (%s)", type(exc).__name__
        )
        raise VerificacionVentaError("no se pudo leer Supabase") from exc
    if respuesta.status_code >= 400:
        logger.warning(
            "Verificaciones de venta: Supabase rechazó la lectura (%s)",
            respuesta.status_code,
        )
        raise VerificacionVentaError("Supabase rechazó la lectura")
    datos = respuesta.json()
    return [_json_de_fila(fila) for fila in datos] if isinstance(datos, list) else []


def guardar(
    *,
    tenant: str,
    cod_clase: str,
    num_documento: str,
    fecha_venta: str,
    valor: Decimal,
    estado: str,
    verificado_por: str,
    job_id: str | None = None,
    pagador: str | None = None,
    referencia: str | None = None,
    fecha_movimiento: str | None = None,
) -> bool:
    """Estampa la verificación sobre la venta (upsert por tenant + documento).

    Devuelve `False` (sin excepción) cuando el nodo no tiene Supabase: la
    pantalla no debe romperse por una función de sólo lectura.
    """
    if not configurado():
        return False
    if estado not in ESTADOS:
        raise VerificacionVentaError(f"estado desconocido: {estado}")
    fila = {
        "tenant": tenant,
        "cod_clase": cod_clase,
        "num_documento": num_documento,
        "fecha_venta": fecha_venta,
        "valor": str(valor),
        "estado": estado,
        "pagador": pagador,
        "referencia": referencia,
        "fecha_movimiento": fecha_movimiento,
        "job_id": job_id,
        "verificado_por": verificado_por,
    }
    try:
        with _cliente() as cliente:
            respuesta = cliente.post(
                f"/{TABLA}",
                params={"on_conflict": "tenant,cod_clase,num_documento"},
                json=fila,
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.warning("Verificaciones de venta: no se pudo guardar (%s)", type(exc).__name__)
        raise VerificacionVentaError("no se pudo escribir en Supabase") from exc
    if respuesta.status_code >= 400:
        logger.warning(
            "Verificaciones de venta: Supabase rechazó la escritura (%s)",
            respuesta.status_code,
        )
        raise VerificacionVentaError("Supabase rechazó la escritura")
    return True
