# Plan F1.5 · Hardening pre-F2

> Sprint corto, **proactivo** (no es FIX, nada está roto). Cierra 2 de las 5 deudas vivas de F1 antes de construir Silver y PWA encima. Originado por recomendación humana 2026-05-28 (Sesión 18): *"Fortalece idempotencia y validaciones + Optimiza latencia /stock"*.
>
> Tiempo estimado: **~2 horas** del ejecutor. F2 arranca después.

---

## 1 · Por qué hacerlo ANTES de F2

| Si no lo hacemos | Lo que pasa |
|------------------|-------------|
| R3 sin cerrar (idempotencia kill-y-retry) | Silver agregará sobre Bronze potencialmente inconsistente; los KPIs cuadrarán consigo mismos pero no con sgHermes. Regla de Oro #3 se rompe silenciosamente. |
| R-X2 sin cerrar (latencia 781 ms) | El hito de F2 ("vendedor abre app, busca, ve stock") se sentirá lento en el celular. El feedback de gerencia (E3 académico) va a ser sobre velocidad, no funcionalidad. |

Costo: 2 horas. Beneficio: F2 entra con base limpia y baseline correcto de UX.

---

## 2 · Lo que NO entra en este sprint

| Deuda | Por qué se mantiene |
|-------|---------------------|
| R1 (passwords MySQL en historial) | Acotado a `@localhost`, mitigaciones activas. Trigger documentado. |
| R2 (FG28 en README) | Decisión humana 2026-05-28: extendida indefinida hasta nuevo aviso. |
| R4 (Workflow Databricks postergado) | Task Scheduler cubre. Solo se aborda si compute se mueve a Databricks. |
| Iteración constante (recomendación 3) | Es un **principio**, no una tarea. Ya está embebido en la metodología (KPIs medidos, evidencia versionada, ADRs, bitácora). |

---

## 3 · Tarea 1 · R3 · Probar idempotencia kill-y-retry

### Objetivo

Demostrar que matar el dump a mitad de corrida y reintentarlo deja Bronze en estado correcto (conteos == MySQL para la fecha de ingesta).

### Pre-requisitos

- Ejecutor con acceso a la PC MotoShop.
- `.venv-infra` operativo (`python infra/dump_to_cloud.py --help` responde).
- Conexión a Databricks (`DATABRICKS_TOKEN` válido en `.env`).
- **Acordar ventana de prueba** fuera del schedule normal (02:00, 12:00, 20:00). Recomendado: una vez que un schedule termine, antes del siguiente.

### Pasos

**3.1 · Capturar estado inicial**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1

# Borrar staging local para empezar limpio
Remove-Item -Recurse -Force _staging -ErrorAction SilentlyContinue

# Anotar la fecha de prueba (usá una distinta a la del último schedule para no contaminar)
$TEST_DATE = "2026-05-30"
Write-Host "Fecha de prueba: $TEST_DATE"
```

**3.2 · Primera corrida (la que vamos a matar)**

En **terminal A**:

```powershell
python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE 2>&1 | Tee-Object -FilePath _staging\kill_test_run1.log
```

En **terminal B**, mientras corre, monitorear:

```powershell
Get-Content -Wait C:\Users\MotoShop\Documents\javidevmoto\_staging\kill_test_run1.log
```

Esperar a que el log muestre que terminó la 6ª tabla (cuando muestre `→ terceros: extrayendo...` o similar — la 7ª). Entonces matar con `Ctrl+C` en terminal A.

**3.3 · Inspeccionar el estado post-kill**

```powershell
# ¿Qué Parquets quedaron en _staging?
Get-ChildItem -Recurse _staging\*.parquet | Select-Object FullName, Length, LastWriteTime

# ¿Algún Parquet trunco? Verificar que se puede leer
python -c "
import pyarrow.parquet as pq
import pathlib
for p in pathlib.Path('_staging').rglob('*.parquet'):
    try:
        t = pq.read_table(p)
        print(f'OK  {p.name}: {t.num_rows} filas')
    except Exception as e:
        print(f'BAD {p.name}: {e}')
"

