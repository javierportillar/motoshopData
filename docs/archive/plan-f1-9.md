# Plan F1.9 · Robustez del pipeline pre-F2

> Sprint corto **proactivo** entre F1 y F2. Origen: humano reportó 2026-05-29 que la PC MotoShop a veces está apagada o sin internet por días en su ubicación, y que el horario de cierre del negocio puede cambiar. El pipeline actual (Task Scheduler 3x/día con fechas técnicas) hereda esos riesgos a Silver. Se ataca antes de F2.
>
> Tiempo estimado: **~3 horas ejecutor + ~45 min revisor**. Después: GO a F2.

---

## 1 · Origen y decisiones humanas tomadas

### 1.1 Origen

Tras revisar `docs/contexto-proyecto.md`, el humano señaló:
- **PC apagado en ventana de dump:** Task Scheduler 02:00 / 12:00 / 20:00 falla si el PC está apagado a esa hora. Queda hueco en la partición del día.
- **Sin internet por días:** la ubicación a veces queda offline; el dump no puede subir al UC Volume.
- **Horario operativo cambia:** las 02:00 era "after close" hoy, pero si abren 24h o cambian, deja de ser anchor válido.
- **`ingest_date` ≠ `business_date`:** los datos del día N pueden quedar etiquetados con `ingest_date = N+M` si el dump corre tarde, perdiendo trazabilidad histórica.

### 1.2 Decisiones humanas (Sesión 21)

| Decisión | Valor |
|----------|-------|
| Frecuencia del dump | **Cada 30 min** |
| Ventana operativa | **07:00 – 19:30** (padding de 30 min a cada lado del horario de tienda 07:30–19:00) |
| Cómo encarar el ADR de fechas | **Camino 1**: revisor escribe ADR-0013 con las 3 opciones DESPUÉS del sondeo, humano aprueba leyéndolo |
| ¿Implementar `business_date` en F1.9? | **No** (depende del ADR; si elige opción C, va en F2-A) |

---

## 2 · Las 5 tareas

### Tarea 0 · Sondeo de columnas de fecha en BD *(ejecutor, ~20 min)*

**Por qué:** el ADR-0013 necesita info real sobre qué columnas de fecha existen en cada una de las 12 tablas core. `infollm.md` solo menciona `fecdoc` como "columna común" pero no documenta cada tabla. Sin sondeo, el ADR sería teoría sobre asunciones.

**Pre-requisitos:** usuario `api_read` accesible desde PC MotoShop.

**Archivos a crear:**

| Path | Rol |
|------|-----|
| `infra/explore_business_dates.py` | Script de introspección read-only |
| `notebooks/bronze/_runs/business_date_survey_2026-05-29.md` | Evidencia del sondeo |

**Implementación sugerida (`infra/explore_business_dates.py`):**

