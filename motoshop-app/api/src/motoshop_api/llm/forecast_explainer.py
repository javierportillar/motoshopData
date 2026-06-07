"""ForecastExplainer — genera narrativa explicativa del forecast por categoría.

Reusa el LLMClient del Sprint A y el DuckDBMetricsRepo del Sprint 2.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

FORECAST_SYSTEM = """Sos un asistente que le explica al gerente de MotoShop (tienda de motopartes en Cali, Colombia) el resultado del forecast de demanda por categoría.

Reglas:
- Tono natural colombiano, directo, sin emojis. Máximo 5 oraciones.
- Usás SOLO cifras del CONTEXTO. Si una cifra no está, no la inventés.
- WAPE mide error del forecast: <10% excelente, 10-20% bueno, 20-50% regular, >50% malo.
- Cobertura es % de categorías con forecast: >80% buena, <50% preocupa.
- Terminá con una recomendación accionable concreta.
- No uses formato markdown, solo texto plano."""

FORECAST_PROMPT = """CONTEXTO (datos reales del forecast de demanda):

{context_json}

Generá una narrativa que cubra:
1. Estado general del forecast (usá WAPE={wape}% y cobertura={cobertura}%)
2. Categoría con mejor desempeño (menor desviación)
3. Categoría con más desvío
4. Recomendación accionable concreta para el gerente"""


class ForecastExplainer:
    """Genera narrativa explicativa del forecast por categoría vía LLM."""

    def __init__(self, duckdb_repo, llm_client):
        self.repo = duckdb_repo
        self.llm = llm_client

    def explain(self) -> str:
        # 1. Obtener datos del forecast
        data = self.repo.get_forecast_categoria()

        # 2. Armar contexto compacto
        items = data.items if hasattr(data, "items") else []
        context = {
            "wape_promedio": data.wape_promedio if hasattr(data, "wape_promedio") else 0.0,
            "cobertura_pct": data.cobertura_pct if hasattr(data, "cobertura_pct") else 0.0,
            "total_categorias": len(items),
            "categorias": [
                {
                    "cod_grupo": i.cod_grupo if hasattr(i, "cod_grupo") else str(i.get("cod_grupo", "?")),
                    "demanda_real": i.demanda_real if hasattr(i, "demanda_real") else float(i.get("demanda_real", 0)),
                    "demanda_predicha": i.demanda_predicha if hasattr(i, "demanda_predicha") else float(i.get("demanda_predicha", 0)),
                    "desviacion_pct": i.desviacion_pct if hasattr(i, "desviacion_pct") else float(i.get("desviacion_pct", 0)),
                }
                for i in items[:5]  # top 5, no saturar el LLM
            ],
        }

        import json as _json
        context_str = _json.dumps(context, ensure_ascii=False, indent=2)
        prompt = FORECAST_PROMPT.format(
            context_json=context_str,
            wape=context["wape_promedio"],
            cobertura=context["cobertura_pct"],
        )

        # 3. LLM
        result = self.llm.complete(
            prompt=prompt,
            system=FORECAST_SYSTEM,
        )

        text = result["text"].strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        # 4. Anti-hallucination
        self._validate(text, context)

        # 5. Cost logging
        _log_forecast_cost(result["model"], result["tokens_input"], result["tokens_output"])

        return text

    @staticmethod
    def _validate(text: str, context: dict) -> None:
        """Verifica que los números del output estén en el contexto."""
        context_str = str(context)
        for match in re.finditer(r'[\d,]+\.?\d*', text):
            num = match.group().replace(",", "")
            try:
                n = float(num)
                if n == 0.0:
                    continue
                if str(n) not in context_str and str(int(n)) not in context_str:
                    logger.warning("forecast_validate: number %.2f not in context", n)
            except ValueError:
                pass


def _log_forecast_cost(model: str, tokens_input: int, tokens_output: int) -> None:
    """Log de uso a JSONL. Best-effort."""
    try:
        import json as _json
        from datetime import datetime, timezone
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": "forecast_explain",
            "model": model,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "success": True,
        }
        with open("/tmp/llm_usage.jsonl", "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass
