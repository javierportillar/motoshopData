"""Worker del nodo (S6 Â· 6.2): un job a la vez, lock y estados.

El worker corre **en el nodo local** (el proceso de la API del tenant): toma
el turno de sesiÃ³n del scraper (lock + 30 s de intervalo mÃ­nimo), lee los
movimientos de la cuenta del tenant y **reporta** lo que encontrÃ³. Nunca
postea un pago: eso lo confirma el operador en el POS.

    en_cola â†’ ejecutando â†’ (esperando_otp) â†’ resuelto | sin_coincidencia |
                                              ambiguo | fallido

Todo es **offline**: la sesiÃ³n del portal es el doble `PortalFalso` de
`tests/bank_fakes.py` y el vault es un doble (nada de red ni navegador).
"""

from __future__ import annotations

import dataclasses
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
    BankScrapeError,
    ScrapedMovement,
    ScrapeResult,
    acquire_session_slot,
)
from motoshop_api.erp.bankreconciliation.store import FakeBankStore
from motoshop_api.erp.bankreconciliation.vault import Entry, VaultNotFound
from motoshop_api.erp.bankreconciliation.worker import (
    ESPERA_REINTENTO_SEG,
    BankVerificationWorker,
)
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
    """ConfiguraciÃ³n de un nodo con el perfil fuera del repo."""
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
    """Portal falso con las dos pÃ¡ginas de movimientos de los fixtures."""
    return PortalFalso(
        cuentas_html=leer_fixture("cuentas.html"),
        paginas_html=[
            leer_fixture("movimientos_pagina1.html"),
            leer_fixture("movimientos_pagina2.html"),
        ],
        **extra,
    )


def _movimiento(valor: Decimal, *, id_externo: str) -> ScrapedMovement:
    """Movimiento del portal (un ingreso) para las pruebas de clasificaciÃ³n."""
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

    def scrape(self, config: NodeConfig, on_progress=None) -> ScrapeResult:
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
    esperar=None,
    facturas=None,
) -> BankVerificationWorker:
    """Worker con el scraper real (doble de sesiÃ³n) o con un scraper preparado."""
    return BankVerificationWorker(
        jobs=jobs,
        config=_config(tmp_path),
        store=store,
        scraper_factory=scraper_factory,
        session_factory=None if scraper_factory else (lambda _cfg: sesion),
        vault=_VaultFalso(),
        pedir_codigo=pedir_codigo,
        reloj=reloj,
        esperar=esperar,
        facturas=facturas or (lambda _fid: None),
        nodo="pc-masvital",
    )


def test_worker_marca_el_job_ejecutando_y_luego_resuelto_con_la_ventana(tmp_path: Path) -> None:
    """El job pasa por `ejecutando` y termina `resuelto` con la ventana leÃ­da."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    estados: list[EstadoJob] = []

    def factory(_cfg: NodeConfig) -> PortalFalso:
        # En el momento de abrir la sesiÃ³n, el job ya estÃ¡ `ejecutando`.
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
        facturas=lambda _fid: None,
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
    # El worker sÃ³lo LEE: el movimiento queda pendiente de conciliaciÃ³n.
    movimientos = store.list_movements(config.tenant)
    assert len(movimientos) > 0
    assert {movimiento.estado for movimiento in movimientos} == {EstadoMovimiento.PENDIENTE}


def test_worker_marca_esperando_otp_ante_de_pedir_el_codigo(tmp_path: Path) -> None:
    """El job pasa por `esperando_otp` ANTES de pedir el cÃ³digo en la consola."""
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
    """Un fallo del portal deja el job en `fallido` con el cÃ³digo estable."""
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
    assert "sesiÃ³n" not in str(guardado.error_codigo)


def test_worker_no_deja_movimientos_parciales_ante_un_error(tmp_path: Path) -> None:
    """Un antibot en la pÃ¡gina 2 deja cero movimientos ingeridos."""
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

    El despachador levanta un hilo por peticiÃ³n; en el doble clic los dos
    hilos corren `run_once` con el mismo job. El claim atÃ³mico decide: el
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

    # Otro hilo ya reclamÃ³ el job (el ganador del doble despacho).
    assert jobs.reclamar_ejecucion("masvital", job.job_id, nodo="pc-masvital")
    antes = jobs.get_job("masvital", job.job_id)

    worker.run_once(job)

    despues = jobs.get_job("masvital", job.job_id)
    assert despues is not None
    assert despues.estado is antes.estado is EstadoJob.EJECUTANDO
    # El perdedor no toca el portal ni vuelve a raspar.
    assert scraper.llamadas == 0


def test_worker_rechaza_un_segundo_job_simultaneo(tmp_path: Path) -> None:
    """Con el turno de sesiÃ³n tomado, el segundo job no entra al portal."""
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
    """Dos corridas seguidas violan el intervalo mÃ­nimo de 30 s del nodo."""
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


# --- TriangulaciÃ³n de la clasificaciÃ³n ---


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

class _ScraperIntermitente:
    """Scraper que falla las primeras N veces y despues entrega el resultado."""

    def __init__(
        self,
        resultado: ScrapeResult,
        *,
        fallos: int,
        codigo: str = "portal_no_disponible",
    ) -> None:
        self._resultado = resultado
        self._fallos = fallos
        self._codigo = codigo
        self.llamadas = 0

    def scrape(self, config: NodeConfig, on_progress=None) -> ScrapeResult:
        self.llamadas += 1
        if self.llamadas <= self._fallos:
            raise BankScrapeError(self._codigo, "el portal no respondio: timeout")
        return self._resultado


def _worker_con_scraper(
    tmp_path: Path,
    *,
    jobs: FakeVerificationJobStore,
    store: FakeBankStore,
    scraper: _ScraperIntermitente,
    esperar=None,
    reloj=None,
) -> BankVerificationWorker:
    return _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
        esperar=esperar,
        reloj=reloj,
    )


def test_worker_reintenta_una_vez_cuando_el_portal_no_responde(tmp_path: Path) -> None:
    """Un timeout del portal se reintenta una sola vez y el job termina bien."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    scraper = _ScraperIntermitente(_resultado(), fallos=1)
    esperas: list[float] = []

    worker = _worker_con_scraper(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper=scraper,
        esperar=esperas.append,
    )
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert scraper.llamadas == 2
    assert esperas == [ESPERA_REINTENTO_SEG]
    assert guardado.estado != EstadoJob.FALLIDO


