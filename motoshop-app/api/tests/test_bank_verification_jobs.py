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
import threading
import uuid
from decimal import Decimal

import pytest

from motoshop_api.erp.bankreconciliation.jobs import (
    CODIGO_SIN_NODO,
    ESTADOS_DEL_JOB,
    ESTADOS_TERMINALES,
    EstadoJob,
    FakeVerificationJobStore,
    id_dominio_job,
    ttl_cola_segundos,
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
    assert (
        store.update_job(TENANT, job.job_id, EstadoJob.FALLIDO, error_codigo="credencial_ausente")
        is True
    )

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
        store.update_job(TENANT, "00000000-0000-4000-8000-000000000000", EstadoJob.FALLIDO) is False
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
    assert store.update_job(OTRO_TENANT, job.job_id, EstadoJob.FALLIDO) is False
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


def test_un_job_terminado_no_bloquea_el_reintento() -> None:
    """Si el intento falló, el operador puede pedir la misma verificación otra vez.

    El job es de dominio (`tenant:factura:valor`), así que sin revivir la fila
    una factura cuya verificación falló quedaría bloqueada para siempre.
    """
    instante = datetime.datetime(2026, 10, 22, 8, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante)
    primero = store.create_job(TENANT, FACTURA, VALOR)
    store.update_job(
        TENANT,
        primero.job_id,
        EstadoJob.FALLIDO,
        resultado={"candidatos": 0},
        error_codigo="credencial_ausente",
    )

    segundo = store.create_job(TENANT, FACTURA, VALOR)

    assert segundo.id == primero.id
    assert segundo.job_id != primero.job_id
    assert segundo.estado == EstadoJob.EN_COLA
    assert segundo.error_codigo is None
    assert segundo.resultado is None
    assert segundo.creado_en == instante
    assert len(store.jobs) == 1


def test_un_job_en_curso_no_se_duplica_al_pedirlo_de_nuevo() -> None:
    """La idempotencia sigue protegiendo el scrape que estǭ corriendo."""
    store = FakeVerificationJobStore()
    primero = store.create_job(TENANT, FACTURA, VALOR)
    store.update_job(TENANT, primero.job_id, EstadoJob.EJECUTANDO)

    segundo = store.create_job(TENANT, FACTURA, VALOR)

    assert segundo.job_id == primero.job_id
    assert segundo.estado == EstadoJob.EJECUTANDO
    assert len(store.jobs) == 1


def test_reclamar_ejecucion_toma_el_job_en_cola_una_sola_vez() -> None:
    """El claim atómico `en_cola → ejecutando` lo gana un único hilo.

    El despacho levanta un hilo por petición: en el doble clic llegan dos
    hilos al mismo job. El que pierde el claim no debe tocar estados (antes
    marcaba `fallido` y enmascaraba el resultado real del scrape).
    """
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)

    assert store.reclamar_ejecucion(TENANT, job.job_id, nodo="nodo-test") is True
    tomado = store.get_job(TENANT, job.job_id)
    assert tomado.estado is EstadoJob.EJECUTANDO
    assert tomado.nodo == "nodo-test"

    assert store.reclamar_ejecucion(TENANT, job.job_id) is False
    assert store.get_job(TENANT, job.job_id).estado is EstadoJob.EJECUTANDO


def test_reclamar_ejecucion_no_resucita_un_job_terminado() -> None:
    """Un job en estado terminal ya no es reclamable (el revivir es de create_job)."""
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)
    store.update_job(TENANT, job.job_id, EstadoJob.SIN_COINCIDENCIA)

    assert store.reclamar_ejecucion(TENANT, job.job_id) is False
    assert store.get_job(TENANT, job.job_id).estado is EstadoJob.SIN_COINCIDENCIA


# --- Job empantanado: vencido antes del claim (fix de 154ddf3) ---


def test_un_job_en_cola_vencido_se_revive_con_job_id_nuevo() -> None:
    """Un `en_cola` que vence antes del claim no queda empantanado.

    `reclamar_ejecucion` exige `expira_en > now`: si el job vence antes de que
    el worker lo tome, ningún hilo lo reclama y ningún reintento lo sacaba
    (quedaba `en_cola` para siempre, con el `job_id` viejo y la UI sondeando
    en vano). El reintento tiene que devolver un job **nuevo** y ejecutable.
    """
    ahora = [datetime.datetime(2026, 10, 22, 8, 0, 0)]
    store = FakeVerificationJobStore(reloj=lambda: ahora[0], ttl_segundos=30)
    primero = store.create_job(TENANT, FACTURA, VALOR)

    # Nadie lo reclama y vence: el claim que ahora fallaría, no debe dejarlo clavado.
    ahora[0] += datetime.timedelta(seconds=31)
    segundo = store.create_job(TENANT, FACTURA, VALOR)

    assert segundo.id == primero.id
    assert segundo.job_id != primero.job_id
    assert segundo.estado is EstadoJob.EN_COLA
    assert segundo.expira_en == ahora[0] + datetime.timedelta(seconds=30)
    assert store.reclamar_ejecucion(TENANT, segundo.job_id) is True