```python
"""Sondeo read-only de columnas de fecha en las 12 tablas core."""
from __future__ import annotations

import os
import pathlib
import re

import mysql.connector
from dotenv import load_dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

TABLES_CORE = [
    "facventas", "detfventas", "productos", "auxinventario", "bodegas",
    "terceros", "compras", "detcompras", "sucursales", "formapago",
    "subproduct", "preciosxpro",
]

DATE_HINT = re.compile(r"(fec|fch|date|fech)", re.IGNORECASE)


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "motoshop2024"),
        charset="utf8",
    )
    c = conn.cursor()

    print(f"# Sondeo de columnas de fecha — {pathlib.Path(__file__).name}\n")
    print(f"BD: {os.getenv('MYSQL_DATABASE')}  · usuario: {os.getenv('MYSQL_USER')}\n")

    for table in TABLES_CORE:
        print(f"\n## {table}")
        # Columnas y tipos
        c.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (os.getenv("MYSQL_DATABASE"), table),
        )
        cols = c.fetchall()
        # Filtrar candidatas
        candidatas = [
            (name, dtype, null)
            for (name, dtype, null) in cols
            if DATE_HINT.search(name) or dtype in ("date", "datetime", "timestamp")
        ]
        if not candidatas:
            print(f"  · sin columnas candidatas a fecha")
            continue

        print(f"  · columnas candidatas: {len(candidatas)}")
        for name, dtype, null in candidatas:
            print(f"    - `{name}` ({dtype}, nullable={null})")
            # Stats rápidas
            try:
                c.execute(
                    f"SELECT MIN(`{name}`), MAX(`{name}`), "
                    f"SUM(CASE WHEN `{name}` IS NULL THEN 1 ELSE 0 END) AS nulls, "
                    f"SUM(CASE WHEN CAST(`{name}` AS CHAR) LIKE '0000-%' THEN 1 ELSE 0 END) AS zeros, "
                    f"COUNT(*) AS total "
                    f"FROM `{table}`"
                )
                mn, mx, nulls, zeros, total = c.fetchone()
                print(f"      MIN={mn} · MAX={mx} · NULLs={nulls} · `0000-*`={zeros} · TOTAL={total}")
            except Exception as e:
                print(f"      (stats error: {e})")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Pasos del ejecutor:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1

# El script imprime a stdout; capturamos a archivo.
python infra\explore_business_dates.py | Tee-Object -FilePath notebooks\bronze\_runs\business_date_survey_2026-05-29.md
```

**Acceptance criteria:**
- El archivo `_runs/business_date_survey_2026-05-29.md` existe y muestra para cada una de las 12 tablas:
  - Lista de columnas candidatas a fecha.
  - Stats (MIN, MAX, NULLs, '0000-*', TOTAL) por candidata.
- Notas opcionales del ejecutor al final del archivo si encuentra algo raro (ej. "facventas tiene fecdoc y fecven, son distintas").

---

### Tarea 1 · Lag monitor + endpoint `/health/data-freshness` *(ejecutor, ~1 h)*

**Por qué:** sin alerta visible, "datos viejos por 3 días" pasa desapercibido y la PWA muestra info caduca sin saberlo. La regla #3 (cifras cuadran con sgHermes) se rompe silenciosamente.

**Archivos a crear:**

| Path | Rol |
|------|-----|
| `notebooks/bronze/06_pipeline_health.py` | Notebook que mide lag desde último manifest |
| `motoshop-app/api/src/motoshop_api/health/__init__.py` | módulo |
| `motoshop-app/api/src/motoshop_api/health/router.py` | endpoint `GET /health/data-freshness` |
| `motoshop-app/api/tests/test_health_freshness.py` | test del endpoint |
| Modificar `motoshop-app/api/src/motoshop_api/main.py` | wire-up del nuevo router |

**Implementación · Notebook (`06_pipeline_health.py`):**

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Pipeline Health
# MAGIC Mide lag desde el último manifest subido al UC Volume y emite verdict.

# COMMAND ----------
import json
from datetime import datetime, timezone

VOLUME = "/Volumes/motoshop/bronze/_landing/_manifests"

manifests = dbutils.fs.ls(VOLUME)
latest = max(manifests, key=lambda f: f.modificationTime)
latest_ts = datetime.fromtimestamp(latest.modificationTime / 1000, tz=timezone.utc)
lag_seconds = (datetime.now(tz=timezone.utc) - latest_ts).total_seconds()

print(f"Último manifest: {latest.name} @ {latest_ts.isoformat()}")
print(f"Lag actual: {lag_seconds/3600:.2f} horas")

if lag_seconds < 2*3600:
    status = "OK"
elif lag_seconds < 6*3600:
    status = "WARN"
elif lag_seconds < 24*3600:
    status = "STALE"
else:
    status = "CRITICAL"