# ¿Qué subió al UC Volume? (lista vía SDK)
python -c "
from databricks.sdk import WorkspaceClient
import os
from dotenv import load_dotenv
load_dotenv()
w = WorkspaceClient(host=os.getenv('DATABRICKS_HOST'), token=os.getenv('DATABRICKS_TOKEN'))
TEST_DATE = '$TEST_DATE'
for table in ['facventas','detfventas','productos','auxinventario','bodegas','terceros','compras','detcompras','sucursales','formapago','subproduct','preciosxpro']:
    path = f'/Volumes/motoshop/bronze/_landing/{table}/ingest_date={TEST_DATE}'
    try:
        files = list(w.files.list_directory_contents(path))
        print(f'{table}: {len(files)} archivos')
    except Exception:
        print(f'{table}: (no existe)')
"
```

**Anotar:** cuántas tablas alcanzaron a subir antes del kill. Esto define el escenario que estamos probando.

**3.4 · Segunda corrida (retry completo)**

```powershell
python infra\dump_to_cloud.py --tables-core --ingest-date $TEST_DATE 2>&1 | Tee-Object -FilePath _staging\kill_test_run2.log
```

Dejarla terminar completa.

**3.5 · Ingestar a Bronze para esa fecha**

En Databricks (notebook `02_ingest_all_bronze.py`):

- Widget `ingest_date = 2026-05-30`.
- Run all.

**3.6 · Verificar idempotencia**

En Databricks SQL Warehouse:

```sql
-- Para cada tabla, comparar el conteo en bronze (partición de prueba)
-- con el COUNT correspondiente en MySQL (vía DBeaver o test_mysql_connectivity).

-- Bronze (12 tablas):
SELECT 'facventas' AS t, COUNT(*) AS bronze_rows FROM motoshop.bronze.facventas WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'detfventas', COUNT(*) FROM motoshop.bronze.detfventas WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'productos', COUNT(*) FROM motoshop.bronze.productos WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'auxinventario', COUNT(*) FROM motoshop.bronze.auxinventario WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'bodegas', COUNT(*) FROM motoshop.bronze.bodegas WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'terceros', COUNT(*) FROM motoshop.bronze.terceros WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'compras', COUNT(*) FROM motoshop.bronze.compras WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'detcompras', COUNT(*) FROM motoshop.bronze.detcompras WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'sucursales', COUNT(*) FROM motoshop.bronze.sucursales WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'formapago', COUNT(*) FROM motoshop.bronze.formapago WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'subproduct', COUNT(*) FROM motoshop.bronze.subproduct WHERE ingest_date = '2026-05-30'
UNION ALL SELECT 'preciosxpro', COUNT(*) FROM motoshop.bronze.preciosxpro WHERE ingest_date = '2026-05-30';
```

En MySQL (DBeaver o el script):

```sql
-- Para `facventas` (ejemplo, repetir para las 12):
SELECT COUNT(*) FROM motoshop2024.facventas WHERE estdoc = 'A';
-- Comparar con bronze_rows del SELECT anterior. Deben coincidir.
```

### Acceptance criteria

- **R3 ✅** si para las 12 tablas: `bronze_rows == count_origen_mysql`.
- **R3 con observación** si hay diferencias pequeñas explicables (ej. ventas nuevas entre la 1ª y 2ª corrida) → documentar.
- **R3 ❌** si hay diferencias inexplicables → blindar `dump_to_cloud.py`:
  - Limpiar `_staging/<tabla>/` antes de escribir cada tabla (probable fix).
  - Atomic write: escribir a `.tmp` y `os.rename` solo si completa.

### Evidencia

`notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md` con esta plantilla:

```markdown
# R3 · Idempotencia kill-y-retry — 2026-05-30

## Setup
- Fecha de prueba: 2026-05-30 (distinta a corridas normales)
- Tablas ya subidas al Volume antes del kill: X / 12
- Parquets locales presentes tras kill: lista

## Run 1 (matado)
- Duración hasta kill: Ns
- Tablas completadas: 6 / 12
- Última tabla en proceso: terceros (truncado o incompleto)

## Run 2 (retry)
- Duración: Ns
- Tablas completadas: 12 / 12

## Conteos finales (bronze vs MySQL)
| Tabla | Bronze | MySQL | Diferencia |
|-------|--------|-------|------------|
| facventas | 6336 | 6336 | 0 |
| ... | ... | ... | ... |

## Veredicto
✅ R3 cumplida — kill-y-retry deja Bronze consistente.
(o ⚠️ con observaciones / ❌ con explicación)

