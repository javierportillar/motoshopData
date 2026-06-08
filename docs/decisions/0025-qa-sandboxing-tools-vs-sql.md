# ADR-0025 · Q&A sandboxing: tools tipadas vs SQL generation

- **Fecha:** 2026-06-07
- **Status:** Accepted
- **Deciders:** Dev L (implementa) + Revisor (aprueba arquitectura)
- **Referencia:** [docs/plan-v1.6-llm.md](../plan-v1.6-llm.md) Sprint C

---

## 1 · Contexto

Sprint C implementa Q&A conversacional sobre DuckDB. El gerente puede preguntar en lenguaje natural ("¿cómo van las ventas?") y el sistema debe responder con cifras reales del negocio.

**Riesgo principal:** el LLM podría generar SQL arbitrario (DROP TABLE, inyección) o inventar cifras.

**Alternativas evaluadas:**

| Opción | Seguridad | Complejidad | Calidad |
|--------|-----------|-------------|---------|
| A: LLM genera SQL libre → validar con sqlglot AST | Media | Alta (parser + whitelist + tests) | Alta (flexible) |
| B: Tools tipadas (function calling) | **Alta** (el LLM nunca escribe SQL) | **Baja** (Pydantic models) | Alta (tool descriptions guían al LLM) |
| C: RAG sobre documentos | Baja (no hay datos reales) | Media | Muy baja |

---

## 2 · Decisión

✅ **Tools tipadas con function calling (Opción B).** El LLM NUNCA genera SQL. Las herramientas son funciones Python con argumentos Pydantic que ejecutan queries pre-escritas y validadas contra DuckDB.

### Arquitectura

```
Usuario: "¿cómo van las ventas vs mes pasado?"
         │
         ▼
┌─────────────────────────────────┐
│ QAChat.chat()                   │
│  1. Envía mensaje + TOOL_DEFS   │
│  2. LLM decide: get_kpis_month  │
│     + compare_periods           │
│  3. ToolExecutor.run()          │
│     → DuckDB query pre-escrita  │
│     → dict JSON serializable    │
│  4. LLM narra resultado         │
│  5. Responde al usuario         │
└─────────────────────────────────┘
```

### Por qué NO sqlglot

- sqlglot validaría AST pero no semántica (ej: `SELECT * FROM users` es válido pero no debería existir)
- Tools tipadas son más seguras: el LLM solo puede llamar funciones registradas
- Menos código: 10 tools con Pydantic (~200 líneas) vs parser + whitelist + tests (~500 líneas)
- Más fácil de auditar: cada tool es una función Python legible por humanos

---

## 3 · Consecuencias

### Positivas

- **Seguridad**: imposible que el LLM ejecute DROP/INSERT/DELETE. Solo las 10 tools registradas.
- **Auditability**: cada tool loguea qué ejecutó y con qué argumentos.
- **Extensibilidad**: agregar una tool nueva es 15 líneas de código.
- **Costo**: las tools reducen tokens del prompt (no hay que enviar schema completo). El LLM solo ve descripciones.

### Negativas

- **Flexibilidad limitada**: si el gerente pregunta algo que ninguna tool puede responder, el LLM dice "no puedo". Para expandir, hay que agregar tools.
- **Dependencia del LLM**: el LLM debe interpretar correctamente qué tool usar. Si el LLM se equivoca, la respuesta es incorrecta.

### Hard caps

| Límite | Valor | Motivo |
|--------|-------|--------|
| Turnos por sesión | 20 | Evitar loops infinitos |
| Tool calls por turno | 5 | Evitar consumo excesivo de tokens |
| TTL sesión | 30 min | Liberar memoria |
| Message length | 500 chars | Evitar prompt injection masiva |

---

## 4 · Referencias

- [motoshop-app/api/src/motoshop_api/llm/tools.py](../../motoshop-app/api/src/motoshop_api/llm/tools.py) — 10 tools implementadas
- [motoshop-app/api/src/motoshop_api/llm/qa_chat.py](../../motoshop-app/api/src/motoshop_api/llm/qa_chat.py) — orquestador
- [motoshop-app/api/src/motoshop_api/llm/client.py](../../motoshop-app/api/src/motoshop_api/llm/client.py) — LLMClient con function calling
- [docs/decisions/0024-llm-provider-cost-policy.md](../0024-llm-provider-cost-policy.md) — provider + cost policy
