"""Jobs de verificación bancaria (S6 · 6.1): identidad, estados e idempotencia.

El job tiene dos identidades: `id` es el identificador de **dominio**
(`uuid5` de `tenant:factura_id:valor`, estable ⇒ pedir dos veces la misma
verificación devuelve el **mismo job**) y `job_id` es el **público**
(`uuid4`, el que viaja en la URL y sondea el front).

Los estados son exactamente los del contrato: `en_cola`, `ejecutando`,
`esperando_otp`, `resuelto`, `sin_coincidencia`, `ambiguo`, `fallido`,
`expirado`.
"""


from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from motoshop_api.erp.bankreconciliation.jobs import (
    ESTADOS_DEL_JOB,
    ESTADOS_TERMINALES,
    EstadoJob,
    FakeVerificationJobStore,
    id_dominio_job,
)
from motoshop_api.erp.bankreconciliation.store import NAMESPACE_DOMINIO

TENANT = "masvital"
OTRO_TENANT = "motoshop"
FACTURA = "FVP-100"
VALOR = Decimal("458200.00")


def test_id_del_job_es_uuid5_estable_para_mismo_tenant_factura_y_valor() -> None:
    """El id de dominio es el `uuid5` del contrato y no depende del proceso."""
    store = FakeVerificationJobStore()

    job = store.create_job(TENANT, FACTURA, VALOR)

    esperado = str(uuid.uuid5(NAMESPACE_DOMINIO, f"{TENANT}:{FACTURA}:{VALOR}"))
    assert job.id == esperado
    assert job.id == id_dominio_job(TENANT, FACTURA, VALOR)
    # Otra instancia (otro proceso, otro nodo) calcula el mismo id.
    assert FakeVerificationJobStore().create_job(TENANT, FACTURA, VALOR).id == job.id


def test_job_id_http_es_uuid4_distinto_del_id_de_dominio() -> None:
    """El id público es un `uuid4` y nunca coincide con el id de dominio."""
    store = FakeVerificationJobStore()

    job = store.create_job(TENANT, FACTURA, VALOR)
    otro = store.create_job(TENANT, FACTURA, Decimal("1.00"))

    assert job.job_id != job.id
    assert uuid.UUID(job.job_id).version == 4
    assert uuid.UUID(job.id).version == 5
    assert otro.job_id != job.job_id


def test_estados_del_job_son_los_del_contrato() -> None:
    """La máquina de estados del contrato, sin estados de más ni de menos."""
    esperados = {
        "en_cola",
        "ejecutando",
        "esperando_otp",
        "resuelto",
        "sin_coincidencia",
        "ambiguo",
        "fallido",
        "expirado",
    }
    assert {estado.value for estado in EstadoJob} == esperados
    assert frozenset(esperados) == ESTADOS_DEL_JOB
    assert EstadoJob.EN_COLA == "en_cola"
    # Los estados terminales son los que ya no admiten más transiciones.
    assert {estado.value for estado in ESTADOS_TERMINALES} == {
        "resuelto",
        "sin_coincidencia",
        "ambiguo",
        "fallido",
        "expirado",
    }


def test_segunda_creacion_del_mismo_job_devuelve_el_mismo_job_id() -> None:
    """Pedir dos veces la misma verificación NO crea un segundo job."""
    store = FakeVerificationJobStore()

    primero = store.create_job(TENANT, FACTURA, VALOR)
    segundo = store.create_job(TENANT, FACTURA, VALOR)

    assert segundo.job_id == primero.job_id
    assert segundo.id == primero.id
    assert segundo.creado_en == primero.creado_en
    assert len(store.jobs) == 1