## Trade-off documentado
INSERT REPLACE WHERE en el notebook 02 sobreescribe la partición del día completa
en cada corrida exitosa. El estado intermedio (entre Run 1 matado y Run 2 completo)
no se ingesta a Bronze hasta el notebook 02. Por tanto, el riesgo se limita a
Parquets parciales en el UC Volume entre runs, lo cual el siguiente upload reemplaza
con overwrite=True.
```

### Si R3 falla (NO debería, pero por si)

Documentar el modo de falla y crear ADR-0013 (o un PR mini) que ajuste `dump_to_cloud.py`:

```python
# Patrón "atomic move":
def write_parquet(table, columns, rows, ingest_date):
    out_dir = STAGING_DIR / table / f"ingest_date={ingest_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    final_file = out_dir / "part-0.parquet"
    tmp_file = out_dir / "part-0.parquet.tmp"
    # Write to tmp
    pq.write_table(table_pa, tmp_file, compression="snappy")
    # Atomic rename
    tmp_file.replace(final_file)
    return final_file
```

---

## 4 · Tarea 2 · R-X2 · Cache `/stock` con TTL 5 min

### Objetivo

Bajar la latencia p95 de `GET /products/{sku}/stock` de 781 ms a < 500 ms con caché en memoria. Trade-off: stock visible puede estar hasta 5 min desactualizado.

### Pre-requisitos

- Test integration de `/stock` corre (aunque sea manualmente).
- Ejecutor con acceso al código de la API.

### Archivos a modificar

| Path | Cambio |
|------|--------|
| `motoshop-app/api/pyproject.toml` | Añadir `cachetools>=5.3` a dependencies |
| `motoshop-app/api/src/motoshop_api/stock/repo.py` | Instrumentar `StockRepo.get_stock_by_sku` con `TTLCache` |
| `motoshop-app/api/tests/test_stock.py` | Test que 2 llamadas seguidas al mismo SKU → 1 hit (mock o spy del repo) |
| `infra/measure_stock_latency.ps1` *(opcional)* | Si no existe, crear; sirve para K-1 re-medición |

### Implementación sugerida

`stock/repo.py`:

```python
"""Repositorio de stock — lee auxinventario para cantidades."""

from __future__ import annotations

from cachetools import TTLCache
from sqlalchemy import Engine, select, func

from motoshop_api.db.tables import productos, bodegas, auxinventario

# Cache en memoria. 200 SKUs distintos × 5 min TTL.
# Trade-off documentado: el stock visible puede estar hasta 5 min desactualizado.
# Aceptable para una operación de tienda (no de trading).
_stock_cache: TTLCache[str, dict] = TTLCache(maxsize=200, ttl=300)


class StockRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_stock_by_sku(self, sku: str) -> dict:
        # Cache hit
        cached = _stock_cache.get(sku)
        if cached is not None:
            return cached

        # Cache miss: query como antes
        prod_stmt = select(productos).where(productos.c.codprod == sku)
        with self._engine.connect() as conn:
            prod_row = conn.execute(prod_stmt).mappings().first()
            if not prod_row:
                result = {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []}
                _stock_cache[sku] = result
                return result

            nomprod = prod_row.get("nomprod", "")

            try:
                stock_stmt = (
                    select(
                        auxinventario.c.codprod,
                        func.coalesce(auxinventario.c.codbod, "SIN_BODEGA").label("codbod"),
                        func.sum(auxinventario.c.valor3).label("cantidad"),
                    )
                    .where(auxinventario.c.codprod == sku)
                    .group_by(auxinventario.c.codprod, auxinventario.c.codbod)
                )
                stock_rows = conn.execute(stock_stmt).mappings().all()

                if not stock_rows:
                    result = {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}
                    _stock_cache[sku] = result
                    return result

                total = sum(float(r["cantidad"] or 0) for r in stock_rows)
                by_bodega = [
                    {"codbod": r["codbod"], "nombod": r["codbod"], "cantidad": float(r["cantidad"] or 0)}
                    for r in stock_rows
                ]

                result = {"sku": sku, "nomprod": nomprod, "total": total, "by_bodega": by_bodega}
                _stock_cache[sku] = result
                return result
            except Exception:
                return {"sku": sku, "nomprod": nomprod, "total": 0, "by_bodega": []}


# Función para invalidar el caché (útil en tests y en escenarios futuros de write).
def clear_stock_cache() -> None:
    _stock_cache.clear()


