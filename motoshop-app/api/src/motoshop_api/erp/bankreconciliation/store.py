"""Persistencia de los movimientos bancarios (S4 — `app_bank_movements`).

- **Idempotencia por `(tenant, id_externo)`**: la tabla tiene `UNIQUE KEY
  uq_tenant_id_externo (tenant, id_externo)` y la ingesta usa `INSERT ... ON
  DUPLICATE KEY UPDATE` (sintaxis de MySQL 5.0.45). Reingerir actualiza los
  datos leídos y **no** crea una segunda fila, **no** toca `id_externo` y
  **no** revierte el estado ya avanzado por la conciliación.
- **Identificador de dominio `uuid5`**: `uuid5(NAMESPACE_DOMINIO,
  f"{tenant}:{id_externo}")`: estable entre procesos y distinto entre tenants.

Toda lectura filtra por `tenant`: un movimiento de otro tenant es invisible.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, Protocol

from motoshop_api.erp.bankreconciliation.schemas import (
    BankMovementIn,
    BankMovementOut,
    EstadoMovimiento,
)

#: Namespace del dominio de conciliación bancaria. Es FIJO: cambiarlo cambia
#: el `id` de todos los movimientos ya ingeridos, así que no debe tocarse
#: nunca. Separa los identificadores de dominio de los de HTTP (`uuid4`,
#: efímeros) y de los de otros dominios.
NAMESPACE_DOMINIO = uuid.UUID("fb53d95b-57d0-4515-95a9-1edbd5b429fd")

#: Columnas que la ingesta escribe y la reingesta refresca (nunca la identidad).
_COLUMNAS_DEL_SCRAPE = (
    "fecha_movimiento",
    "valor",
    "descripcion",
    "referencia",
    "referencia_norm",
    "pagador_nombre",
    "cuenta_origen",
)

_Movimientos = Sequence[BankMovementIn]

_SQL_UPSERT = """
INSERT INTO app_bank_movements
  (id, tenant, empresa, id_externo, fecha_movimiento, valor, descripcion,
   referencia, referencia_norm, pagador_nombre, cuenta_origen, estado, scraped_at)
VALUES
  (:id, :tenant, :empresa, :id_externo, :fecha_movimiento, :valor, :descripcion,
   :referencia, :referencia_norm, :pagador_nombre, :cuenta_origen, :estado, :scraped_at)
ON DUPLICATE KEY UPDATE
  empresa = VALUES(empresa),
  fecha_movimiento = VALUES(fecha_movimiento),
  valor = VALUES(valor),
  descripcion = VALUES(descripcion),
  referencia = VALUES(referencia),
  referencia_norm = VALUES(referencia_norm),
  pagador_nombre = VALUES(pagador_nombre),
  cuenta_origen = VALUES(cuenta_origen),
  scraped_at = VALUES(scraped_at)
"""

_SQL_EXISTENTES = """
SELECT id_externo FROM app_bank_movements
WHERE tenant = :tenant AND id_externo IN :id_externos
"""

_SQL_SELECT = """
SELECT id, tenant, empresa, id_externo, fecha_movimiento, valor, descripcion,
       referencia, referencia_norm, pagador_nombre, cuenta_origen, estado,
       recibo_numero, recibo_pref, confianza, razones, scraped_at
FROM app_bank_movements
WHERE tenant = :tenant
"""


def id_dominio_movimiento(tenant: str, id_externo: str) -> str:
    """Identificador de dominio del movimiento: `uuid5` de `tenant:id_externo`."""
    return str(uuid.uuid5(NAMESPACE_DOMINIO, f"{tenant}:{id_externo}"))


def _ahora() -> datetime:
    """Instante de la ingesta (UTC naive: MySQL 5.0 no guarda zona horaria)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _datos_del_scrape(movimiento: BankMovementIn) -> dict[str, Any]:
    """Datos leídos del portal que la reingesta refresca."""
    return {columna: getattr(movimiento, columna) for columna in _COLUMNAS_DEL_SCRAPE}


def _campos_del_estado(
    estado: EstadoMovimiento,
    recibo_numero: str | None,
    recibo_pref: str | None,
    confianza: int | None,
    razones: str | None,
) -> dict[str, Any]:
    """Campos que se escriben al cambiar el estado (un `None` no toca nada)."""
    campos: dict[str, Any] = {"estado": estado.value}
    if recibo_numero is not None:
        campos["recibo_numero"] = recibo_numero
    if recibo_pref is not None:
        campos["recibo_pref"] = recibo_pref
    if confianza is not None:
        campos["confianza"] = confianza
    if razones is not None:
        campos["razones"] = razones
    return campos