def test_worker_no_reintenta_mas_de_una_vez(tmp_path: Path) -> None:
    """Si el segundo intento tambien falla, el job queda fallido."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    scraper = _ScraperIntermitente(_resultado(), fallos=2)
    esperas: list[float] = []

    worker = _worker_con_scraper(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper=scraper,
        esperar=esperas.append,
    )
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert scraper.llamadas == 2
    assert len(esperas) == 1
    assert guardado.estado == EstadoJob.FALLIDO
    assert guardado.error_codigo == "portal_no_disponible"


def test_worker_no_reintenta_codigos_que_no_son_del_portal(tmp_path: Path) -> None:
    """Una sesion expirada no se reintenta: no es un timeout de red."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    scraper = _ScraperIntermitente(_resultado(), fallos=1, codigo="sesion_expirada")
    esperas: list[float] = []

    worker = _worker_con_scraper(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper=scraper,
        esperar=esperas.append,
    )
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert scraper.llamadas == 1
    assert esperas == []
    assert guardado.error_codigo == "sesion_expirada"


def test_worker_no_reintenta_si_el_job_ya_vencio(tmp_path: Path) -> None:
    """Sin tiempo antes del vencimiento, no se duerme: el job falla ya."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    vencido = dataclasses.replace(
        job, expira_en=datetime.datetime.now() - datetime.timedelta(seconds=1)
    )
    scraper = _ScraperIntermitente(_resultado(), fallos=1)
    esperas: list[float] = []

    worker = _worker_con_scraper(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper=scraper,
        esperar=esperas.append,
    )
    worker.run_once(vencido)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert scraper.llamadas == 1
    assert esperas == []
    assert guardado.estado == EstadoJob.FALLIDO

def test_worker_suma_nitter_y_cliente_nombre_de_la_factura(tmp_path: Path) -> None:
    """El candidato lleva el NIT y el cliente de la FACTURA, no del banco."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)
    pedidas: list[str] = []

    def facturas(factura_id: str) -> dict[str, str]:
        pedidas.append(factura_id)
        # NIT real, no el comodin 222222222: el comodin (consumidor final) se
        # quita a proposito del candidato (ver `_candidato_con_senales`), asi
        # que usarlo aca probaria la regla contraria a la que este test cubre.
        return {"nitter": "900123456", "cliente_nombre": "CONSUMIDOR"}

    worker = _worker(tmp_path, jobs=jobs, store=store, sesion=_sesion(), facturas=facturas)
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None and guardado.resultado is not None
    candidato = guardado.resultado["candidato"]
    assert candidato["nitter"] == "900123456"
    assert candidato["cliente_nombre"] == "CONSUMIDOR"
    # Los datos del banco siguen intactos.
    assert "pagador_nombre" in candidato
    assert "referencia" in candidato
    assert candidato["id"]
    assert pedidas == [FACTURA]


