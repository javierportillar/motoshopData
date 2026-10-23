"""Cuenta los pares QR que el banco manda duplicados, por dia.

El banco publica cada PAGO QR dos veces: con el nombre completo del pagador y
con el nombre corto (`PAGO QR VALERIA CASTR` junto a `PAGO QR VALERIA
CASTRILLON SAL`). El scraper descarta el corto y deja una linea `qr_duplicado`
en `logs/api_uvicorn.log`. Este script la lee y resume.

Por que un script y no una consulta: el par descartado NUNCA llega a la base
(se colapsa antes de la ingesta), asi que la unica huella auditable es el log.
No toca MySQL, no toca el portal, no escribe nada.

Uso:
    uv run --project motoshop-app\\api python infra\\check_qr_duplicates.py
    ... --log <ruta> --desde 2026-10-01 --hasta 2026-10-31 --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_POR_DEFECTO = REPO / "logs" / "api_uvicorn.log"

#: Linea emitida por `BankScraper._colapsar_duplicados` (formato estable).
_LINEA = re.compile(
    r"qr_duplicado dia=(?P<dia>\d{4}-\d{2}-\d{2}) valor=(?P<valor>[-\d.]+) "
    r"referencia=(?P<ref>\S*) descartada=(?P<descartada>.*) conservada=(?P<conservada>.*)$"
)


def _sin_comillas(texto: str) -> str:
    return texto.strip().strip("'").strip('"')


def leer_pares(ruta: Path) -> list[dict[str, str]]:
    """Pares `qr_duplicado` del log, en orden de aparicion."""
    pares: list[dict[str, str]] = []
    if not ruta.exists():
        return pares
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        coincidencia = _LINEA.search(linea)
        if not coincidencia:
            continue
        pares.append(
            {
                "dia": coincidencia.group("dia"),
                "valor": coincidencia.group("valor"),
                "referencia": coincidencia.group("ref"),
                "descartada": _sin_comillas(coincidencia.group("descartada")),
                "conservada": _sin_comillas(coincidencia.group("conservada")),
            }
        )
    return pares


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=LOG_POR_DEFECTO)
    parser.add_argument("--desde", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--hasta", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--json", action="store_true", help="Salida para maquina")
    args = parser.parse_args(argv)

    pares = leer_pares(args.log)
    if args.desde:
        pares = [p for p in pares if dt.date.fromisoformat(p["dia"]) >= args.desde]
    if args.hasta:
        pares = [p for p in pares if dt.date.fromisoformat(p["dia"]) <= args.hasta]

    # Un mismo par puede repetirse en cada scrape del dia: se cuenta una vez
    # por (dia, valor, referencia, descartada).
    unicos: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for par in pares:
        unicos.setdefault(
            (par["dia"], par["valor"], par["referencia"], par["descartada"]), par
        )
    por_dia: dict[str, list[dict[str, str]]] = defaultdict(list)
    for par in unicos.values():
        por_dia[par["dia"]].append(par)

    if args.json:
        print(
            json.dumps(
                {
                    "log": str(args.log),
                    "pares_por_dia": {
                        dia: {"pares": len(items), "detalle": items}
                        for dia, items in sorted(por_dia.items())
                    },
                    "total_pares": len(unicos),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not unicos:
        print(f"sin pares qr_duplicado en {args.log}")
        return 0
    for dia in sorted(por_dia):
        items = por_dia[dia]
        print(f"{dia}: {len(items)} par(es)")
        for par in sorted(items, key=lambda p: p["valor"]):
            print(
                "  {valor:>14}  ref={ref:<12} descartada={desc!r} conservada={cons!r}".format(
                    valor=par["valor"],
                    ref=par["referencia"],
                    desc=par["descartada"],
                    cons=par["conservada"],
                )
            )
    print(f"TOTAL pares={len(unicos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