def test_un_job_en_curso_vigente_no_se_revive() -> None:
    """La idempotencia no toca un job en curso que sigue dentro del TTL."""
    ahora = [datetime.datetime(2026, 10, 22, 8, 0, 0)]
    store = FakeVerificationJobStore(reloj=lambda: ahora[0], ttl_segundos=300)
    primero = store.create_job(TENANT, FACTURA, VALOR)

    ahora[0] += datetime.timedelta(seconds=120)  # sigue vigente
    segundo = store.create_job(TENANT, FACTURA, VALOR)
    assert segundo.job_id == primero.job_id
    assert segundo.estado is EstadoJob.EN_COLA
    assert segundo.expira_en == primero.expira_en

    # Y también protege el scrape en vuelo (`ejecutando` vigente).
    assert store.reclamar_ejecucion(TENANT, primero.job_id) is True
    ahora[0] += datetime.timedelta(seconds=60)
    tercero = store.create_job(TENANT, FACTURA, VALOR)
    assert tercero.job_id == primero.job_id
    assert tercero.estado is EstadoJob.EJECUTANDO


def test_un_job_ejecutando_vencido_se_recupera_con_job_id_nuevo() -> None:
    """Si el worker muere sin cerrar (`ejecutando` vencido), el reintento revive."""
    ahora = [datetime.datetime(2026, 10, 22, 8, 0, 0)]
    store = FakeVerificationJobStore(reloj=lambda: ahora[0], ttl_segundos=30)
    primero = store.create_job(TENANT, FACTURA, VALOR)
    assert store.reclamar_ejecucion(TENANT, primero.job_id) is True

    ahora[0] += datetime.timedelta(seconds=31)
    segundo = store.create_job(TENANT, FACTURA, VALOR)

    assert segundo.job_id != primero.job_id
    assert segundo.estado is EstadoJob.EN_COLA
    assert store.reclamar_ejecucion(TENANT, segundo.job_id) is True


def test_el_claim_es_unico_con_dos_hilos() -> None:
    """Dos hilos reclamando el mismo job a la vez: exactamente uno gana."""
    store = FakeVerificationJobStore()
    job = store.create_job(TENANT, FACTURA, VALOR)

    resultados: list[bool] = []
    barrera = threading.Barrier(2)

    def reclamar() -> None:
        barrera.wait()
        resultados.append(store.reclamar_ejecucion(TENANT, job.job_id))

    hilos = [threading.Thread(target=reclamar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == [False, True]
    assert store.get_job(TENANT, job.job_id).estado is EstadoJob.EJECUTANDO


# --- TTL de cola: 900 s esperando nodo, `sin_nodo` al vencer -----------------


def test_la_cola_espera_900_segundos_por_defecto() -> None:
    """El job nace con el reloj de cola (900 s), no con los 300 s del scrape."""
    instante = datetime.datetime(2026, 10, 26, 12, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante)

    job = store.create_job(TENANT, FACTURA, VALOR)

    assert ttl_cola_segundos() == 900
    assert job.expira_en == instante + datetime.timedelta(seconds=900)


def test_la_cola_vive_a_los_301_segundos_y_vence_con_sin_nodo_a_los_901() -> None:
    """301 s sigue en cola; 901 s es `expirado`/`sin_nodo`, nunca `fallido`."""
    instante = datetime.datetime(2026, 10, 26, 12, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante)
    job = store.create_job(TENANT, FACTURA, VALOR)

    assert store.expire_stale_jobs(instante + datetime.timedelta(seconds=301)) == 0
    viva = store.get_job(TENANT, job.job_id)
    assert viva is not None
    assert viva.estado is EstadoJob.EN_COLA

    assert store.expire_stale_jobs(instante + datetime.timedelta(seconds=901)) == 1
    vencida = store.get_job(TENANT, job.job_id)
    assert vencida is not None
    assert vencida.estado is EstadoJob.EXPIRADO
    assert vencida.error_codigo == CODIGO_SIN_NODO


def test_el_reloj_de_cola_sale_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """`BANK_JOB_QUEUE_TTL` mueve el reloj; un valor invalido no rompe nada."""
    monkeypatch.setenv("BANK_JOB_QUEUE_TTL", "1200")
    instante = datetime.datetime(2026, 10, 26, 12, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante)

    assert ttl_cola_segundos() == 1200
    assert store.create_job(TENANT, FACTURA, VALOR).expira_en == (
        instante + datetime.timedelta(seconds=1200)
    )

    for invalido in ("", "abc", "0", "-5"):
        monkeypatch.setenv("BANK_JOB_QUEUE_TTL", invalido)
        assert ttl_cola_segundos() == 900


def test_un_ejecutando_vencido_no_inventa_motivo() -> None:
    """El barrido cierra el `ejecutando` colgado; el rescate con motivo es del router."""
    instante = datetime.datetime(2026, 10, 26, 12, 0, 0)
    store = FakeVerificationJobStore(reloj=lambda: instante)
    job = store.create_job(TENANT, FACTURA, VALOR)
    assert store.reclamar_ejecucion(TENANT, job.job_id) is True

    assert store.expire_stale_jobs(instante + datetime.timedelta(seconds=901)) == 1
    colgado = store.get_job(TENANT, job.job_id)
    assert colgado is not None
    assert colgado.estado is EstadoJob.EXPIRADO
    assert colgado.error_codigo is None


def test_el_motivo_sin_nodo_es_el_mismo_del_plano_de_control() -> None:
    """Un solo motivo para la misma situacion: no puede derivar entre modulos."""
    from motoshop_api.erp.bankreconciliation.node_router import (
        CODIGO_SIN_NODO as DEL_PLANO_DE_CONTROL,
    )

    assert CODIGO_SIN_NODO == DEL_PLANO_DE_CONTROL == "sin_nodo"
