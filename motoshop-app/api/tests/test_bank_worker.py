"""Worker del nodo (S6 · 6.2): un job a la vez, lock y estados.

El worker corre **en el nodo local** (el proceso de la API del tenant): toma
el turno de sesión del scraper (lock + 30 s de intervalo mínimo), lee los
movimientos de la cuenta del tenant y **reporta** lo que encontró. Nunca
postea un pago: eso lo confirma el operador en el POS.

    en_cola → ejecutando → (esperando_otp) → resuelto | sin_coincidencia |
                                              ambiguo | fallido

Todo es **offline**: la sesión del portal es el doble `PortalFalso` de
`tests/bank_fakes.py` y el vault es un doble (nada de red ni navegador).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

from motoshop_api.erp.bankreconciliation.jobs import (
    EstadoJob,
    FakeVerificationJobStore,
)
from motoshop_api.erp.bankreconciliation.node_config import NodeConfig, load_node_config
from motoshop_api.erp.bankreconciliation.parser import MovementDirection
from motoshop_api.erp.bankreconciliation.schemas import EstadoMovimiento
from motoshop_api.erp.bankreconciliation.scraper import (
    ScrapedMovement,
    ScrapeResult,
    acquire_session_slot,
)
from motoshop_api.erp.bankreconciliation.store import FakeBankStore
from motoshop_api.erp.bankreconciliation.vault import Entry, VaultNotFound
from motoshop_api.erp.bankreconciliation.worker import BankVerificationWorker
from tests.bank_fakes import PortalFalso, leer_fixture

ETIQUETA_TENANT = "MasVital"
VALOR = Decimal("458200.00")
FACTURA = "FVP-100"


class _VaultFalso:
    """Vault de prueba: entrega la credencial o falla como el vault real."""

    def __init__(self, con_entrada: bool = True) -> None:
        self.con_entrada = con_entrada

    def get_entry(self, name: str) -> Entry:
        if not self.con_entrada:
            raise VaultNotFound("no existe la entrada")
        return Entry(
            username="usuario_secreto",
            password="clave_secreta_123",
            updated_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
        )


def _config(tmp_path: Path, *, tenant: str = "masvital") -> NodeConfig:
    """Configuración de un nodo con el perfil fuera del repo."""
    env = {
        "BANK_SCRAPER_ENABLED": "true",
        "BANK_TENANT": tenant,
        "BANK_ACCOUNT_LABEL": ETIQUETA_TENANT,
        "BANK_CREDENTIAL_ENTRY": f"bancolombia-{tenant}",
        "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
        # Los fixtures son una captura REAL del portal (21 oct 2026).
        "BANK_WINDOW_START": "2026-01-01",
        "BANK_WINDOW_END": "2026-12-31",
    }
    return load_node_config(env)


def _sesion(**extra) -> PortalFalso:
    """Portal falso con las dos páginas de movimientos de los fixtures."""
    return PortalFalso(
        cuentas_html=leer_fixture("cuentas.html"),
        paginas_html=[
            leer_fixture("movimientos_pagina1.html"),
            leer_fixture("movimientos_pagina2.html"),
        ],
        **extra,
    )


def _movimiento(valor: Decimal, *, id_externo: str) -> ScrapedMovement:
    """Movimiento del portal (un ingreso) para las pruebas de clasificación."""
    return ScrapedMovement(
        id_externo=id_externo,
        fecha=datetime.date(2026, 10, 21),
        descripcion="PAGO QR TEST",
        referencia="0092055984",
        referencia_utilizable=True,
        pagador_nombre="TEST",
        valor=valor,
        direccion=MovementDirection.INGRESO,
        es_candidato_pago=True,
        pagina=1,
        cuenta_origen=ETIQUETA_TENANT,
    )


def _resultado(*movimientos: ScrapedMovement) -> ScrapeResult:
    """Resultado de scrape con los movimientos indicados."""
    return ScrapeResult(
        tenant="masvital",
        cuenta=ETIQUETA_TENANT,
        ventana=(
            datetime.datetime(2026, 10, 21, 0, 0, 0),
            datetime.datetime(2026, 10, 21, 23, 59, 59),
        ),
        paginas=1,
        movimientos=tuple(movimientos),
        leido_en=datetime.datetime(2026, 10, 21, 12, 0, 0),
    )


class _ScraperFalso:
    """Scraper que devuelve un resultado preparado (sin navegador ni lock)."""

    def __init__(self, resultado: ScrapeResult) -> None:
        self._resultado = resultado
        self.llamadas = 0

    def scrape(self, config: NodeConfig) -> ScrapeResult:
        self.llamadas += 1
        return self._resultado


def _worker(
    tmp_path: Path,
    *,
    jobs: FakeVerificationJobStore,
    store: FakeBankStore,
    sesion: PortalFalso | None = None,
    scraper_factory=None,
    pedir_codigo=None,
    reloj=None,
) -> BankVerificationWorker:
    """Worker con el scraper real (doble de sesión) o con un scraper preparado."""
    return BankVerificationWorker(
        jobs=jobs,
        config=_config(tmp_path),
        store=store,
        scraper_factory=scraper_factory,
        session_factory=None if scraper_factory else (lambda _cfg: sesion),
        vault=_VaultFalso(),
        pedir_codigo=pedir_codigo,
        reloj=reloj,
        nodo="pc-masvital",
    )


def test_worker_marca_el_job_ejecutando_y_luego_resuelto_con_la_ventana(tmp_path: Path) -> None:
    """El job pasa por `ejecutando` y termina `resuelto` con la ventana leída."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    estados: list[EstadoJob] = []

    def factory(_cfg: NodeConfig) -> PortalFalso:
        # En el momento de abrir la sesión, el job ya está `ejecutando`.
        actual = jobs.get_job(config.tenant, job.job_id)
        assert actual is not None
        estados.append(actual.estado)
        return _sesion()

    worker = BankVerificationWorker(
        jobs=jobs,
        config=config,
        store=store,
        session_factory=factory,
        vault=_VaultFalso(),
        nodo="pc-masvital",
    )

    worker.run_once(job)

    assert estados == [EstadoJob.EJECUTANDO]
    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.RESUELTO
    assert guardado.error_codigo is None
    assert guardado.nodo == "pc-masvital"
    assert guardado.resultado is not None
    assert guardado.resultado["ventana"] == {
        "desde": config.window_start.isoformat(),
        "hasta": config.window_end.isoformat(),
    }
    assert guardado.resultado["nodo"] == "pc-masvital"
    assert guardado.resultado["ingesta_at"]
    # El movimiento del importe buscado es el candidato del job.
    assert guardado.resultado["candidatos"] == 1
    # El worker sólo LEE: el movimiento queda pendiente de conciliación.
    movimientos = store.list_movements(config.tenant)
    assert len(movimientos) > 0
    assert {movimiento.estado for movimiento in movimientos} == {EstadoMovimiento.PENDIENTE}


def test_worker_marca_esperando_otp_ante_de_pedir_el_codigo(tmp_path: Path) -> None:
    """El job pasa por `esperando_otp` ANTES de pedir el código en la consola."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    estados_al_preguntar: list[EstadoJob] = []

    def pedir(_prompt: str) -> str:
        actual = jobs.get_job(config.tenant, job.job_id)
        assert actual is not None
        estados_al_preguntar.append(actual.estado)
        return "483920"

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        sesion=_sesion(otp_html=leer_fixture("login_otp.html")),
        pedir_codigo=pedir,
    )

    worker.run_once(job)

    assert estados_al_preguntar == [EstadoJob.ESPERANDO_OTP]
    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.RESUELTO


def test_worker_marca_fallido_con_el_codigo_de_error_del_portal(tmp_path: Path) -> None:
    """Un fallo del portal deja el job en `fallido` con el código estable."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        sesion=_sesion(sesion_expirada=True),
    )

    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.FALLIDO
    assert guardado.error_codigo == "sesion_expirada"
    # El mensaje crudo (que puede traer datos del portal) no se persiste.
    assert "sesión" not in str(guardado.error_codigo)


def test_worker_no_deja_movimientos_parciales_ante_un_error(tmp_path: Path) -> None:
    """Un antibot en la página 2 deja cero movimientos ingeridos."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        sesion=_sesion(antibot_en_pagina=1),
    )

    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.FALLIDO
    assert guardado.error_codigo == "antibot"
    assert store.list_movements(config.tenant) == []


def test_hilo_que_pierde_el_claim_no_corrompe_al_ganador(tmp_path: Path) -> None:
    """Doble despacho del mismo job: el segundo `run_once` muere sin tocar nada.

    El despachador levanta un hilo por petición; en el doble clic los dos
    hilos corren `run_once` con el mismo job. El claim atómico decide: el
    ganador raspa y clasifica; el perdedor muere **antes de raspear** y sin
    escribir `fallido` (que enmascaraba el resultado del ganador).
    """
    jobs = FakeVerificationJobStore()
    scraper = _ScraperFalso(_resultado(_movimiento(VALOR, id_externo="t1")))
    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=FakeBankStore(),
        scraper_factory=lambda pedir_codigo: scraper,
    )
    job = jobs.create_job("masvital", FACTURA, VALOR)

    # Otro hilo ya reclamó el job (el ganador del doble despacho).
    assert jobs.reclamar_ejecucion("masvital", job.job_id, nodo="pc-masvital")
    antes = jobs.get_job("masvital", job.job_id)

    worker.run_once(job)

    despues = jobs.get_job("masvital", job.job_id)
    assert despues is not None
    assert despues.estado is antes.estado is EstadoJob.EJECUTANDO
    # El perdedor no toca el portal ni vuelve a raspar.
    assert scraper.llamadas == 0


def test_worker_rechaza_un_segundo_job_simultaneo(tmp_path: Path) -> None:
    """Con el turno de sesión tomado, el segundo job no entra al portal."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    worker = _worker(tmp_path, jobs=jobs, store=store, sesion=_sesion())

    with acquire_session_slot(config):
        worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.FALLIDO
    assert guardado.error_codigo == "ejecucion_concurrente"
    assert store.list_movements(config.tenant) == []


