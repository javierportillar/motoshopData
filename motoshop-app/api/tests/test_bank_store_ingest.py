"""Tests de la ingesta idempotente de movimientos bancarios (S4).

La ingesta es idempotente por `(tenant, id_externo)`: reingerir el mismo
movimiento NO crea una segunda fila, NO modifica el `id_externo` y NO revierte
el estado ya avanzado. El identificador de dominio es `uuid5` del namespace del
dominio: estable entre procesos y distinto entre tenants. Toda lectura filtra
por tenant: un movimiento de otro tenant es invisible.
"""

from __future__ import annotations

import datetime
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn, EstadoMovimiento
from motoshop_api.erp.bankreconciliation.store import (
    NAMESPACE_DOMINIO,
    FakeBankStore,
    RealBankStore,
    get_bank_store,
    id_dominio_movimiento,
)

TENANT = "motoshop"
OTRO_TENANT = "masvital"
EMPRESA = "MOTO"

_DDL = Path(__file__).resolve().parents[3] / "infra/migrations/F9-001-app_bank_movements.sql"


def _movimiento(id_externo: str = "EXT-1", **cambios: Any) -> BankMovementIn:
    """Movimiento entrante del portal con los datos de una consignación."""
    datos: dict[str, Any] = {
        "id_externo": id_externo,
        "fecha_movimiento": datetime.date(2025, 2, 10),
        "valor": Decimal("458200.00"),
        "descripcion": "PAGO QR LIZETH STEPHANIA PORTI",
        "referencia": "0092055984",
        "referencia_norm": "0092055984",
        "pagador_nombre": "LIZETH STEPHANIA PORTI",
        "cuenta_origen": "AHORROS MOTO SHOP",
    }
    datos.update(cambios)
    return BankMovementIn(**datos)


def _fila_mysql(id_externo: str = "EXT-1", **cambios: Any) -> dict[str, Any]:
    """Fila como la devuelve MySQL (el importe ya es `Decimal`)."""
    fila: dict[str, Any] = {
        "id": id_dominio_movimiento(TENANT, id_externo),
        "tenant": TENANT,
        "empresa": EMPRESA,
        "id_externo": id_externo,
        "fecha_movimiento": datetime.date(2025, 2, 10),
        "valor": Decimal("458200.00"),
        "descripcion": "PAGO QR",
        "referencia": "0092055984",
        "referencia_norm": "0092055984",
        "pagador_nombre": "LIZETH STEPHANIA PORTI",
        "cuenta_origen": "AHORROS MOTO SHOP",
        "estado": "PENDIENTE",
        "recibo_numero": None,
        "recibo_pref": None,
        "confianza": None,
        "razones": None,
        "scraped_at": None,
    }
    fila.update(cambios)
    return fila


# ─── Ingesta idempotente ────────────────────────────────────────


def test_upsert_primera_carga_graba_n_filas() -> None:
    """La primera carga persiste los movimientos y devuelve cuántos son nuevos."""
    store = FakeBankStore()

    nuevos = store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1"), _movimiento("EXT-2")])

    assert nuevos == 2
    assert len(store.list_movements(TENANT)) == 2


def test_reingesta_del_mismo_id_externo_no_crea_filas() -> None:
    """Reingerir el mismo movimiento no crea una segunda fila: 0 filas nuevas."""
    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])

    nuevos = store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])

    assert nuevos == 0
    assert len(store.list_movements(TENANT)) == 1


def test_reingesta_no_modifica_el_id_externo_ni_el_id_de_dominio() -> None:
    """La reingesta refresca los datos leídos, pero nunca la identidad de la fila."""
    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])
    antes = store.list_movements(TENANT)[0]

    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1", valor=Decimal("458300.00"))])
    despues = store.list_movements(TENANT)[0]

    assert despues.id_externo == antes.id_externo
    assert despues.id == antes.id
    assert despues.valor == Decimal("458300.00")


def test_reingesta_no_revierte_el_estado_ya_aplicado() -> None:
    """Un movimiento ya aplicado no vuelve a PENDIENTE por una reingesta."""
    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])
    id_movimiento = store.list_movements(TENANT)[0].id

    store.move_to_state(TENANT, id_movimiento, EstadoMovimiento.APLICADO, recibo_numero="101")
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])

    assert store.list_movements(TENANT)[0].estado is EstadoMovimiento.APLICADO
    assert store.list_movements(TENANT)[0].recibo_numero == "101"


# ─── Identificador de dominio (uuid5) ───────────────────────────


def test_id_de_dominio_uuid5_es_estable_para_mismo_tenant_y_id_externo() -> None:
    """El id de dominio es `uuid5(NAMESPACE, "tenant:id_externo")`: el mismo siempre."""
    primero = id_dominio_movimiento(TENANT, "EXT-1")
    segundo = id_dominio_movimiento(TENANT, "EXT-1")

    assert primero == segundo
    assert primero == str(uuid.uuid5(NAMESPACE_DOMINIO, f"{TENANT}:EXT-1"))

    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])
    assert store.list_movements(TENANT)[0].id == primero