class BankStore(Protocol):
    """Contrato de persistencia de movimientos (doble falso y real)."""

    def upsert_movements(self, tenant: str, empresa: str, movimientos: _Movimientos) -> int: ...

    def list_movements(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]: ...

    def list_movimientos(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]: ...

    def find_movement(self, tenant: str, id_movimiento: str) -> BankMovementOut | None: ...

    def move_to_state(
        self,
        tenant: str,
        id_movimiento: str,
        estado: EstadoMovimiento,
        recibo_numero: str | None = None,
        recibo_pref: str | None = None,
        confianza: int | None = None,
        razones: str | None = None,
    ) -> bool: ...


class FakeBankStore:
    """Doble en memoria: mismas restricciones que la tabla real.

    Reproduce la clave única `(tenant, id_externo)`, el filtro por tenant de
    todas las lecturas y el orden estable del listado.
    """

    def __init__(self) -> None:
        self.movimientos: dict[tuple[str, str], dict[str, Any]] = {}

    def upsert_movements(self, tenant: str, empresa: str, movimientos: _Movimientos) -> int:
        nuevos = 0
        for movimiento in movimientos:
            clave = (tenant, movimiento.id_externo)
            existente = self.movimientos.get(clave)
            if existente is None:
                self.movimientos[clave] = {
                    "id": id_dominio_movimiento(tenant, movimiento.id_externo),
                    "tenant": tenant,
                    "empresa": empresa,
                    "id_externo": movimiento.id_externo,
                    "estado": EstadoMovimiento.PENDIENTE.value,
                    "recibo_numero": None,
                    "recibo_pref": None,
                    "confianza": None,
                    "razones": None,
                    "scraped_at": _ahora(),
                    **_datos_del_scrape(movimiento),
                }
                nuevos += 1
            else:
                # La identidad y el estado NO se tocan: sólo los datos leídos.
                existente.update(_datos_del_scrape(movimiento))
                existente["empresa"] = empresa
                existente["scraped_at"] = _ahora()
        return nuevos

    def list_movements(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]:
        filas = [fila for fila in self.movimientos.values() if fila["tenant"] == tenant]
        if estado is not None:
            filas = [fila for fila in filas if fila["estado"] == estado.value]
        if desde is not None:
            filas = [fila for fila in filas if fila["fecha_movimiento"] >= desde]
        if hasta is not None:
            filas = [fila for fila in filas if fila["fecha_movimiento"] <= hasta]
        # Orden estable: fecha descendente y, a igualdad, `id_externo` ascendente.
        filas.sort(key=lambda fila: fila["id_externo"])
        filas.sort(key=lambda fila: fila["fecha_movimiento"], reverse=True)
        return [BankMovementOut(**fila) for fila in filas]

    def list_movimientos(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]:
        """Alias en español de `list_movements` (mismo resultado, otro nombre)."""
        return self.list_movements(tenant, estado, desde, hasta)

    def find_movement(self, tenant: str, id_movimiento: str) -> BankMovementOut | None:
        fila = self._fila(tenant, id_movimiento)
        return BankMovementOut(**fila) if fila is not None else None

    def move_to_state(
        self,
        tenant: str,
        id_movimiento: str,
        estado: EstadoMovimiento,
        recibo_numero: str | None = None,
        recibo_pref: str | None = None,
        confianza: int | None = None,
        razones: str | None = None,
    ) -> bool:
        fila = self._fila(tenant, id_movimiento)
        if fila is None:
            return False
        fila.update(_campos_del_estado(estado, recibo_numero, recibo_pref, confianza, razones))
        return True

    def _fila(self, tenant: str, id_movimiento: str) -> dict[str, Any] | None:
        """Fila del tenant con ese identificador de dominio (`None` si no existe)."""
        for fila in self.movimientos.values():
            if fila["tenant"] == tenant and fila["id"] == id_movimiento:
                return fila
        return None


