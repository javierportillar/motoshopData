"""Test anti-hallucination: el briefing del LLM nunca debe inventar cifras.

Estrategia:
1. Mock build_context() con cifras conocidas
2. Generar briefing con BriefingGenerator.generate()
3. Extraer todos los números del output
4. Verificar que cada número aparezca en el contexto original
5. Si algún número no aparece → FAIL con evidencia

NOTA: Este test requiere OPENCODE_API_KEY para llamar al LLM real.
Si no está configurado, se skipea con pytest.skip.
"""

from __future__ import annotations

import os
import re
from datetime import date

import pytest


def _extract_numbers(text: str) -> set[float]:
    """Extrae todos los números (enteros, decimales, con formato COP) del texto."""
    numbers = set()
    # Números con formato: 1,234.56 o 1234.56 o 42
    for match in re.finditer(r'[\d,]+\.?\d*', text):
        num = match.group().replace(",", "")
        try:
            numbers.add(float(num))
        except ValueError:
            pass
    return numbers


def _flatten_numbers(obj, max_depth: int = 5) -> set[float]:
    """Extrae recursivamente todos los números de un dict/list anidado."""
    numbers = set()
    if max_depth <= 0:
        return numbers
    if isinstance(obj, dict):
        for v in obj.values():
            numbers.update(_flatten_numbers(v, max_depth - 1))
    elif isinstance(obj, list):
        for v in obj:
            numbers.update(_flatten_numbers(v, max_depth - 1))
    elif isinstance(obj, (int, float)):
        numbers.add(float(obj))
    elif isinstance(obj, str):
        numbers.update(_extract_numbers(obj))
    return numbers


@pytest.mark.skipif(
    not os.environ.get("OPENCODE_API_KEY"),
    reason="OPENCODE_API_KEY no configurado — test requiere LLM real",
)
class TestBriefingNoHallucination:
    """Verifica que el LLM no invente cifras en el briefing."""

    CONTEXT = {
        "fecha": "2026-06-06",
        "ventas_ayer": 23516508.33,
        "facturas_ayer": 911,
        "ticket_promedio_ayer": 25813.95,
        "ventas_anteayer": 26365000.0,
        "ventas_vs_anteayer_pct": -10.8,
        "ventas_vs_semana_pasada_pct": 5.3,
        "top_skus": [
            {"sku": "601325", "nombre": "MOBIL SUPER MOTO 4T 20W50", "valor": 1160000.0},
            {"sku": "MOTS1297", "nombre": "ACEITE CASTROS 20W50", "valor": 864000.0},
        ],
        "alertas_criticas": [
            {"sku": "02_00002", "nombre": "BATERIA MOTO AGM 12V 5AH", "stock": 0.0, "demanda": 1.0, "dias": 0},
        ],
        "dormidos_recuperados": [],
        "vendedor_top": {"nombre": "KAROL NATALIA BURGOS BUSTOS", "facturas": 151, "total": 23516508.33},
    }

    def _get_context_numbers(self) -> set[float]:
        return _flatten_numbers(self.CONTEXT)

    def test_single_generation_no_hallucination(self):
        """Una generación: ningún número inventado."""
        from motoshop_api.llm.briefing import BriefingGenerator
        from motoshop_api.llm.client import get_llm_client

        gen = BriefingGenerator(duckdb_path="out/motoshop_gold.duckdb")
        result = gen.generate(self.CONTEXT)
        text = result["briefing_text"]

        context_nums = self._get_context_numbers()
        output_nums = _extract_numbers(text)

        invented = output_nums - context_nums
        # Permitir 0.0 (ej: "0 alertas") si aparece
        invented.discard(0.0)

        assert not invented, (
            f"Números INVENTADOS detectados en el briefing:\n"
            f"  Inventados: {sorted(invented)}\n"
            f"  En contexto: {sorted(context_nums)[:15]}...\n"
            f"  Briefing:\n{text[:500]}"
        )

    def test_repeated_generation_no_hallucination(self):
        """10 generaciones: ninguna debe inventar números."""
        from motoshop_api.llm.briefing import BriefingGenerator

        gen = BriefingGenerator(duckdb_path="out/motoshop_gold.duckdb")
        context_nums = self._get_context_numbers()

        failures = []
        for i in range(10):
            result = gen.generate(self.CONTEXT)
            text = result["briefing_text"]
            output_nums = _extract_numbers(text)
            invented = output_nums - context_nums
            invented.discard(0.0)

            if invented:
                failures.append((i, invented, text[:300]))

        assert not failures, (
            f"Hallucinations en {len(failures)}/10 generaciones:\n" +
            "\n".join(
                f"  Gen #{i}: invented={sorted(nums)}" for i, nums, _ in failures
            )
        )

    def test_briefing_has_required_elements(self):
        """El briefing debe contener elementos clave del contexto."""
        from motoshop_api.llm.briefing import BriefingGenerator

        gen = BriefingGenerator(duckdb_path="out/motoshop_gold.duckdb")
        result = gen.generate(self.CONTEXT)
        text = result["briefing_text"].lower()

        # Debe empezar con saludo
        assert "buen día" in text or "buenos días" in text, f"No tiene saludo: {text[:100]}"

        # Debe mencionar ventas o facturas
        assert "venta" in text or "factura" in text or "pesos" in text, f"No menciona ventas: {text[:100]}"

        # Debe tener al menos un número del contexto
        assert "23516508" in text or "911" in text or "1160000" in text, f"No tiene cifras: {text[:100]}"