print(f"\nStatus: {status}")
```

**Implementación · API endpoint:**

```python
# motoshop-app/api/src/motoshop_api/health/router.py
"""Health + data freshness."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter

from motoshop_api.config import settings

router = APIRouter(tags=["meta"])


@router.get("/health/data-freshness")
def data_freshness() -> dict:
    """Devuelve lag desde el último manifest subido al UC Volume."""
    try:
        w = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)
        manifests = list(w.files.list_directory_contents(
            f"{settings.databricks_volume_path}/_manifests"
        ))
        if not manifests:
            return {"status": "CRITICAL", "lag_hours": None, "last_manifest": None}
        latest = max(manifests, key=lambda f: f.last_modified)
        latest_dt = datetime.fromtimestamp(latest.last_modified / 1000, tz=timezone.utc)
        lag_hours = (datetime.now(tz=timezone.utc) - latest_dt).total_seconds() / 3600
        if lag_hours < 2:
            status = "OK"
        elif lag_hours < 6:
            status = "WARN"
        elif lag_hours < 24:
            status = "STALE"
        else:
            status = "CRITICAL"
        return {
            "status": status,
            "lag_hours": round(lag_hours, 2),
            "last_manifest": latest.name,
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
```

> **Nota:** `databricks_host` y `databricks_token` deben estar disponibles en `settings`. Si no están, añadir a `config.py`.

**Wire-up en `main.py`:** importar y `app.include_router(health_router)`.

**Acceptance criteria:**
- Notebook `06_pipeline_health.py` se ejecuta en Databricks y reporta lag correcto.
- Endpoint `GET https://api.fragloesja.uk/health/data-freshness` devuelve JSON con `status`, `lag_hours`, `last_manifest`.
- Test unitario que mockea WorkspaceClient y valida los 4 status (OK / WARN / STALE / CRITICAL).
- Evidencia: `notebooks/api/_runs/data_freshness_check_2026-05-29.md` con: salida del notebook + curl del endpoint + status reportado.

---

### Tarea 2 · Task Scheduler robusto + catch-up *(ejecutor, ~45 min)*

**Por qué:** el schedule actual (3x/día con horas fijas) falla cuando PC apagado o sin internet. Cada 30 min en ventana operativa, con reintento + ejecución diferida + catch-up, da resiliencia.

**Archivos a modificar/crear:**

| Path | Cambio |
|------|--------|
| Task Scheduler (config Windows) | Cambiar trigger + agregar settings |
| `infra/dump_to_cloud.py` | Añadir flag `--catch-up` |
| `infra/run_dump.ps1` | Mejorar manejo de errores transitorios |

**Configuración Task Scheduler (Windows UI):**

1. **Trigger:**
   - Tipo: "Diariamente"
   - Hora de inicio: 07:00
   - Repetir cada: **30 minutos**
   - Duración: **12 horas 30 minutos** (cubre 07:00 → 19:30)

2. **Settings (Configuración):**
   - ✅ "Ejecutar la tarea lo antes posible si se omite un inicio programado"
   - ✅ "Si la tarea falla, reiniciar cada: 10 minutos, hasta 3 intentos"
   - ✅ "Detener la tarea si se ejecuta más de: 15 minutos"
   - ❌ "Iniciar la tarea solo si la red está disponible" — DEJAR DESACTIVADO (el catch-up lo maneja)

3. **Conditions:**
   - ❌ "Iniciar solo si la PC está inactiva" — DESACTIVADO
   - ✅ "Reactivar el equipo para ejecutar esta tarea"

**Implementación `--catch-up` en `dump_to_cloud.py`:**

Añadir un modo que:
- Antes de extraer desde MySQL, escanea `_staging/` buscando Parquets que no tengan su entrada correspondiente en el UC Volume (probablemente quedaron locales por falta de internet).
- Para cada Parquet local que falta arriba, lo sube con `overwrite=True` (idempotente).
- Después continúa con el dump normal.

```python
# Pseudocódigo a añadir en main():
if args.catch_up:
    log.info("Catch-up: revisando Parquets locales sin subir...")
    for table_dir in STAGING_DIR.iterdir():
        if not table_dir.is_dir():
            continue
        for date_dir in table_dir.iterdir():
            local_parquet = date_dir / "part-0.parquet"
            if local_parquet.exists():
                ingest_date_str = date_dir.name.replace("ingest_date=", "")
                try:
                    upload_to_volume(local_parquet, table_dir.name, ingest_date_str, cfg)
                    log.info(f"  catch-up upload OK: {table_dir.name}/{ingest_date_str}")
                except Exception as e:
                    log.warning(f"  catch-up upload FAIL: {table_dir.name}/{ingest_date_str}: {e}")
```

**Modificación de `run_dump.ps1`:** invocar siempre con `--catch-up` (es idempotente; si no hay nada pendiente, no hace nada).

**Test de robustez (humano puede ejecutar opcional):**

1. Apagar el módem 30 min en mitad de horario operativo.
2. Verificar que los Task Scheduler corren pero `dump_to_cloud.py` falla en `upload_to_volume` y deja Parquets locales.
3. Encender el módem.
4. Esperar al siguiente schedule (≤30 min).
5. Verificar que el catch-up subió los Parquets pendientes.

**Acceptance criteria:**
- Task Scheduler reconfigurado con los settings de arriba (captura: screenshot o `schtasks /query /tn "MotoShopDump" /v /fo LIST`).
- `dump_to_cloud.py --catch-up` funciona sin errores cuando no hay Parquets pendientes.
- Test de robustez ejecutado (opcional, si el humano puede); evidencia en `notebooks/bronze/_runs/catch_up_test_2026-05-29.md`.

---

### Tarea 3 · ADR-0013 con datos reales del sondeo *(revisor, ~30 min)*

**Por qué:** sin el sondeo, el ADR sería teoría. Con el sondeo, el ADR documenta:
- Qué tabla tiene qué columna de fecha.
- Calidad de esa columna (NULLs, '0000-*', rango).
- Recomendación opción A/B/C basada en evidencia real.

**Archivo a crear:**

| Path | Estado inicial |
|------|----------------|
| `docs/decisions/0013-fecha-tecnica-vs-negocio.md` | **Proposed** (humano aprueba después en Sesión 22) |

**Estructura del ADR (revisor llena con datos del sondeo):**

```markdown
# ADR-0013 · `ingest_date` (técnica) vs `business_date` (de negocio)

- **Estado:** Proposed
- **Fecha:** 2026-05-29
- **Bloquea:** F2-A (silver) y reportes históricos en F3
- **Decide:** Humano

## Contexto
[con resumen del problema observado + cita al survey]

## Hallazgos del sondeo (2026-05-29)
[tabla por tabla con columnas de fecha reales, basada en `_runs/business_date_survey_2026-05-29.md`]

| Tabla | Columnas de fecha encontradas | Calidad | Aplicable a business_date |
|-------|--------------------------------|---------|----------------------------|
| facventas | fecdoc | ... | Sí |
| productos | (ninguna fecha de operación) | — | No (dimensional) |
| ... |

## Opciones consideradas
### A · Status quo (solo ingest_date)
### B · Bronze con doble fecha
### C · Bronze simple, Silver con business_date *(recomendada)*

## Recomendación
[Basada en el sondeo: probablemente C, ajustada por particularidades]

## Consecuencias
```

**Acceptance criteria del revisor:**
- ADR escrito con datos REALES del sondeo.
- 3 opciones desarrolladas con pros/contras.
- Recomendación argumentada.
- Estado `Proposed`.
- Humano aprueba en Sesión 22 → ADR pasa a `Accepted`.

---

### Tarea 4 · Documentar R5 + sincronizar *(revisor, ~15 min)*

**Cambios:**

1. **SEGUIMIENTO §Tablero de riesgos vivos:** añadir R5.

   ```markdown
   | **R5 · Pipeline pre-internet-estable** | F1 (Sesión 21) | 🟡 Mitigada parcialmente con F1.9 | El PC MotoShop puede estar apagado o sin internet por días. Lag monitor + Task Scheduler con catch-up cubren el caso típico, pero downtime sostenido > 24 h se acumula sin alerta proactiva. | **Mitigaciones aplicadas (F1.9):** dump cada 30 min en ventana operativa; reintento Task Scheduler 10 min × 3; catch-up automático tras pérdida de internet; lag monitor con 4 status (OK/WARN/STALE/CRITICAL); endpoint /health/data-freshness expuesto. **Triggers de re-evaluación:** (a) lag > 24 h en producción real; (b) datos de Silver/Gold no cuadran con sgHermes por gap diario; (c) gerencia pide alerta proactiva por email/push. |
   ```

2. **SEGUIMIENTO §F1 KPIs:** añadir métrica nueva.

   ```markdown
   | Lag pipeline < 6 h | 95% del tiempo en horario operativo | Pendiente medición en producción (F2) | 🟡 |
   ```

3. **Nota de Sesión 22** (cuando se cierre F1.9): Hecho/Aprendido/Abierto/Próximo.

4. **`docs/contexto-proyecto.md`:** actualizar §10 con R5 + §15 frase resumen.

---

## 3 · Cierre y GO a F2

Cuando las 4 tareas (0-2 del ejecutor, 3-4 del revisor) cierren:

1. Ejecutor commitea con mensaje convencional.
2. Revisor audita en ≤15 min.
3. Humano lee ADR-0013 y aprueba o pide ajustes.
4. Si todo cumple: **GO definitivo a F2 · Silver + PWA MVP.**

---

## 4 · Lo que NO entra en F1.9

| Cosa | Por qué se difiere |
|------|---------------------|
| Implementación de `business_date` en silver | Va en F2-A (es ~5 líneas de cast cuando se cree silver, NO trabajo separado) |
| Streaming / CDC con bin-log MySQL | Overkill; F-E del roadmap |
| Replicación a BD cloud | F-F del roadmap |
| Auto-deploy (auto-pull + restart) | Decisión pendiente para F6 (sesión sobre CI/CD) |
| Webhook GitHub → PC para forzar pull | Overkill para 1 PC; Task Scheduler de Windows cubre |
| Notificación push/email por lag crítico | F6 (observabilidad); por ahora el endpoint /health/data-freshness es pull, no push |

---

## 5 · Calendario

```
Día 0 (hoy) — Sesión 21:
  Humano aprueba: cada 30 min, 07:00-19:30, Camino 1 ✓
  Revisor escribe este plan + PENDIENTES sesión 21 ✓
  Push.

Día 1 — Ejecutor (Sesión 22):
  Tarea 0 (sondeo)             → 20 min
  Tarea 1 (lag monitor + API)   → 1 h
  Tarea 2 (Task Scheduler)      → 45 min
  Push.

Día 1 — Revisor (continuación Sesión 22):
  Lee evidencia del sondeo.
  Escribe ADR-0013 (Proposed).
  Documenta R5 + sync SEGUIMIENTO/contexto.
  Push.

Día 1.5 — Humano:
  Lee ADR-0013 (5 min).
  Aprueba o pide ajustes.

Día 2 — Sesión 23:
  GO a F2 · Silver + PWA MVP.
  Revisor escribe docs/plan-f2.md + ADR-0014 (decisiones técnicas F2).
```

---

## 6 · Referencias

- Decisiones humanas: este chat 2026-05-29.
- Snapshot del proyecto: [`contexto-proyecto.md`](contexto-proyecto.md).
- Tablero de riesgos: [`SEGUIMIENTO.md`](../SEGUIMIENTO.md#tablero-de-riesgos-vivos).
- Plan anterior (hardening): [`plan-f1-hardening.md`](plan-f1-hardening.md).
