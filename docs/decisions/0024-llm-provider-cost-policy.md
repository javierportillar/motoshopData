# ADR-0024 · LLM provider + cost policy (OpenCode Go + Zen)

- **Fecha:** 2026-06-07
- **Status:** Accepted
- **Deciders:** PO (provee OpenCode Go key) + Dev L (implementa dual-API)
- **Referencia:** [docs/plan-v1.6-llm.md](../plan-v1.6-llm.md)

---

## 1 · Contexto

V1.6 Sprint A requiere un LLM para generar el briefing diario del gerente. El PO ya tiene una suscripción a OpenCode Go que incluye modelos como `deepseek-v4-pro`, `kimi-k2.6`, `qwen3.6-plus`, etc. Además, OpenCode Zen ofrece `deepseek-v4-flash-free` como modelo gratuito sin suscripción.

**Necesidad**: elegir un provider primario y uno de fallback que garanticen:
- Disponibilidad 24/7 para el cron de las 06:00 COL
- Costo $0 marginal para MotoShop
- Calidad de respuesta en español colombiano
- Latencia aceptable (< 30s para el briefing completo)

---

## 2 · Decisión

✅ **Provider primario: OpenCode Go** (`https://opencode.ai/zen/go/v1`) con modelo `deepseek-v4-pro`.

✅ **Provider fallback: OpenCode Zen** (`https://opencode.ai/zen/v1`) con modelo `deepseek-v4-flash-free`.

### Arquitectura dual-API

```
┌────────────────────────────────────┐
│ LLMClient (httpx)                  │
│                                    │
│  1. deepseek-v4-pro @ GO           │
│     └─ key: OPENCODE_API_KEY (GO)  │
│     └─ max_tokens: 8000            │
│     └─ cost: $0 (incluido en plan) │
│                                    │
│  2. deepseek-v4-flash-free @ Zen   │
│     └─ key: OPENCODE_API_KEY_FALLBACK│
│     └─ max_tokens: 8000            │
│     └─ cost: $0 (free forever)     │
└────────────────────────────────────┘
```

### Por qué deepseek-v4-pro como primario

| Criterio | deepseek-v4-pro (GO) | Alternativas rechazadas |
|----------|---------------------|-------------------------|
| Costo | $0 marginal (plan del PO) | - |
| Español | Excelente, tono natural | qwen3.6-plus también bueno pero PO prefiere deepseek |
| Latencia | ~15s para briefing (481 tokens) | kimi-k2.6 ~30s (más lento) |
| Chain-of-thought | Sí, pero con max_tokens=8000 termina y produce content | - |
| Disponibilidad | 24/7 vía OpenCode Go | - |

### Por qué deepseek-v4-flash-free como fallback

- Mismo proveedor (OpenCode), distinto endpoint (Zen)
- Key separada (redundancia de credenciales)
- Free forever, sin depender del plan del PO
- Si GO está caído, Zen sigue respondiendo

---

## 3 · Consecuencias

### Positivas

| Métrica | Valor |
|---------|-------|
| Costo marginal | **$0/mes** (incluido en plan OpenCode Go del PO) |
| Latencia briefing | ~15s (481 tokens, deepseek-v4-pro) |
| Redundancia | Dual API + dual key → sin single point of failure |
| Cost audit | `app_llm_usage` en MySQL (tokens, modelo, endpoint) |
| Rollback | Cambiar env vars GO_MODEL → otro modelo en < 1 min |

### Negativas

- **Chain-of-thought overhead**: deepseek-v4-pro consume ~400 tokens en reasoning antes del content. Requiere `max_tokens >= 8000` para que el content quede poblado. Con 2000, content queda vacío.
- **Dependencia del plan del PO**: si el PO cancela OpenCode Go, el primario deja de funcionar. Mitigado por el fallback a Zen (free forever).
- **Sin streaming**: el cron no necesita streaming, pero si en Sprint C (Q&A) queremos streaming, habría que adaptar el cliente.

### Plan B (degradación de GO)

Si OpenCode Go degrada el servicio o el PO cancela:
1. Cambiar `GO_MODEL=""` en Render env vars
2. El LLMClient automáticamente usa Zen como único backend
3. Tiempo de recuperación: < 1 min (sin deploy, solo cambio de env var + reinicio)

### Plan C (degradación de Zen)

Si Zen también degrada:
1. El PO puede configurar un API key de Anthropic/OpenAI en `OPENCODE_API_KEY_FALLBACK`
2. Agregar un tercer backend en `LLMClient` apuntando a `https://api.anthropic.com/v1`
3. Tiempo de implementación: ~30 min (el LLMClient ya soporta múltiples backends)

---

## 4 · Cost audit

Aunque el costo marginal es $0, toda llamada se registra en `app_llm_usage` (MySQL) con:
- `endpoint`: `briefing_generate` / `briefing_send` / `forecast_explain`
- `model`: nombre del modelo usado
- `tokens_input`, `tokens_output`: conteo real
- `cost_usd`: siempre 0.0
- `success`: 1 si el call fue exitoso

Dashboard en `GET /api/admin/llm-cost` (admin-only).

---

## 5 · Referencias

- [docs/plan-v1.6-llm.md](../plan-v1.6-llm.md) — plan completo V1.6
- [motoshop-app/api/src/motoshop_api/llm/client.py](../../motoshop-app/api/src/motoshop_api/llm/client.py) — implementación
- [infra/migrations/app_llm_usage_v16.sql](../../infra/migrations/app_llm_usage_v16.sql) — schema cost audit