class RealBankStore:
    """Store real sobre `app_bank_movements` (InnoDB, motor de escritura)."""

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def _motor(self) -> Any:
        if self._engine is not None:
            return self._engine
        from motoshop_api.db.engine import get_writer_engine

        return get_writer_engine()

    def upsert_movements(self, tenant: str, empresa: str, movimientos: _Movimientos) -> int:
        if not movimientos:
            return 0
        from sqlalchemy import text

        ids_del_lote = {movimiento.id_externo for movimiento in movimientos}
        with self._motor().connect() as conn:
            existentes = self._existentes(conn, tenant, ids_del_lote)
            for movimiento in movimientos:
                conn.execute(text(_SQL_UPSERT), self._parametros(tenant, empresa, movimiento))
            conn.commit()
        return len(ids_del_lote - existentes)

    def list_movements(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]:
        from sqlalchemy import text

        sql = _SQL_SELECT
        params: dict[str, Any] = {"tenant": tenant}
        if estado is not None:
            sql += " AND estado = :estado"
            params["estado"] = estado.value
        if desde is not None:
            sql += " AND fecha_movimiento >= :desde"
            params["desde"] = desde
        if hasta is not None:
            sql += " AND fecha_movimiento <= :hasta"
            params["hasta"] = hasta
        sql += " ORDER BY fecha_movimiento DESC, id_externo ASC"
        with self._motor().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [_a_movimiento(row) for row in rows]

    def list_movimientos(
        self,
        tenant: str,
        estado: EstadoMovimiento | None = None,
        desde: date | None = None,
        hasta: date | None = None,
    ) -> list[BankMovementOut]:
        """Alias en español de `list_movements` (mismo resultado, otro nombre)."""
        return self.list_movements(tenant, estado, desde, hasta)

    def find_movement(self, tenant: str, id_movimiento: str) -> BankMovementOut | None:
        from sqlalchemy import text

        sql = _SQL_SELECT + " AND id = :id LIMIT 1"
        with self._motor().connect() as conn:
            row = conn.execute(text(sql), {"tenant": tenant, "id": id_movimiento}).fetchone()
        return _a_movimiento(row) if row is not None else None

    def move_to_state(
        self,
        tenant: str,
        id_movimiento: str,
        estado: EstadoMovimiento,
        recibo_numero: str | None = None,
        recibo_pref: str | None = None,
        confianza: int | None = None,
        razones: str | None = None,
    ) -> bool:
        from sqlalchemy import text

        valores = _campos_del_estado(estado, recibo_numero, recibo_pref, confianza, razones)
        sets = ", ".join(f"{columna} = :{columna}" for columna in valores)
        sql = f"UPDATE app_bank_movements SET {sets} WHERE tenant = :tenant AND id = :id"
        with self._motor().connect() as conn:
            resultado = conn.execute(
                text(sql),
                {**valores, "tenant": tenant, "id": id_movimiento},
            )
            conn.commit()
            impacted = resultado.rowcount
        return bool(impacted)

    def _existentes(self, conn: Any, tenant: str, ids: set[str]) -> set[str]:
        """`id_externo` que ya existen para el tenant (clave única `(tenant, id_externo)`)."""
        from sqlalchemy import bindparam, text

        if not ids:
            return set()
        sentencia = text(_SQL_EXISTENTES).bindparams(bindparam("id_externos", expanding=True))
        rows = conn.execute(sentencia, {"tenant": tenant, "id_externos": sorted(ids)}).fetchall()
        return {row[0] for row in rows}

    def _parametros(self, tenant: str, empresa: str, movimiento: BankMovementIn) -> dict[str, Any]:
        """Valores de la fila (el importe viaja como texto: `DECIMAL`, nunca float)."""
        params: dict[str, Any] = {
            "id": id_dominio_movimiento(tenant, movimiento.id_externo),
            "tenant": tenant,
            "empresa": empresa,
            "id_externo": movimiento.id_externo,
            "estado": EstadoMovimiento.PENDIENTE.value,
            "scraped_at": _ahora(),
            **_datos_del_scrape(movimiento),
        }
        params["valor"] = str(movimiento.valor)
        return params


def _a_movimiento(row: Any) -> BankMovementOut:
    """Fila de MySQL → modelo de lectura (el importe vuelve a `Decimal`)."""
    datos = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    return BankMovementOut(**datos)


def get_bank_store() -> BankStore:
    """Real en prod/dev, doble falso bajo pruebas (`settings.env == 'test'`)."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealBankStore()
    return FakeBankStore()