def test_worker_etiqueta_consumidor_final_sin_nit(tmp_path: Path) -> None:
    """El comodin 222222222 no se muestra: el chulo dice CONSUMIDOR FINAL."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)

    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        sesion=_sesion(),
        facturas=lambda _fid: {"nitter": "222222222", "cliente_nombre": "CONSUMIDOR"},
    )
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None and guardado.resultado is not None
    candidato = guardado.resultado["candidato"]
    assert "nitter" not in candidato
    assert candidato["cliente_nombre"] == "CONSUMIDOR FINAL"


def test_worker_no_se_cae_si_el_erp_no_devuelve_la_factura(tmp_path: Path) -> None:
    """Sin factura, el job resuelve igual: el NIT es un extra, no un requisito."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, FACTURA, VALOR)

    def facturas(_factura_id: str) -> dict[str, str]:
        raise RuntimeError("ERP caido")

    worker = _worker(tmp_path, jobs=jobs, store=store, sesion=_sesion(), facturas=facturas)
    worker.run_once(job)

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None and guardado.estado == EstadoJob.RESUELTO
    assert guardado.resultado is not None
    candidato = guardado.resultado["candidato"]
    assert "nitter" not in candidato
    assert "cliente_nombre" not in candidato


def test_variantes_numfven_quita_el_prefijo_del_pos() -> None:
    """El POS manda `FVP-3600` y el catalogo guarda `3600`."""
    from motoshop_api.erp.bankreconciliation.worker import _variantes_numfven

    assert _variantes_numfven("FVP-3600") == ["FVP-3600", "3600"]
    assert _variantes_numfven("3600") == ["3600"]


# --- Modo "pago": sin factura, el POS manda importe (+ NIT y nombre) ---


def _movimiento_nombrado(valor: Decimal, *, id_externo: str, pagador: str) -> ScrapedMovement:
    """Movimiento del portal con el nombre que publicó el banco."""
    return dataclasses.replace(
        _movimiento(valor, id_externo=id_externo),
        pagador_nombre=pagador,
        descripcion=f"PAGO QR {pagador}",
    )


def _job_de_pago(
    jobs: FakeVerificationJobStore,
    valor: Decimal = VALOR,
    **solicitud,
) -> object:
    """Job de modo pago: sin factura y con la solicitud del POS."""
    return jobs.create_job("masvital", "", valor, solicitud={"modo": "pago", **solicitud})


def test_modo_pago_resuelve_con_un_solo_candidato(tmp_path: Path) -> None:
    """Un único pago con el importe exacto resuelve y devuelve NIT y nombre."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = _job_de_pago(jobs, nitter="900123456", nombre_esperado="Valeria Castrillón")
    scraper = _ScraperFalso(
        _resultado(_movimiento_nombrado(VALOR, id_externo="a", pagador="VALERIA CASTRILLON SAL"))
    )
    worker = _worker(tmp_path, jobs=jobs, store=store, scraper_factory=lambda _pedir: scraper)

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.RESUELTO
    candidato = (guardado.resultado or {})["candidato"]
    assert candidato["pagador_nombre"] == "VALERIA CASTRILLON SAL"
    assert candidato["nitter"] == "900123456"
    assert candidato["cliente_nombre"] == "Valeria Castrillón"
    assert candidato["coincide_nombre"] is True
    assert "candidatos_detalle" not in (guardado.resultado or {})


def test_modo_pago_sin_nit_ni_nombre_no_rompe(tmp_path: Path) -> None:
    """Verificar sólo por importe es válido: no se inventan datos del cliente."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = _job_de_pago(jobs)
    scraper = _ScraperFalso(_resultado(_movimiento(VALOR, id_externo="a")))
    worker = _worker(tmp_path, jobs=jobs, store=store, scraper_factory=lambda _pedir: scraper)

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.RESUELTO
    candidato = (guardado.resultado or {})["candidato"]
    assert "nitter" not in candidato
    assert "cliente_nombre" not in candidato
    assert "coincide_nombre" not in candidato