class FakeStockRepo:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    def get_stock_by_sku(self, sku: str) -> dict:
        return self._data.get(sku, {"sku": sku, "nomprod": None, "total": 0, "by_bodega": []})
```

`tests/test_stock.py` — añadir:

```python
def test_stock_cache_hits_second_call(client_with_stock, fake_users, admin_token, monkeypatch) -> None:
    """R-X2: segunda llamada al mismo SKU sale del caché, no del repo."""
    from motoshop_api.stock import repo as stock_repo_module
    stock_repo_module.clear_stock_cache()

    # Counter de hits al repo real
    calls = {"n": 0}
    original = stock_repo_module.FakeStockRepo.get_stock_by_sku
    def spy(self, sku):
        calls["n"] += 1
        return original(self, sku)
    monkeypatch.setattr(stock_repo_module.FakeStockRepo, "get_stock_by_sku", spy)

    # Primera llamada → cache miss (calls = 1)
    r1 = client_with_stock.get("/products/MOTS1011/stock",
                                headers={"Authorization": f"Bearer {admin_token}"})
    assert r1.status_code == 200

    # Segunda llamada al mismo SKU → cache hit (calls debería seguir en 1
    # si la cache funciona sobre el repo real, no el fake)
    # Nota: como FakeStockRepo se inyecta via dependency_overrides, este test
    # documenta el patrón. La validación real del cache se hace con el repo real
    # en tests integration.
```

> **Nota técnica:** como `FakeStockRepo` no usa la cache (es la `StockRepo` real la que la tiene), el test de cache sobre FakeRepo es ilustrativo. La validación real del comportamiento de cache requiere un test integration que apunte a MySQL. Documentar esto en el test.

### Pasos

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"   # instala cachetools
pytest -m "not integration" -v
```

### Re-medición K-1

Mismo script de las 100 requests, pero hacer **dos pasadas**:

1. **Pasada cold (cache vacía):** 100 requests, p95 esperado ~750 ms (sin cambio, primer hit es como antes).
2. **Pasada warm (después de la cold):** 100 requests, p95 esperado < 50 ms.

Si la PWA real consulta el mismo SKU varias veces (probable: vendedor refresca o navega), la p95 efectiva del flujo de usuario será ~la warm.

Capturar en `notebooks/api/_runs/r_x2_cache_2026-05-30.json`:

```json
{
  "sku": "MOTS1297",
  "requests_per_run": 100,
  "cold_run": {
    "p50_ms": 670,
    "p95_ms": 780,
    "p99_ms": 815
  },
  "warm_run": {
    "p50_ms": 2,
    "p95_ms": 5,
    "p99_ms": 12
  },
  "meta_cumplida": true,
  "nota": "Cold run sin cambio (era de esperar). Warm run p95 < 50 ms. La p95 percibida por la PWA dependerá del patrón de re-consulta."
}
```

### Acceptance criteria

- `pytest -m "not integration"` verde (incluye los tests existentes + el nuevo).
- Warm run p95 < 500 ms.
- Trade-off documentado en el docstring de `_stock_cache` y en el `.md` de evidencia.

### Riesgos del cache

1. **Stock desactualizado hasta 5 min.** Aceptado.
2. **Memoria:** 200 SKUs × ~500 bytes ≈ 100 KB. Insignificante.
3. **Concurrencia:** `cachetools.TTLCache` es **NO thread-safe**. FastAPI corre async pero las queries son sync con SQLAlchemy. El acceso al dict en CPython es atómico para `get`/`set` de claves individuales; en este uso (key SKU, value dict) no hay race condition real. Si en F6 movemos a workers múltiples (gunicorn) hay que migrar a `cachetools.lru_cache` con `@cached(cache=..., lock=Lock())` o a Redis.

---

## 5 · Tarea 3 · Sincronizar SEGUIMIENTO + contexto-proyecto

### Cambios en `SEGUIMIENTO.md`

**§Tablero de riesgos vivos:**

- **R3:** estado actualizado a ✅ Resuelto (o ⚠️ con observaciones) según resultado de Tarea 1.
- **R-X2:** estado actualizado a ✅ Resuelto con cifra warm p95.

**§Notas de sesión — añadir Sesión 19 arriba:**

