# MotoShopData — Transformación digital de una motopartes

Esto nació como proyecto de la materia **Big Data y Transformación Digital del Negocio** (Maestría UAO, 2025-2) y terminó siendo mucho más. Arrancó con una BD MySQL 5.0 de un sistema que se llama sgHermes, y la idea es llevarla a un lakehouse en Databricks con todo lo que eso implica: ingesta, transformación, ML, y una PWA para consultar desde el celu.

Son dos tracks paralelos:

- **Track A · Analítico** — Databricks Lakehouse con arquitectura medallion (bronze → silver → gold) + modelos ML.
- **Track T · Transaccional** — FastAPI + PWA con Next.js para consultar stock, ventas, predicciones, alertas.

> El estado vivo del proyecto, decisiones, y qué está pasando ahora está en [SEGUIMIENTO.md](SEGUIMIENTO.md). Ahí está todo el detalle día a día.

---

## Cómo está organizado el repo

```
motoshopData/
├── PLAN.md                      El plan maestro con la visión general
├── SEGUIMIENTO.md               Bitácora viva: sesiones, avances, checklist
├── INICIAR_AGENTE.md            Para cuando arranco una sesión con IA
├── INICIAR_REVIEWER.md          Para cuando alguien viene a auditar
├── PENDIENTES.md                Lo que yo (Javier) tengo que hacer entre sesiones
├── infollm.md                   Datos de conexión a la BD y esquema
├── AGENT_PROMPT.md              Cómo está configurado el agente de IA
├── pyproject.toml               Python (Track A — tests, lint)
├── .env.example                 Template de variables de entorno
│
├── docs/                        Documentación del proyecto
│   ├── decisiones/              ADRs — cada decisión técnica justificada
│   ├── plan-f1.md, plan-f2.md…  Planes detallados por fase
│   ├── contexto-proyecto.md     Snapshot del proyecto para ponerse al día
│   └── handoff-f1.md, …         Handoffs para arranque de fase
│
├── notebooks/                   Track A — Notebooks Databricks
│   ├── bronze/                  Ingesta de datos crudos
│   ├── silver/                  Limpieza y transformación
│   └── gold/                    Métricas, marts, features stores, ML
│
├── src/motoshop/                Código Python reusable
├── tests/                       Tests de transformaciones y lógica
├── infra/                       Scripts de infraestructura
│   ├── backup_mysql.sh/.ps1     Backups de la BD
│   └── run_*.py                 Scripts portables de ML (corren en Mac o Windows)
│
├── motoshop-app/                Track T — API + PWA
│   ├── api/                     FastAPI con endpoints de negocio
│   └── web/                     Next.js 14 + PWA
│
└── mlruns/                      Experimentos de MLflow locales
```

Decisión de mantener todo en un monorepo: [ADR-0009](docs/decisions/0009-monorepo-vs-two-repos.md).

---

## Las fases del proyecto

Son 7 fases, de la 0 a la 6. Cada una tiene su gate de verificación antes de pasar a la siguiente.

```
F0 🟢 Cimientos — Conexión a BD, Databricks, túnel, backups, usuarios
F1 🟢 Ingesta — Bronze con 12 tablas core + API funcionando
     └── F1.5 Hardening — Cache de stock, robustez
     └── F1.9 Pipeline — Sondeo BD, lag monitor, task scheduler
F2 🟢 Silver + PWA — Limpieza de datos + app web instalable
F3 🟢 Gold + Dashboards — Marts de negocio + dashboards + workflow
     └── F3.5 Silver Hardening — Corrección universo ventas completo
     └── F3.6 Quality Gold — Fix quality + sanity checks
F4 🟡 Predictivo — Forecasting demanda + alertas de quiebre de stock
     ├── F4-A Feature Store + Baseline ✅
     ├── F4-B Modelos ML (Prophet, LightGBM, Classifier) ✅
     └── F4-C API + PWA Predicciones/Alertas 🟡
F5 ⬜ Escritura — Cotizaciones y pedidos desde la app
F6 ⬜ Prospectivo — Optimización de compras, what-if, CI/CD completo
```

---

## Estado actual

Estoy en **Fase 4 — Predictivo**. Hasta ahora:

- ✅ Feature store con 4,392 SKUs y 34,838 registros de demanda diaria
- ✅ Baseline naïve con MAPE 43.72% registrado en MLflow
- ✅ Prophet top-100 (no supera baseline — demanda intermitente)
- ✅ LightGBM global (no supera baseline — mismo problema)
- ✅ Clasificador de quiebre con F1=0.99 — 69 alertas en gold.alertas_quiebre
- ✅ API endpoints para forecast y alertas
- ✅ PWA con páginas de predicciones y alertas
- 🟡 Integrar PWA con datos reales de forecast/alertas
- ⬜ Push notifications activas
- ⬜ Correo de alertas desde Workflows

Lo más valioso hasta ahora: el clasificador de quiebre. Los modelos de forecasting no superaron al baseline porque las autopartes tienen demanda muy intermitente (80% de los días son 0). Pero saber qué SKU se va a quedar sin stock antes de que pase — eso es útil ya.

---

## Reglas que no negocio

1. **sgHermes es intocable** — no se modifican esquemas, datos ni permisos del MySQL productivo.
2. **Credenciales fuera de Git** — siempre `.env`, nunca hardcodeadas.
3. **Toda cifra en pantalla debe cuadrar con sgHermes** con tolerancia documentada.
4. **Modelo que no supera al baseline no se libera** — prefiero el promedio histórico conocido.
5. **Predicciones son sugerencias revisables**, no decisiones autónomas (hasta F6).

---

## Cómo arrancar todo local

```bash
# Track A — Python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest

# Track T — API
cd motoshop-app/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn motoshop_api.main:app --reload --port 8000

# Track T — Web
cd motoshop-app/web
npm install
cp .env.local.example .env.local
npm run dev
```

Para arrancar todo junto en el PC (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File infra\start_motoshop.ps1
```

Para probar la demo desde el celu:
1. Apagar WiFi (solo 4G)
2. Ir a `https://api.fragloesja.uk/demo`

---

## Links rápidos

| Qué | Dónde |
|-----|-------|
| Documentación general | [docs/contexto-proyecto.md](docs/contexto-proyecto.md) |
| Decisiones técnicas | [docs/decisions/](docs/decisions/README.md) |
| Estado en vivo | [SEGUIMIENTO.md](SEGUIMIENTO.md) |
| Mis pendientes | [PENDIENTES.md](PENDIENTES.md) |
| Plan maestro | [PLAN.md](PLAN.md) |