def test_modo_pago_con_dos_iguales_sigue_ambiguo_aunque_coincida_el_nombre(
    tmp_path: Path,
) -> None:
    """`nombre_esperado` es señal, no decisión: dos importes iguales = ambiguo."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = _job_de_pago(jobs, nombre_esperado="Valeria Castrillón")
    scraper = _ScraperFalso(
        _resultado(
            _movimiento_nombrado(VALOR, id_externo="a", pagador="OTRO PAGADOR"),
            _movimiento_nombrado(VALOR, id_externo="b", pagador="VALERIA CASTRILLON SAL"),
        )
    )
    worker = _worker(tmp_path, jobs=jobs, store=store, scraper_factory=lambda _pedir: scraper)

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.AMBIGUO
    resultado = guardado.resultado or {}
    assert resultado["candidato"] is None
    detalle = resultado["candidatos_detalle"]
    assert len(detalle) == 2
    # El que coincide por nombre va primero, pero el estado no cambia.
    assert detalle[0]["pagador_nombre"] == "VALERIA CASTRILLON SAL"
    assert detalle[0]["coincide_nombre"] is True
    assert detalle[1]["coincide_nombre"] is False


def test_modo_pago_sin_movimientos_es_sin_coincidencia(tmp_path: Path) -> None:
    """Ningún pago con ese importe: `sin_coincidencia`, sin candidato."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = _job_de_pago(jobs, valor=Decimal("999.00"))
    scraper = _ScraperFalso(_resultado(_movimiento(VALOR, id_externo="a")))
    worker = _worker(tmp_path, jobs=jobs, store=store, scraper_factory=lambda _pedir: scraper)

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.SIN_COINCIDENCIA
    assert (guardado.resultado or {})["candidato"] is None


def test_el_nit_comodin_no_se_muestra_en_el_candidato(tmp_path: Path) -> None:
    """222222222 es consumidor final: el chulo no debe mostrar ese NIT."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = jobs.create_job("masvital", FACTURA, VALOR)
    scraper = _ScraperFalso(_resultado(_movimiento(VALOR, id_externo="a")))
    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
        facturas=lambda _fid: {"nitter": "222222222", "cliente_nombre": "CONSUMIDOR FINAL"},
    )

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    candidato = (guardado.resultado or {})["candidato"]
    assert "nitter" not in candidato
    assert candidato["cliente_nombre"] == "CONSUMIDOR FINAL"


def test_el_nit_real_si_se_muestra(tmp_path: Path) -> None:
    """Un NIT que identifica al cliente viaja al resultado (modo factura)."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    job = jobs.create_job("masvital", FACTURA, VALOR)
    scraper = _ScraperFalso(_resultado(_movimiento(VALOR, id_externo="a")))
    worker = _worker(
        tmp_path,
        jobs=jobs,
        store=store,
        scraper_factory=lambda _pedir: scraper,
        facturas=lambda _fid: {"nitter": "901234567", "cliente_nombre": "VALERIA CASTRILLON"},
    )

    worker.run_once(job)

    guardado = jobs.get_job("masvital", job.job_id)
    assert guardado is not None
    assert (guardado.resultado or {})["candidato"]["nitter"] == "901234567"


# ── Ventana por job: verificar el pago de ayer ────────────────────────────


class _ScraperQueRegistra:
    """Scraper que anota la configuración recibida y devuelve su ventana.

    Reproduce lo que hace el scraper real: la ventana del `ScrapeResult` es la
    de la configuración con la que se raspó, no otra.
    """

    def __init__(self, movimiento: ScrapedMovement) -> None:
        self.configs: list[NodeConfig] = []
        self._movimiento = movimiento

    def scrape(self, config: NodeConfig, on_progress=None) -> ScrapeResult:
        self.configs.append(config)
        return ScrapeResult(
            tenant=config.tenant,
            cuenta=ETIQUETA_TENANT,
            ventana=(config.window_start, config.window_end),
            paginas=1,
            movimientos=(self._movimiento,),
            leido_en=datetime.datetime(2026, 10, 22, 9, 0, 0),
        )