```markdown
### 2026-05-29 — Sesión 19 · F1.5 Hardening pre-F2 (R3 + R-X2 cerradas)

- **Hecho:**
  - ✅ R3 · idempotencia kill-y-retry probada y cerrada. Evidencia: `notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md`.
  - ✅ R-X2 · cache /stock con TTLCache(200, 300s). Warm run p95 < 50 ms. Evidencia: `notebooks/api/_runs/r_x2_cache_2026-05-30.json`.
  - ✅ SEGUIMIENTO §Tablero de riesgos vivos sincronizado: R3 ✅, R-X2 ✅.
  - ✅ `docs/contexto-proyecto.md` §10 actualizado.
- **Aprendido:**
  - El patrón `INSERT REPLACE WHERE` + `overwrite=True` en upload protege idempotencia siempre que el job termine completo. Kill mid-run sin retry deja inconsistencia, pero el siguiente retry exitoso converge.
  - La cache cubre el patrón real de uso de la PWA (re-consulta de SKUs vistos). Cold-run sigue lenta pero ocurre 1 vez por SKU cada 5 min.
- **Abierto:**
  - R1, R2, R4 siguen como deudas documentadas (sin cambios).
  - ADR-0012 (stack F2) por escribir en Sesión 20.
- **Próximo paso:**
  - Sesión 20: planificar Fase 2 · Silver + PWA MVP.
```

### Cambios en `docs/contexto-proyecto.md`

§10 Riesgos vivos: actualizar R3 y R-X2 a ✅ resuelto con fecha + referencia a evidencia.

§12.4 Métricas: actualizar latencia `/stock` p95 a `~50 ms (warm) / 780 ms (cold)`, con nota.

§6.2 Cronología F1: añadir entrada Sesión 19.

§15 Resumen ejecutivo: actualizar (ahora 3 deudas, no 5).

### Cambios en `PENDIENTES.md`

Marcar las 3 tareas de Sesión 18 a ✅. Añadir bloque Sesión 19 cerrado.

### Commit

```powershell
git add `
  motoshop-app/api/pyproject.toml `
  motoshop-app/api/src/motoshop_api/stock/repo.py `
  motoshop-app/api/tests/test_stock.py `
  notebooks/bronze/_runs/r3_idempotency_kill_retry_2026-05-30.md `
  notebooks/api/_runs/r_x2_cache_2026-05-30.json `
  SEGUIMIENTO.md `
  PENDIENTES.md `
  docs/contexto-proyecto.md

git commit -m "feat(F1.5): hardening pre-F2 - R3 idempotencia + R-X2 cache stock"
git push
```

**Antes del commit:** `git diff --cached | grep -iE "password\s*[:=]\s*['\"]"` debe estar vacío.

---

## 6 · Cierre y handoff a F2

Cuando las 3 tareas terminen:

1. Ejecutor pushea y notifica al revisor.
2. Revisor audita en ≤10 min:
   - Existe `r3_idempotency_kill_retry_*.md` con conteos comparados.
   - Existe `r_x2_cache_*.json` con warm p95.
   - `pytest -m "not integration"` verde.
   - SEGUIMIENTO §Tablero refleja R3 + R-X2 cerradas.
3. Revisor confirma: **GO a F2.**
4. Sesión 20 abre con `docs/plan-f2.md` + ADR-0012.

---

## 7 · Si algo no cumple

- **R3 falla** (conteos no cuadran): aplicar el patrón atomic-move en `dump_to_cloud.py` (sección 3 "Si R3 falla"), volver a probar, ADR-0013 si el cambio es estructural.
- **R-X2 no llega a <500ms en warm:** revisar que el cache se está poblando (logs de structlog cache_hit / cache_miss). Si el problema es la pasada cold, evaluar precalentar cache al startup con los top-100 SKUs (mejora futura).
- **Algún test rompe:** investigar antes de mergear; no marcar Sesión 19 como cerrada hasta resolver.

---

## 8 · Referencias

- Recomendación humana original: Sesión 18 (chat 2026-05-28).
- Plan F1 + cierres previos: [`plan-f1.md`](plan-f1.md), [`plan-f1-fix1.md`](plan-f1-fix1.md), [`plan-f1-fix2.md`](plan-f1-fix2.md).
- Snapshot del proyecto: [`contexto-proyecto.md`](contexto-proyecto.md).
- Deudas R3 y R-X2: [SEGUIMIENTO §Tablero de riesgos vivos](../SEGUIMIENTO.md#tablero-de-riesgos-vivos).
- Cache library elegida: [`cachetools`](https://cachetools.readthedocs.io/) (consistente con stack actual, sin dep externa pesada).
