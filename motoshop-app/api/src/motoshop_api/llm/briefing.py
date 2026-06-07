"""BriefingGenerator — genera briefing diario narrativo desde DuckDB.

Flujo:
1. build_context() → consulta DuckDB y arma dict < 4K tokens
2. generate() → envía contexto al LLM, parsea respuesta, valida contra alucinaciones
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ── Prompt template ────────────────────────────────────────────────────────

BRIEFING_SYSTEM = """Sos un asistente que le hace al gerente de MotoShop (tienda de motopartes en Cali, Colombia) un briefing diario corto y útil.

Reglas:
- Tono colombiano natural, directo, sin emojis cursis ni saludos protocolares largos
- Máximo 8 oraciones
- Usás SOLO las cifras del CONTEXTO. Si una cifra no está, no la inventés — directamente no la menciones
- Empezá con "Buen día, gerente."
- Los valores monetarios se expresan en pesos colombianos (COP)
- Si hay alertas críticas, mencioná las más importantes
- Si no hay datos para un rubro (ej: no hay dormidos recuperados), simplemente no lo mencionés
- No uses formato markdown, solo texto plano"""

BRIEFING_PROMPT = """CONTEXTO (datos reales del día de hoy y comparativas):

{context_json}

Generá el briefing en español colombiano."""


class BriefingGenerator:
    """Genera briefing diario para el gerente vía LLM."""

    def __init__(self, duckdb_path: str = "out/motoshop_gold.duckdb"):
        import duckdb
        self._con = duckdb.connect(duckdb_path, read_only=True)

    def build_context(self) -> dict:
        """Consulta DuckDB y arma un dict compacto con los KPIs del día anterior.

        Usa MAX(business_date) en vez de date.today() porque el DuckDB es un snapshot
        estático (no real-time). En producción con pipeline diario, la diferencia es 0.
        """
        max_date_row = self._con.execute("""
            SELECT MAX(business_date) FROM motoshop_gold_mart_ventas_diarias_sku
        """).fetchone()
        max_date = max_date_row[0] if max_date_row and max_date_row[0] else date.today()

        ayer = max_date
        anteayer = max_date - timedelta(days=1)
        semana_pasada = max_date - timedelta(days=7)

        ctx = {}

        # ── Ventas ────────────────────────────────────────────────────────
        ventas = self._con.execute("""
            SELECT
                ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS ventas,
                COALESCE(SUM(num_facturas), 0) AS facturas,
                ROUND(COALESCE(SUM(valor_total), 0.0) / NULLIF(COALESCE(SUM(num_facturas), 0), 0), 2) AS ticket_promedio
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
        """, [ayer.isoformat()]).fetchone()

        ctx["ventas_ayer"] = float(ventas[0]) if ventas[0] else 0.0
        ctx["facturas_ayer"] = int(ventas[1]) if ventas[1] else 0
        ctx["ticket_promedio_ayer"] = float(ventas[2]) if ventas[2] else 0.0
        ctx["fecha"] = ayer.isoformat()

        # Comparación vs anteayer
        prev = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS ventas,
                   COALESCE(SUM(num_facturas), 0) AS facturas
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
        """, [anteayer.isoformat()]).fetchone()

        if prev and prev[0]:
            va_ant = float(prev[0])
            if va_ant > 0:
                delta = round((ctx["ventas_ayer"] - va_ant) / va_ant * 100, 1)
                ctx["ventas_vs_anteayer_pct"] = delta
                ctx["ventas_anteayer"] = va_ant

        # Comparación vs mismo día semana pasada
        prev_w = self._con.execute("""
            SELECT ROUND(COALESCE(SUM(valor_total), 0.0), 2) AS ventas
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
        """, [semana_pasada.isoformat()]).fetchone()

        if prev_w and prev_w[0]:
            va_w = float(prev_w[0])
            if va_w > 0:
                delta_w = round((ctx["ventas_ayer"] - va_w) / va_w * 100, 1)
                ctx["ventas_vs_semana_pasada_pct"] = delta_w

        # ── Top SKUs vendidos ──────────────────────────────────────────────
        top = self._con.execute("""
            SELECT cod_producto, nom_producto, ROUND(SUM(valor_total), 2) AS valor
            FROM motoshop_gold_mart_ventas_diarias_sku
            WHERE business_date = ?
            GROUP BY cod_producto, nom_producto
            ORDER BY valor DESC
            LIMIT 5
        """, [ayer.isoformat()]).fetchall()
        ctx["top_skus"] = [{"sku": r[0], "nombre": r[1], "valor": float(r[2])} for r in top if r[2]]

        # ── Alertas de quiebre críticas ────────────────────────────────────
        alerts = self._con.execute("""
            SELECT sku, nom_producto, stock_actual, demanda_predicha, dias_hasta_quiebre
            FROM motoshop_gold_alertas_quiebre
            WHERE urgencia = 'alta'
            ORDER BY dias_hasta_quiebre ASC
            LIMIT 5
        """).fetchall()
        ctx["alertas_criticas"] = [
            {"sku": r[0], "nombre": r[1], "stock": float(r[2]), "demanda": float(r[3]), "dias": int(r[4])}
            for r in alerts
        ]

        # ── Dormidos recuperados ───────────────────────────────────────────
        dormidos = self._con.execute("""
            SELECT d.cod_producto, d.nom_producto, d.dias_sin_venta, ROUND(SUM(v.valor_total), 2) AS ventas
            FROM motoshop_gold_mart_productos_dormidos d
            INNER JOIN motoshop_gold_mart_ventas_diarias_sku v
                ON d.cod_producto = v.cod_producto AND v.business_date = ?
            GROUP BY d.cod_producto, d.nom_producto, d.dias_sin_venta
            ORDER BY ventas DESC
            LIMIT 3
        """, [ayer.isoformat()]).fetchall()
        ctx["dormidos_recuperados"] = [
            {"sku": r[0], "nombre": r[1], "dias_dormido": int(r[2]), "ventas_hoy": float(r[3])}
            for r in dormidos if r[3]
        ]

        # ── Vendedor top ───────────────────────────────────────────────────
        top_v = self._con.execute("""
            SELECT COALESCE(NULLIF(nit_vendedor,''),'Sin asignar') AS nit,
                   COALESCE(NULLIF(nombre_vendedor,''),'Sin asignar') AS nombre,
                   COUNT(*) AS facturas, ROUND(SUM(total_factura), 2) AS total
            FROM motoshop_silver_fact_ventas
            WHERE business_date = ?
            GROUP BY nit_vendedor, nombre_vendedor
            ORDER BY total DESC
            LIMIT 1
        """, [ayer.isoformat()]).fetchone()
        if top_v:
            ctx["vendedor_top"] = {"nombre": top_v[1], "facturas": int(top_v[2]), "total": float(top_v[3])}

        logger.info("build_context: ventas_ayer=%.2f facturas=%d", ctx["ventas_ayer"], ctx["facturas_ayer"])
        return ctx

    def generate(self, context: dict) -> dict:
        """Llama al LLM con el contexto y devuelve {briefing_text, tokens_used, model, cost_usd}."""
        from motoshop_api.llm.client import get_llm_client

        import json as _json
        context_str = _json.dumps(context, ensure_ascii=False, indent=2)
        prompt = BRIEFING_PROMPT.format(context_json=context_str)

        # deepseek-v4-flash-free consume ~400 tokens en reasoning_content,
        # necesita max_tokens alto para que content tenga espacio (único free funcional)
        client = get_llm_client()
        result = client.complete(
            prompt=prompt,
            max_tokens=2000,
            system=BRIEFING_SYSTEM,
        )

        text = result["text"].strip()
        # Limpiar posibles artifacts del LLM
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        # ── Anti-hallucination: verificar que cada número del output esté en el contexto ──
        self._validate_numbers(text, context)

        return {
            "briefing_text": text,
            "tokens_used": result["tokens_used"],
            "tokens_input": result["tokens_input"],
            "tokens_output": result["tokens_output"],
            "model": result["model"],
            "cost_usd": result["cost_usd"],
        }

    @staticmethod
    def _validate_numbers(text: str, context: dict) -> None:
        """Verifica que los números en el texto del LLM aparezcan en el contexto."""
        context_str = str(context)
        # Extraer todos los números (enteros y decimales) del texto
        numbers_in_text = set()
        for match in re.finditer(r'[\d,]+\.?\d*', text):
            num = match.group().replace(",", "")
            try:
                numbers_in_text.add(float(num))
            except ValueError:
                pass

        # Extraer todos los números del contexto
        numbers_in_context = set()
        for match in re.finditer(r'[\d,]+\.?\d*', context_str):
            num = match.group().replace(",", "")
            try:
                numbers_in_context.add(float(num))
            except ValueError:
                pass

        # Verificar que cada número del texto aparezca en el contexto (±0.01 para floats)
        for num in numbers_in_text:
            if num == 0.0:  # Permitir "0" (ej: "0 alertas")
                continue
            found = False
            for ctx_num in numbers_in_context:
                if abs(num - ctx_num) < 0.02:
                    found = True
                    break
            if not found:
                logger.warning(
                    "anti_hallucination: number %.2f found in briefing but NOT in context", num
                )

    def close(self):
        self._con.close()