def test_uuid5_difiere_entre_tenants() -> None:
    """El mismo `id_externo` en dos tenants son dos movimientos distintos."""
    id_motoshop = id_dominio_movimiento(TENANT, "EXT-1")
    id_masvital = id_dominio_movimiento(OTRO_TENANT, "EXT-1")

    assert id_motoshop != id_masvital

    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])
    store.upsert_movements(OTRO_TENANT, EMPRESA, [_movimiento("EXT-1")])

    assert len(store.list_movements(TENANT)) == 1
    assert len(store.list_movements(OTRO_TENANT)) == 1


# ─── Aislamiento por tenant ─────────────────────────────────────


def test_movimientos_de_otro_tenant_no_son_visibles() -> None:
    """Las lecturas siempre filtran por tenant."""
    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])
    store.upsert_movements(OTRO_TENANT, EMPRESA, [_movimiento("EXT-1")])

    visibles = store.list_movements(TENANT)

    assert [mov.id_externo for mov in visibles] == ["EXT-1"]
    assert visibles[0].tenant == TENANT
    assert store.find_movement(TENANT, id_dominio_movimiento(OTRO_TENANT, "EXT-1")) is None


def test_move_to_state_no_mueve_movimientos_de_otro_tenant() -> None:
    """Un tenant no puede cambiar el estado de un movimiento de otro tenant."""
    store = FakeBankStore()
    store.upsert_movements(OTRO_TENANT, EMPRESA, [_movimiento("EXT-1")])
    id_movimiento = id_dominio_movimiento(OTRO_TENANT, "EXT-1")

    assert store.move_to_state(TENANT, id_movimiento, EstadoMovimiento.IGNORADO) is False
    assert store.list_movements(OTRO_TENANT)[0].estado is EstadoMovimiento.PENDIENTE


# ─── Listado: filtros y orden ───────────────────────────────────


def test_list_movements_filtra_por_estado_y_rango_de_fechas() -> None:
    """El listado filtra por estado y por rango de fechas."""
    store = FakeBankStore()
    store.upsert_movements(
        TENANT,
        EMPRESA,
        [
            _movimiento("EXT-1", fecha_movimiento=datetime.date(2025, 2, 10)),
            _movimiento("EXT-2", fecha_movimiento=datetime.date(2025, 2, 15)),
            _movimiento("EXT-3", fecha_movimiento=datetime.date(2025, 3, 1)),
        ],
    )
    store.move_to_state(TENANT, id_dominio_movimiento(TENANT, "EXT-2"), EstadoMovimiento.APLICADO)

    por_estado = store.list_movements(TENANT, estado=EstadoMovimiento.APLICADO)
    assert [mov.id_externo for mov in por_estado] == ["EXT-2"]

    por_rango = store.list_movements(
        TENANT, desde=datetime.date(2025, 2, 11), hasta=datetime.date(2025, 2, 28)
    )
    assert [mov.id_externo for mov in por_rango] == ["EXT-2"]

    ambos = store.list_movements(
        TENANT,
        estado=EstadoMovimiento.PENDIENTE,
        desde=datetime.date(2025, 1, 1),
        hasta=datetime.date(2025, 12, 31),
    )
    # Orden del listado: fecha descendente (EXT-3 es de marzo, EXT-1 de febrero).
    assert [mov.id_externo for mov in ambos] == ["EXT-3", "EXT-1"]


def test_list_movements_ordena_por_fecha_descendente_y_desempata_por_id_externo() -> None:
    """El orden es estable: fecha descendente y, a igualdad de fecha, `id_externo`."""
    store = FakeBankStore()
    store.upsert_movements(
        TENANT,
        EMPRESA,
        [
            _movimiento("EXT-B", fecha_movimiento=datetime.date(2025, 2, 10)),
            _movimiento("EXT-A", fecha_movimiento=datetime.date(2025, 2, 10)),
            _movimiento("EXT-C", fecha_movimiento=datetime.date(2025, 3, 1)),
        ],
    )

    orden = [mov.id_externo for mov in store.list_movements(TENANT)]

    assert orden == ["EXT-C", "EXT-A", "EXT-B"]


# ─── Contrato de los modelos ─────────────────────────────────────


def test_el_importe_se_guarda_como_decimal_de_dos_decimales() -> None:
    """El importe es `Decimal` exacto: nunca float."""
    store = FakeBankStore()
    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1", valor="458200.00")])

    valor = store.list_movements(TENANT)[0].valor

    assert isinstance(valor, Decimal)
    assert valor == Decimal("458200.00")
    assert valor.as_tuple().exponent == -2


def test_el_importe_con_mas_de_dos_decimales_es_rechazado() -> None:
    """La columna es DECIMAL(18,2): tres decimales no entran."""
    with pytest.raises(ValidationError):
        _movimiento("EXT-1", valor=Decimal("458200.005"))


def test_un_campo_desconocido_es_rechazado() -> None:
    """Los modelos son cerrados: un campo de más no pasa."""
    with pytest.raises(ValidationError):
        _movimiento("EXT-1", campo_inventado="x")


# ─── El store real habla MySQL 5.0.45 ───────────────────────────


class _Resultado:
    """Resultado mínimo: `fetchall`/`fetchone`/`rowcount`."""

    def __init__(self, filas: list[Any]) -> None:
        self._filas = filas

    def fetchall(self) -> list[Any]:
        return self._filas

    def fetchone(self) -> Any:
        return self._filas[0] if self._filas else None

    @property
    def rowcount(self) -> int:
        return len(self._filas)


class _ConexionFalsa:
    """Conexión mínima que registra el SQL ejecutado."""

    def __init__(self) -> None:
        self.sentencias: list[str] = []
        self.filas: list[list[Any]] = []

    def execute(self, statement: Any, params: Any = None) -> _Resultado:
        self.sentencias.append(str(statement))
        return _Resultado(self.filas.pop(0) if self.filas else [])

    def commit(self) -> None:
        return None


class _MotorFalso:
    """Engine mínimo: `connect()` devuelve la conexión falsa como contexto."""

    def __init__(self, conexion: _ConexionFalsa) -> None:
        self.conexion = conexion

    def connect(self) -> _MotorFalso:
        return self

    def __enter__(self) -> _ConexionFalsa:
        return self.conexion

    def __exit__(self, *args: Any) -> bool:
        return False


def test_el_upsert_real_emite_insert_on_duplicate_key_update() -> None:
    """La ingesta real usa `ON DUPLICATE KEY UPDATE` y no toca la identidad."""
    conexion = _ConexionFalsa()
    store = RealBankStore(engine=_MotorFalso(conexion))

    store.upsert_movements(TENANT, EMPRESA, [_movimiento("EXT-1")])

    inserts = [s for s in conexion.sentencias if s.lstrip().upper().startswith("INSERT")]
    assert len(inserts) == 1
    sql = inserts[0].upper()
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "ON CONFLICT" not in sql
    actualizacion = sql.split("ON DUPLICATE KEY UPDATE", 1)[1]
    assert re.search(r"\bID_EXTERNO\s*=", actualizacion) is None
    assert re.search(r"\bID\s*=", actualizacion) is None


def test_el_upsert_real_cuenta_solo_las_filas_nuevas() -> None:
    """La cuenta de filas nuevas excluye lo que ya existía para el tenant."""
    conexion = _ConexionFalsa()
    conexion.filas.append([("EXT-1",)])  # el SELECT de existentes lo devuelve
    store = RealBankStore(engine=_MotorFalso(conexion))

    nuevos = store.upsert_movements(
        TENANT, EMPRESA, [_movimiento("EXT-1"), _movimiento("EXT-2")]
    )

    assert nuevos == 1


def test_la_lectura_real_siempre_filtra_por_tenant() -> None:
    """Ninguna lectura real puede devolver filas de otro tenant."""
    conexion = _ConexionFalsa()
    store = RealBankStore(engine=_MotorFalso(conexion))

    store.list_movements(TENANT)

    selects = [s for s in conexion.sentencias if s.lstrip().upper().startswith("SELECT")]
    assert selects
    for sql in selects:
        assert "tenant = :tenant" in sql.lower()


def test_la_lectura_real_mapea_las_filas_y_filtra_por_estado() -> None:
    """La lectura real devuelve el modelo y el filtro de estado viaja en el SQL."""
    conexion = _ConexionFalsa()
    conexion.filas.append([_fila_mysql()])
    store = RealBankStore(engine=_MotorFalso(conexion))

    movimientos = store.list_movements(TENANT, estado=EstadoMovimiento.PENDIENTE)

    assert [mov.id_externo for mov in movimientos] == ["EXT-1"]
    assert movimientos[0].valor == Decimal("458200.00")
    assert movimientos[0].estado is EstadoMovimiento.PENDIENTE
    assert "estado = :estado" in conexion.sentencias[-1]


def test_get_bank_store_devuelve_el_doble_falso_bajo_test() -> None:
    """La dependencia de FastAPI resuelve el doble falso en el entorno de pruebas."""
    store = get_bank_store()

    assert isinstance(store, FakeBankStore)


# ─── El DDL y el store hablan el mismo idioma ──────────────────


def test_el_ddl_tiene_las_columnas_la_clave_unica_y_el_indice_del_listado() -> None:
    """El DDL de F9-001 y el SQL del store no pueden divergir."""
    ddl = _DDL.read_text(encoding="utf-8")
    columnas = set(
        re.findall(r"^  (\w+)\s+(?:VARCHAR|CHAR|DATE|DATETIME|DECIMAL|INT|ENUM)", ddl, re.MULTILINE)
    )

    assert {
        "id",
        "tenant",
        "empresa",
        "id_externo",
        "fecha_movimiento",
        "valor",
        "descripcion",
        "referencia",
        "referencia_norm",
        "pagador_nombre",
        "cuenta_origen",
        "estado",
        "recibo_numero",
        "recibo_pref",
        "confianza",
        "razones",
        "scraped_at",
    } <= columnas
    assert "UNIQUE KEY uq_tenant_id_externo (tenant, id_externo)" in ddl
    assert "INDEX idx_estado_fecha (tenant, estado, fecha_movimiento)" in ddl
    assert "DECIMAL(18,2)" in ddl