def test_job_actualiza_estado_y_marca_error_sin_filas_parciales() -> None:
    """`update_job` cambia el estado y graba el código de error; no inventa filas."""
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)

    assert store.update_job(TENANT, job.job_id, EstadoJob.EJECUTANDO) is True
    assert store.update_job(
        TENANT, job.job_id, EstadoJob.FALLIDO, error_codigo="credencial_ausente"
    ) is True

    guardado = store.get_job(TENANT, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.FALLIDO
    assert guardado.error_codigo == "credencial_ausente"
    assert guardado.resultado is None
    # Un fallo no crea filas ni toca la fila de otro tenant.
    assert len(store.jobs) == 1
    assert store.get_job(OTRO_TENANT, job.job_id) is None
    # Un job inexistente no se crea: la actualización falla limpio.
    assert (
        store.update_job(
            TENANT, "00000000-0000-4000-8000-000000000000", EstadoJob.FALLIDO
        )
        is False
    )
    assert len(store.jobs) == 1


def test_job_expira_tras_el_ttl() -> None:
    """Pasado el TTL el job pasa a `expirado`; antes no se toca."""
    instante = datetime.datetime(2026, 10, 22, 8, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante, ttl_segundos=30)

    job = store.create_job(TENANT, FACTURA, VALOR)
    assert job.estado == EstadoJob.EN_COLA
    assert job.expira_en == instante + datetime.timedelta(seconds=30)

    assert store.expire_stale_jobs(instante + datetime.timedelta(seconds=29)) == 0
    vigente = store.get_job(TENANT, job.job_id)
    assert vigente is not None
    assert vigente.estado == EstadoJob.EN_COLA

    assert store.expire_stale_jobs(instante + datetime.timedelta(seconds=31)) == 1
    expirado = store.get_job(TENANT, job.job_id)
    assert expirado is not None
    assert expirado.estado == EstadoJob.EXPIRADO


# --- Triangulación: aislamiento, normalización del importe y estados terminales ---


def test_el_job_de_otro_tenant_no_es_visible() -> None:
    """El mismo `job_id` de otro tenant no existe: no se cruzan tenants."""
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)

    assert store.get_job(OTRO_TENANT, job.job_id) is None
    assert (
        store.update_job(OTRO_TENANT, job.job_id, EstadoJob.FALLIDO) is False
    )
    intacto = store.get_job(TENANT, job.job_id)
    assert intacto is not None
    assert intacto.estado == EstadoJob.EN_COLA


def test_el_valor_se_normaliza_a_dos_decimales() -> None:
    """`458200` y `458200.00` son el mismo importe ⇒ el mismo job."""
    store = FakeVerificationJobStore()

    primero = store.create_job(TENANT, FACTURA, Decimal("458200"))
    segundo = store.create_job(TENANT, FACTURA, Decimal("458200.00"))

    assert primero.id == segundo.id
    assert primero.job_id == segundo.job_id
    assert primero.valor == Decimal("458200.00")
    assert primero.valor.as_tuple().exponent == -2


def test_un_job_terminado_no_expira() -> None:
    """Un job `resuelto` no se toca aunque su TTL ya haya pasado."""
    instante = datetime.datetime(2026, 10, 22, 8, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante, ttl_segundos=30)
    job = store.create_job(TENANT, FACTURA, VALOR)
    store.update_job(TENANT, job.job_id, EstadoJob.RESUELTO, resultado={"candidatos": 1})

    assert store.expire_stale_jobs(instante + datetime.timedelta(hours=1)) == 0

    resuelto = store.get_job(TENANT, job.job_id)
    assert resuelto is not None
    assert resuelto.estado == EstadoJob.RESUELTO
    assert resuelto.resultado == {"candidatos": 1}


def test_el_resultado_se_guarda_como_json_en_la_fila() -> None:
    """`resultado` es un diccionario libre (la ventana, el nodo, la ingesta)."""
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)

    store.update_job(
        TENANT,
        job.job_id,
        EstadoJob.RESUELTO,
        resultado={"ventana": {"desde": "2026-10-22T00:00:00"}, "nodo": "pc-motoshop"},
    )

    guardado = store.get_job(TENANT, job.job_id)
    assert guardado is not None
    assert guardado.resultado == {
        "ventana": {"desde": "2026-10-22T00:00:00"},
        "nodo": "pc-motoshop",
    }