def test_worker_respeta_el_intervalo_minimo_entre_corridas(tmp_path: Path) -> None:
    """Dos corridas seguidas violan el intervalo mínimo de 30 s del nodo."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    instante = datetime.datetime(2026, 10, 21, 8, 0, 0)
    primero = jobs.create_job(config.tenant, FACTURA, VALOR)
    segundo = jobs.create_job(config.tenant, "FVP-200", Decimal("1.00"))
    worker = _worker(tmp_path, jobs=jobs, store=store, sesion=_sesion(), reloj=lambda: instante)

    worker.run_once(primero)
    worker.run_once(segundo)

    primero_guardado = jobs.get_job(config.tenant, primero.job_id)
    segundo_guardado = jobs.get_job(config.tenant, segundo.job_id)
    assert primero_guardado is not None
    assert primero_guardado.estado == EstadoJob.RESUELTO
    assert segundo_guardado is not None
    assert segundo_guardado.estado == EstadoJob.FALLIDO
    assert segundo_guardado.error_codigo == "intervalo_minimo"


# --- Triangulación de la clasificación ---


def test_sin_coincidencia_cuando_ningun_movimiento_tiene_el_importe(tmp_path: Path) -> None:
    """Si el importe no aparece en la ventana, el job queda `sin_coincidencia`."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, Decimal("999999.00"))
    scraper = _ScraperFalso(_resultado(_movimiento(Decimal("458200.00"), id_externo="a")))

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
    )

    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.SIN_COINCIDENCIA
    assert guardado.resultado is not None
    assert guardado.resultado["candidatos"] == 0


def test_dos_movimientos_del_mismo_importe_dejan_el_job_ambiguo(tmp_path: Path) -> None:
    """Dos candidatos con el mismo importe: `ambiguo`, y no se elige ninguno."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    scraper = _ScraperFalso(
        _resultado(
            _movimiento(VALOR, id_externo="a"),
            _movimiento(VALOR, id_externo="b"),
        )
    )

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
    )

    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.AMBIGUO
    assert guardado.resultado is not None
    assert guardado.resultado["candidatos"] == 2


def test_un_egreso_no_es_candidato_del_job(tmp_path: Path) -> None:
    """Un movimiento de salida con el mismo importe NO resuelve el job."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    egreso = ScrapedMovement(
        id_externo="egreso",
        fecha=datetime.date(2026, 10, 21),
        descripcion="COMPRA",
        referencia="",
        referencia_utilizable=False,
        pagador_nombre="",
        valor=VALOR,
        direccion=MovementDirection.EGRESO,
        es_candidato_pago=False,
        pagina=1,
        cuenta_origen=ETIQUETA_TENANT,
    )
    scraper = _ScraperFalso(_resultado(egreso))

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
    )

    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.SIN_COINCIDENCIA
