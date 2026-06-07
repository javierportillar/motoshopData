# Plan V1.6 · IA aplicada (LLM)

> **Spine de la fase post-V1.5.** Arranca solo cuando V1.5 esté cerrado y firmado por revisor.
>
> **Prerequisite duro:** V1.5 cutover Sprint 4 completo + Sprint 5 sub-bloque B (búsqueda semántica) operativo. Sin eso, no se inicia V1.6.

---

## 1. Por qué existe este plan

V1.5 dejó MotoShop sostenible ("para siempre" gratis con DuckDB). V1.6 le agrega **inteligencia aplicada** al negocio sin agregar infraestructura compleja: usamos LLM API como cliente liviano contra servicios externos que ya tienen 0 ops (OpenAI / Anthropic), pagamos por uso real (centavos al mes).

Tres entregables que aportan valor real al gerente y al vendedor en su operación diaria:

1. **Briefing diario en lenguaje natural** — el gerente lee 30 segundos en el celu y sabe el estado del negocio
2. **Forecast con narrativa explicativa** — convierte "WAPE 34.37%" en una oración accionable
3. **Q&A conversacional sobre el negocio** — el gerente pregunta libre, el sistema traduce a SQL DuckDB y responde

ADRs a generar: **ADR-0024 (LLM provider + cost policy)**, **ADR-0025 (RAG sandboxing para Q&A)**.

---

## 2. Objetivo y restricciones duras

| Dimensión | Objetivo | Restricción |
|-----------|----------|-------------|
| Costo recurrente | **$0/mes para siempre** (regla del proyecto) | OpenCode Zen modelos FREE — sin tarjeta de crédito |
| Latencia briefing | < 10 s end-to-end (cron) | Usuario no espera, llega push, no es interactivo |
| Latencia Q&A | < 5 s por turno | Interactivo, usuario espera |
| Privacidad | No enviar PII de clientes al LLM | nit_cliente queda hasheado o agregado |
| Disponibilidad | Briefing diario sin falla | Fallback a 2do modelo si el primario está caído |
| Honestidad | El LLM nunca inventa cifras | Toda cifra que muestre debe venir de DuckDB tool calls |

---

## 3. Arquitectura objetivo

```
┌──────────────────────────────────────────────────────────────┐
│ ANTHROPIC CLAUDE HAIKU (o OpenAI gpt-4o-mini)                │
│  - Sin estado, sin servidor                                   │
│  - $0.25 / millón tokens input · $1.25 / millón output       │
└─────────────────┬────────────────────────────────────────────┘
                  │ HTTPS API key
                  │
┌─────────────────▼────────────────────────────────────────────┐
│ RENDER FastAPI (existente)                                    │
│                                                               │
│  /api/llm/briefing/generate     (Sprint A — cron 06:00 COL)   │
│  /api/llm/forecast/explain      (Sprint B — interactivo)      │
│  /api/llm/qa/chat               (Sprint C — interactivo)      │
│                                                               │
│  LLMClient (httpx + retry + cost logging a app_llm_usage)     │
│  DuckDB tool calls (SQL whitelisted via sqlglot AST)          │
└──────────────┬────────────────┬───────────────────────────────┘
               │                │
               ▼                ▼
   ┌───────────────────┐   ┌───────────────────┐
   │ TELEGRAM BOT      │   │ PWA Next.js       │
   │ Briefing daily    │   │ Forecast page +   │
   │ Push al gerente   │   │ Q&A chat page     │
   └───────────────────┘   └───────────────────┘
                                    ▲
                                    │
                          GitHub Actions cron
                          06:00 COL daily
                          POST /api/llm/briefing/send
```

### Decisiones arquitectónicas

| Decisión | Por qué | Alternativa rechazada |
|----------|---------|------------------------|
| **OpenCode Zen** como LLM gateway | API key gratis sin tarjeta, expone 6 modelos free forever (DeepSeek, Qwen, MiMo, MiniMax, Nemotron), OpenAI-compatible API | Anthropic directo ($5 free 2 años, después $2.50/año + tarjeta), Gemini directo (free pero requiere Google Cloud project) |
| **`deepseek-v4-flash-free`** como modelo primario | Multi-idioma fuerte (español natural), buen razonamiento, JSON output, latencia ~2s | claude-haiku (requiere balance), gpt-mini (requiere balance) |
| **`qwen3.6-plus-free`** como fallback automático | Si OpenCode degrada DeepSeek free, Qwen sigue funcional. Alibaba mantiene alta disponibilidad | Sin fallback (riesgo single point of failure) |
| **Tool use con DuckDB tools whitelisted** | El LLM nunca escribe SQL libre; pide tools tipadas que ejecutan SQL pre-validado | Free SQL generation (riesgo de DROP TABLE, inyección) |
| **Telegram Bot** para delivery | Push real al celular del gerente, gratis, sin app extra | Email (puede ir a spam), PWA notification (requiere PWA abierta) |
| **GitHub Actions cron** para briefing diario | Free 2,000 min/mes, ya tenemos repo en GH, sin nueva infra | Render cron (Pro tier $$$), Cloudflare Worker (limitado en runtime) |
| **Sin streaming** en briefing | Es un push, no interactivo | Streaming agregaría complejidad por gusto |
| **Cost logging en tabla `app_llm_usage`** | Aunque sea $0, logueamos uso por modelo + tokens para audit | Sin logging — perderíamos visibilidad |

---

## 4. Stack tecnológico

### Componentes nuevos

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| LLM Gateway | **OpenCode Zen** vía `https://opencode.ai/zen/v1` | OpenAI-compatible API, key gratis sin tarjeta, expone 6 modelos free forever |
| Modelo primario | `deepseek-v4-flash-free` | Multi-idioma fuerte, español natural, free forever, latencia ~2s |
| Modelo fallback | `qwen3.6-plus-free` | Alta disponibilidad Alibaba, también free forever |
| LLM Client en FastAPI | **httpx** + wrapper liviano | OpenAI-compatible. No requiere SDK específico. ~30 líneas |
| Tool use SQL safety | **sqlglot** | Parser SQL que valida que la query del LLM solo lee de tablas whitelisted |
| Cron disparo briefing | **GitHub Actions** schedule | Gratis. Curl simple POST al API con admin token |
| Delivery briefing | **python-telegram-bot** | SDK oficial, gratis, instantáneo. Bot creado vía @BotFather |
| Audit logging | Nueva tabla `app_llm_usage` (MySQL InnoDB) | `tokens_input INT, tokens_output INT, model VARCHAR, endpoint VARCHAR, timestamp DATETIME` (costo=$0 pero seguimos contando) |
| Embeddings (ya en V1.5) | HuggingFace Inference API (free) | Reuse del Sprint 5 sub-bloque B — sin cambio |

### Lo que NO se agrega

- ❌ LangChain / LlamaIndex — agregan complejidad por adopción de framework no justificada para 3 features
- ❌ Vector DB dedicada (Pinecone/Weaviate) — DuckDB+vss ya cubre vector search
- ❌ Streaming SSE para chat — no agrega valor a UX para esta escala
- ❌ Fine-tuning — el caso de uso no lo justifica (4 prompts bien escritos > modelo fine-tuneado)
- ❌ LLM local (Ollama) — Windows tendría que estar prendido + calidad inferior + sin ahorro real

---

## 5. Roadmap de Sprints

### Sprint A · Briefing diario gerente (6-8h, primero por valor)

**Objetivo:** Cron diario que genera resumen narrativo y lo envía al gerente vía Telegram.

| Tarea | DoD |
|-------|-----|
| Crear cuenta Anthropic + API key | Token en Render env + `.env` |
| Crear Telegram Bot vía @BotFather | Token bot + chat_id del gerente registrado |
| Tabla `app_llm_usage` en MySQL | Schema creado, índice por timestamp |
| Endpoint `POST /api/llm/briefing/generate` | Lee 7 marts gold → arma contexto compacto (< 4K tokens) → llama LLM → parsea respuesta JSON → loguea costo |
| Endpoint `POST /api/llm/briefing/send` | Genera briefing + envía vía Telegram al chat_id configurado |
| Prompt engineering iterativo | 10+ ejemplos de briefings reales evaluados por PO. Lenguaje rioplatense/colombiano natural, no robótico |
| Validación honesta | Inyectar dato falso en mart → verificar que briefing detecta diff vs día anterior |
| GitHub Action workflow `.github/workflows/briefing-daily.yml` | Schedule `0 11 * * *` UTC (06:00 COL). Curl POST /api/llm/briefing/send con admin token desde secret |
| Cost dashboard endpoint `/api/admin/llm-cost` | Lee `app_llm_usage` agregado por mes |

**Criterio salida:** PO recibe el briefing en su celular durante 7 días seguidos sin intervención. Cost < $0.05 acumulado en esos 7 días.

---

### Sprint B · Forecast con narrativa explicativa (3-4h, segundo por low-hanging)

**Objetivo:** Convertir las cifras crudas del dashboard de forecast en una oración accionable.

| Tarea | DoD |
|-------|-----|
| Endpoint `POST /api/llm/forecast/explain` | Recibe forecast data del usuario, devuelve string narrativo |
| Prompt: contexto → narrativa | Toma WAPE actual + WAPE histórico + top 3 categorías mejores y peores → 3 oraciones útiles |
| Integrar en página `/forecast` PWA | Card arriba con narrativa generada (con loading skeleton). Cache cliente 1h |
| Cost cap por sesión | Si el usuario llama 10+ veces en 1 min → throttle a 1 cada 30s |
| Audit log | Cada call loguea en `app_llm_usage` |

**Criterio salida:** PO entra a `/forecast`, lee la narrativa de un vistazo, entiende sin tener que interpretar números. Costo < $0.001 por call.

---

### Sprint C · Q&A conversacional sobre el negocio (10-14h, último por complejidad)

**Objetivo:** Página `/chat` donde el gerente pregunta libre y el sistema responde leyendo DuckDB.

**Esto es lo más ambicioso de V1.6. Si no llegamos, queda diferido a V2.**

| Tarea | DoD |
|-------|-----|
| Diseñar tools whitelisted | 8-10 tools tipadas con `pydantic`. Ej: `get_top_skus_by_period(period, limit)`, `get_dormidos_with_filters(...)`, `compare_periods(p1, p2)` |
| Sandbox SQL con `sqlglot` | Parser detecta que la query es SELECT puro contra tablas `motoshop_gold_*` o `motoshop_silver_*`. Bloquea DML/DDL |
| Endpoint `POST /api/llm/qa/chat` | Body `{message, conversation_id}`. Maneja sesión en memoria con TTL 30 min. Loop: LLM → tool call → ejecución → resultado → LLM → respuesta final |
| Página `/chat` en PWA | UI tipo chat (mensajes con bubbles). Historial de la sesión actual. Send button + Enter. Streaming opcional |
| Limit guardrails | Máximo 20 turnos por sesión. Máximo 5 tool calls por turno. Máximo $0.05 por sesión (corte hard) |
| Cost tracking por sesión | Cada turno actualiza `app_llm_usage` con `conversation_id` |
| Tests adversariales | 20 preguntas raras evaluadas por PO: ambiguas, ofensivas, fuera-de-scope, intentos de inyección SQL |
| Documentación pedagógica en la página | Bloque colapsable: "qué puedo preguntar / qué NO puedo preguntar". Lista de preguntas ejemplo |

**Criterio salida:** PO hace 10 preguntas reales sobre el negocio, recibe respuestas correctas con cifras correctas. Cero alucinación detectada. Costo por sesión < $0.05.

**Criterio para PARAR si se complica:**
- Si después de 8h no llegamos a respuestas confiables → cerrar Sprint C como "experimento documentado, diferido a V2"
- No forzar el cierre. Mejor 2 features sólidas que 3 mediocres

---

## 6. Risk register

| ID | Riesgo | Mitigación | Severidad |
|----|--------|------------|-----------|
| RL1 | LLM inventa cifras (hallucination) | Tool use estricto; todo número debe venir de DuckDB. Tests adversariales en Sprint A | Alta |
| RL2 | Costo se dispara por prompt mal ajustado | Cost cap por sesión + alertas si mes > $1 + logging por endpoint | Media |
| RL3 | Telegram bot bloqueado por gerente o Telegram rate-limit | Fallback a email (Resend free tier) si Telegram falla 3 veces | Baja |
| RL4 | LLM provider cambia precios (Anthropic deja de ser barato) | Wrapper abstrae provider, podemos cambiar a OpenAI en 1h con cambio de SDK | Baja |
| RL5 | SQL injection vía Q&A | sqlglot valida AST, tools whitelisted, never run raw user input | Alta (mitigada) |
| RL6 | Latencia de LLM hace que el chat se sienta lento | Acceptable para texto, mostrar typing indicator. Si > 10s → timeout | Baja |
| RL7 | API key de LLM expuesta en repo | `.env` + render env vars, nunca commit | Resolved by process |

---

## 7. Cost projection

**$0 USD / mes para siempre.** OpenCode Zen `deepseek-v4-flash-free` y `qwen3.6-plus-free` no consumen balance.

**Lo que SÍ tenemos que vigilar:**

| Recurso | Limit aplicable | Lo que MotoShop usa | Headroom |
|---------|-----------------|----------------------|----------|
| OpenCode rate limit free | (no publicado, asumir ~60 RPM por modelo) | Briefing diario 1/día + chat ocasional | x100 |
| HuggingFace Inference free | ~1000 req/mes | Búsqueda semántica ~100 req/día | Suficiente con margen |
| GitHub Actions free | 2000 min/mes private | Briefing cron 1 min/día = 30 min/mes | x60 |
| Telegram Bot | unlimited | Briefing diario + reportes manual | sin riesgo |
| Render free | 750 hours/mes | UptimeRobot mantiene warm | sin riesgo |
| Cloudflare R2 free | 10 GB + 10M ops/mes | 22MB DuckDB + ~10K refreshes | x1000 |

**Riesgo único:** que OpenCode cambie términos del free tier. Mitigación: el wrapper `LLMClient` abstrae el provider, se puede cambiar a Anthropic (con $5 free) o Google Gemini (1500 req/día free) en <1h de trabajo si pasa.

---

## 8. Equipo y handoffs

| Dev | Sprints | Tiempo |
|-----|---------|--------|
| **Dev L (LLM specialist)** | A, B, C | 19-26h total |

Puede ser el mismo Dev D o Dev F si tiene experiencia con LLM APIs. Si no, recomiendo agente fresco con expertise.

Handoff específico (al activarse V1.6) se genera en `docs/handoffs-v1.6.md`.

---

## 9. Dependency graph

```
V1.5 Sprint 4 ──► V1.5 Sprint 5 (incluye búsqueda semántica)
                        │
                        ▼
                V1.6 Sprint A ──► Sprint B ──► Sprint C
                  Briefing       Narrativa     Q&A chat
                   6-8h           3-4h         10-14h
```

**Sprint A primero** porque es el de mayor valor operativo (el gerente recibe el briefing en el celular cada mañana sin entrar a la PWA).
**Sprint B después** porque reusa el LLMClient ya construido.
**Sprint C al final** porque es el más complejo y el que más riesgo tiene de no cerrar.

---

## 10. Definition of Done V1.6

V1.6 cierra cuando:

- [ ] Briefing diario llega al PO en Telegram 7 días seguidos sin intervención
- [ ] Forecast page muestra narrativa generada por LLM con cifras correctas
- [ ] Página `/chat` funcional con tool use sobre DuckDB (o documentada como diferida a V2 si Sprint C no cierra)
- [ ] Tabla `app_llm_usage` operativa con cost dashboard
- [ ] Costo acumulado < $1 en el mes de validación
- [ ] ADR-0024 (LLM provider + cost policy) Accepted
- [ ] ADR-0025 (RAG sandboxing) Accepted o "N/A si Sprint C diferido"
- [ ] SEGUIMIENTO.md bloque V1.6 cierre con métricas de adopción real (cuántos briefings recibidos, cuántas queries chat)

---

## 11. Notas técnicas clave

### ¿Por qué Anthropic Claude Haiku y no OpenAI gpt-4o-mini?

Decisión justa: ambos son equivalentes en costo y calidad para nuestro caso. Elegí Anthropic por:
- Tool use ligeramente más estricto (mejor para nuestro sandboxing)
- JSON mode más confiable (briefing necesita JSON parseable)
- Mejor manejo de prompts en español

El wrapper `LLMClient` abstrae el provider — cambiar a OpenAI en 1h si Anthropic cambia precios.

### ¿Por qué Telegram y no PWA push notification?

PWA push requiere:
- Service worker registrado (ya tenemos)
- Permiso del usuario (alta fricción)
- Que la PWA esté instalada en el celular del gerente
- iOS lo soporta solo desde Safari 16.4+

Telegram requiere:
- Que el gerente tenga Telegram (universal en Colombia)
- Un /start una vez

Latencia y reliability de Telegram > PWA push para este caso.

### ¿Cómo evitamos que el LLM alucine cifras?

Patrón estricto:
1. **Briefing**: el contexto que enviamos al LLM contiene SOLO las cifras ya calculadas por queries DuckDB. El LLM "narra", no "calcula". Validación post-LLM: regex matches sobre `\$[\d,]+` y verifica que cada número aparezca en el contexto enviado.
2. **Forecast narrativa**: idem.
3. **Q&A**: tool use estricto. El LLM puede pedir `get_top_skus_by_period(period="2026-05")` pero no puede generar "vendiste $X". Toda cifra viene literal del tool response.

Si el LLM inventa un número → test falla → re-prompting.

### ¿Cómo escalamos si MotoShop crece?

Si el dataset crece 10x:
- Briefing sigue OK (resumimos antes de mandar al LLM)
- Forecast sigue OK
- Q&A puede necesitar RAG con vector search sobre documentos (que ya tenemos vss en DuckDB)

DuckDB+Claude escala hasta donde necesitemos. No hay refactor arquitectónico previsto.

---

## 12. Trigger de arranque

V1.6 arranca cuando:
- V1.5 Sprint 4 firmado por revisor (cutover DuckDB en producción operativo)
- V1.5 Sprint 5 firmado por revisor (frontend + búsqueda semántica funcional)
- PO da kickoff explícito

Antes de eso, este documento queda como plan aprobado pero **no se ejecuta**. No paralelizar con V1.5.

---

*Documento creado: 2026-05-31*
*Aprobado por: PO (humano) — kickoff diferido post-V1.5*
*Doc relacionado: `docs/plan-v1.5-duckdb.md`*
