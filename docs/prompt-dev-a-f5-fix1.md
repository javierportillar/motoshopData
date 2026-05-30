# Prompt Dev A · F5-FIX1 · Backend/Infra Fixes

```
Soy Dev A · Track A para F5-FIX1 del proyecto MotoShop.

PRE-FLIGHT:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé docs/plan-f5-fix1.md

MI MISIÓN:
Limpiar credenciales hardcodeadas, completar R14 cleanup, crear ADR-0019.

TAREAS (en orden de prioridad):

### C-3: Limpiar passwords hardcodeadas (PRIORITARIO)

Problema: "Sashita123" aparece hardcodeado en ~19 archivos de infra/.
Fix:
1. Buscar: grep -r "Sashita123" infra/ --include="*.ps1" --include="*.py" --include="*.md"
2. En cada archivo .ps1: reemplazar el password por $env:MYSQL_PASSWORD o Get-Content .env
3. En cada archivo .py: reemplazar por os.getenv("MYSQL_PASSWORD")
4. En cada .md: eliminar la referencia al password
5. Verificar que .env.example tenga MYSQL_PASSWORD como placeholder
6. Confirmar: grep -r "Sashita123" . debe devolver 0 resultados

### C-4: Eliminar Databricks PAT de markdown

Problema: Token de Databricks expuesto en documentos versionados.
Fix:
1. Buscar: grep -r "dapi" docs/ PENDIENTES.md SEGUIMIENTO.md
2. Reemplazar tokens por <DATABRICKS_TOKEN> o eliminar la referencia
3. Si el PAT está en historial git, documentar como deuda (no reescribir historial)

### C-5: JWT_SECRET real en start_api.ps1

Problema: Script de deploy usa JWT_SECRET de prueba.
Fix:
1. Abrir infra/start_api.ps1
2. Buscar JWT_SECRET hardcodeado
3. Reemplazar por: $env:JWT_SECRET o lectura de .env
4. Verificar que .env tenga JWT_SECRET=<real>

### M-2: R14 cleanup — archivar notebooks Prophet/LightGBM

Fix:
1. Mover infra/run_forecast_prophet.py → docs/archive/infra/
2. Mover infra/run_forecast_lightgbm.py → docs/archive/infra/
3. Crear docs/archive/infra/README.md explicando que estos scripts
   fueron removidos de producción en F5 porque Prophet/LightGBM
   no superan al baseline (documentado en F4-FIX1).
4. Verificar que create_gold_workflow.py no referencie estos scripts

### M-3: Crear ADR-0019

Archivo: docs/decisions/0019-idempotency-rbac.md

Contenido mínimo:
- Status: Proposed
- Context: F5 abre escritura PWA→MySQL
- Decision: idempotency-key UUID v4 + UNIQUE constraint, RBAC por JWT claims
- Alternatives: Redis dedup, session-based auth
- Consequences: patrón replicable para F6+

VERIFICACIÓN:
- grep -r "Sashita123" . → 0 resultados (V-F4)
- start_api.ps1 lee JWT_SECRET de .env (V-F5)
- docs/decisions/0019-idempotency-rbac.md existe (V-F6)
- R14: Prophet/LightGBM en docs/archive/ (V-F6)

LO QUE NO TOCO:
- motoshop-app/web/** (Dev T)
- Tests de frontend (Dev T)
- Credenciales reales en .env (solo .env.example)

COMMITS:
- prefijo: fix(F5-fix1): ...
```