def test_worker_usa_la_ventana_del_dia_pedido_y_no_la_del_nodo(tmp_path: Path) -> None:
    """Un job con `fecha` raspa ESE día completo; los demás siguen en el nodo."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    dia = datetime.date(2026, 10, 20)
    scraper = _ScraperQueRegistra(
        ScrapedMovement(
            id_externo="mov-ayer",
            fecha=dia,
            descripcion="PAGO QR TEST",
            referencia="0092055984",
            referencia_utilizable=True,
            pagador_nombre="TEST",
            valor=VALOR,
            direccion=MovementDirection.INGRESO,
            es_candidato_pago=True,
            pagina=1,
            cuenta_origen=ETIQUETA_TENANT,
        )
    )
    job = jobs.create_job(
        config.tenant,
        "",
        VALOR,
        solicitud={"modo": "pago", "fecha": dia.isoformat()},
        fecha=dia,
    )
    worker = BankVerificationWorker(
        jobs=jobs,
        config=config,
        store=store,
        scraper_factory=lambda _cfg: scraper,
        vault=_VaultFalso(),
        facturas=lambda _fid: None,
        nodo="pc-masvital",
    )

    worker.run_once(job)

    assert len(scraper.configs) == 1
    enviada = scraper.configs[0]
    assert enviada.window_start.date() == dia
    assert enviada.window_start.time() == datetime.time(0, 0, 0)
    assert enviada.window_end.date() == dia
    assert enviada.window_end.time() == datetime.time(23, 59, 59)
    # La config del proceso no se tocó: los otros jobs siguen en su ventana.
    assert worker._config is config
    assert config.window_start.year == 2026 and config.window_start.month == 1

    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado == EstadoJob.RESUELTO
    assert guardado.resultado is not None
    assert guardado.resultado["ventana"] == {
        "desde": "2026-10-20T00:00:00",
        "hasta": "2026-10-20T23:59:59",
    }


def test_worker_sin_fecha_usa_la_ventana_del_nodo(tmp_path: Path) -> None:
    """Sin `fecha` en la solicitud se raspa la ventana configurada (histórico)."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    scraper = _ScraperQueRegistra(_movimiento(VALOR, id_externo="mov-hoy"))
    job = jobs.create_job(config.tenant, "", VALOR, solicitud={"modo": "pago"})
    worker = BankVerificationWorker(
        jobs=jobs,
        config=config,
        store=store,
        scraper_factory=lambda _cfg: scraper,
        vault=_VaultFalso(),
        facturas=lambda _fid: None,
        nodo="pc-masvital",
    )

    worker.run_once(job)

    assert len(scraper.configs) == 1
    assert scraper.configs[0].window_start == config.window_start
    assert scraper.configs[0].window_end == config.window_end


def test_worker_fecha_ilegible_cae_a_la_ventana_del_nodo(tmp_path: Path) -> None:
    """Una solicitud corrupta no tumba el job: se usa la ventana del nodo."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    scraper = _ScraperQueRegistra(_movimiento(VALOR, id_externo="mov-x"))
    job = jobs.create_job(
        config.tenant, "", VALOR, solicitud={"modo": "pago", "fecha": "no-es-fecha"}
    )
    worker = BankVerificationWorker(
        jobs=jobs,
        config=config,
        store=store,
        scraper_factory=lambda _cfg: scraper,
        vault=_VaultFalso(),
        facturas=lambda _fid: None,
        nodo="pc-masvital",
    )

    worker.run_once(job)

    assert scraper.configs[0].window_start == config.window_start
    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.estado in {EstadoJob.RESUELTO, EstadoJob.AMBIGUO, EstadoJob.SIN_COINCIDENCIA}

# ── Progreso por etapas (lo que ve el operador mientras espera) ───────────


class _ScraperConProgreso:
    """Scraper que reporta una etapa y, en el medio, mira lo que quedó escrito."""

    def __init__(self, jobs: FakeVerificationJobStore, job_id: str) -> None:
        self._jobs = jobs
        self._job_id = job_id
        self.visto: dict | None = None

    def scrape(self, config: NodeConfig, on_progress=None) -> ScrapeResult:
        assert on_progress is not None, "el worker tiene que pasar el callback"
        on_progress("cuenta_abierta", 55)
        actual = self._jobs.get_job(config.tenant, self._job_id)
        self.visto = (actual.resultado or {}) if actual else None
        return _resultado(_movimiento(VALOR, id_externo="mov-progreso"))


def test_worker_escribe_la_etapa_en_el_job_mientras_raspa(tmp_path: Path) -> None:
    """El front sondea el job: la etapa tiene que estar en `resultado.progreso`."""
    jobs = FakeVerificationJobStore()
    store = FakeBankStore()
    config = _config(tmp_path)
    job = jobs.create_job(config.tenant, "", VALOR, solicitud={"modo": "pago"})
    scraper = _ScraperConProgreso(jobs, job.job_id)
    worker = BankVerificationWorker(
        jobs=jobs,
        config=config,
        store=store,
        scraper_factory=lambda _cfg: scraper,
        vault=_VaultFalso(),
        facturas=lambda _fid: None,
        nodo="pc-masvital",
    )

    worker.run_once(job)

    assert scraper.visto == {"progreso": {"paso": "cuenta_abierta", "pct": 55}}
    guardado = jobs.get_job(config.tenant, job.job_id)
    assert guardado is not None
    assert guardado.resultado is not None
    # El resultado final deja el progreso cerrado en 100.
    assert guardado.resultado["progreso"] == {"paso": "listo", "pct": 100}
