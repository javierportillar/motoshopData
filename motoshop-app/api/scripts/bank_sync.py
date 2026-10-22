#!/usr/bin/env python3
"""Corrida del nodo: un scrape del portal + la ingesta idempotente (S5).

Uso (desde `motoshop-app/api`):

    uv run python scripts/bank_sync.py
    uv run python scripts/bank_sync.py --tenant masvital

Qué hace, en orden:

1. carga la configuración del nodo (`BANK_*`, igual que el resto del sistema);
2. toma el turno de sesión (lock + intervalo mínimo de 30 s);
3. raspa la cuenta **por etiqueta** (`BANK_ACCOUNT_LABEL`);
4. ingiere los movimientos de la ventana de forma **idempotente**
   (`UNIQUE (tenant, id_externo)`): la segunda corrida no crea filas nuevas.

Si el portal pide un código de un solo uso, se pide **en esta consola** (no
en el navegador) y no se guarda en ningún lado.

`--help` funciona **sin Playwright instalado**: la dependencia es opcional
(`uv sync --extra bank`) y sólo se importa cuando de verdad se abre el
navegador. Si falta, la corrida termina con un error explícito.

Código de salida: 0 si la corrida terminó bien, 1 si falló el portal o el
turno de sesión, 2 si la configuración del nodo es inválida.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from typing import NamedTuple

from motoshop_api.erp.bankreconciliation.node_config import (
    ENV_SCRAPER_ENABLED,
    ENV_TENANT,
    NodeConfig,
    NodeConfigError,
    load_node_config,
)
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn
from motoshop_api.erp.bankreconciliation.scraper import (
    BankScrapeError,
    BankScraper,
    ScrapedMovement,
    ScrapeResult,
    SessionSlotError,
)
from motoshop_api.erp.bankreconciliation.store import BankStore, get_bank_store

#: Límites de las columnas de `app_bank_movements`: el texto que exceda el
#: límite de la base se recorta aquí (la fila no entra si no).
LIMITE_DESCRIPCION = 255
LIMITE_REFERENCIA = 64
LIMITE_PAGADOR = 128
LIMITE_CUENTA = 64


class SyncSummary(NamedTuple):
    """Resumen de una corrida: qué se leyó y qué se escribió.

    Es un `NamedTuple` y no un `dataclass` **a propósito**: este script se
    carga con `importlib` (las pruebas lo hacen así) fuera de `sys.modules`, y
    un `dataclass` con anotaciones diferidas (`from __future__ import
    annotations`) revienta en ese escenario porque `dataclasses` busca el
    módulo en `sys.modules` para resolver los tipos.

    Attributes:
        tenant: tenant del nodo.
        cuenta: etiqueta de la cuenta leída.
        paginas: páginas recorridas en el portal.
        leidos: movimientos dentro de la ventana.
        nuevos: filas **nuevas** que escribió la ingesta (0 si ya estaban).
        candidatos: movimientos que son ingresos (candidatos de pago).
        ventana: `(inicio, fin)` de la ventana consultada.
        leido_en: instante de la corrida.
    """

    tenant: str
    cuenta: str
    paginas: int
    leidos: int
    nuevos: int
    candidatos: int
    ventana: tuple[datetime.datetime, datetime.datetime]
    leido_en: datetime.datetime


def _a_ingesta(movimiento: ScrapedMovement) -> BankMovementIn:
    """Movimiento del portal → fila de entrada de la ingesta.

    `referencia_norm` es la referencia ya saneada (sin el sufijo `" null"`):
    la normalización sin ceros a la izquierda es del matching (slices S7/S9).
    """
    return BankMovementIn(
        id_externo=movimiento.id_externo,
        fecha_movimiento=movimiento.fecha,
        valor=movimiento.valor,
        descripcion=movimiento.descripcion[:LIMITE_DESCRIPCION],
        referencia=movimiento.referencia[:LIMITE_REFERENCIA],
        referencia_norm=movimiento.referencia[:LIMITE_REFERENCIA],
        pagador_nombre=movimiento.pagador_nombre[:LIMITE_PAGADOR],
        cuenta_origen=movimiento.cuenta_origen[:LIMITE_CUENTA],
    )


def sincronizar(
    config: NodeConfig,
    *,
    scraper: BankScraper | None = None,
    store: BankStore | None = None,
) -> SyncSummary:
    """Raspa el portal e ingiere los movimientos de forma idempotente.

    El scrape **completa** antes de tocar la base: si el portal falla, la
    ingesta no se hace y no queda ninguna fila parcial.

    Args:
        config: configuración del nodo.
        scraper: scraper a usar (por defecto, el de producción).
        store: store a usar (por defecto, el de producción).

    Returns:
        El resumen de la corrida.

    Raises:
        BankScrapeError: si el portal falla.
        SessionSlotError: si el turno de sesión no se puede tomar.
    """
    activo = scraper if scraper is not None else BankScraper()
    destino = store if store is not None else get_bank_store()

    resultado: ScrapeResult = activo.scrape(config)
    movimientos = [_a_ingesta(movimiento) for movimiento in resultado.movimientos]
    nuevos = destino.upsert_movements(config.tenant, config.tenant, movimientos)

    return SyncSummary(
        tenant=resultado.tenant,
        cuenta=resultado.cuenta,
        paginas=resultado.paginas,
        leidos=len(movimientos),
        nuevos=nuevos,
        candidatos=len(resultado.candidatos),
        ventana=resultado.ventana,
        leido_en=resultado.leido_en,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raspa el portal del banco e ingiere los movimientos del tenant.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--tenant",
        default="",
        help="Tenant que sirve este nodo (por defecto, BANK_TENANT).",
    )
    return parser.parse_args(argv)


def _imprimir(resumen: SyncSummary) -> None:
    """Imprime el resumen de la corrida."""
    inicio, fin = resumen.ventana
    print("Sincronización bancaria")
    print(f"  nodo:    {resumen.tenant}")
    print(f"  cuenta:  {resumen.cuenta}")
    print(f"  ventana: {inicio:%Y-%m-%d %H:%M:%S} → {fin:%Y-%m-%d %H:%M:%S}")
    print(f"  páginas: {resumen.paginas}")
    print(f"  leídos:  {resumen.leidos} ({resumen.candidatos} candidatos de pago)")
    print(f"  nuevos:  {resumen.nuevos}")


def main(argv: list[str] | None = None) -> int:
    """Ejecuta una corrida y devuelve el código de salida."""
    args = _parse_args(argv)

    env = dict(os.environ)
    if args.tenant:
        env[ENV_TENANT] = args.tenant
    # El operador invocó el sincronizador a propósito: si no dijo lo contrario,
    # el nodo está con el scraper habilitado.
    env.setdefault(ENV_SCRAPER_ENABLED, "true")

    try:
        config = load_node_config(env)
    except NodeConfigError as error:
        print(f"[FALLO] configuración inválida: {error}", file=sys.stderr)
        return 2

    if not config.scraper_enabled:
        print(
            "[FALLO] el scraper está deshabilitado en este nodo "
            f"({ENV_SCRAPER_ENABLED}=false): no se raspa.",
            file=sys.stderr,
        )
        return 2

    try:
        resumen = sincronizar(config)
    except SessionSlotError as error:
        print(f"[FALLO] {error.motivo}: {error.mensaje}", file=sys.stderr)
        return 1
    except BankScrapeError as error:
        print(f"[FALLO] {error.codigo}: {error.mensaje}", file=sys.stderr)
        return 1

    _imprimir(resumen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
