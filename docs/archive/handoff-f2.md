# Handoff F2 · Silver + PWA MVP

> Si acabás de llegar para trabajar la Fase 2, empezá por este archivo. Te evita releer todo el histórico y te deja claro qué ya está cerrado, qué está listo para construir y cómo mover los notebooks de Databricks sin depender de una UI caprichosa.

---

## 1 · Contexto rápido

- **F1 ✅** está cerrada.
- **F1.5 ✅** también está cerrada: R3 validada con kill-y-retry y R-X2 validada con caché real.
- **F2 🟡** es el siguiente frente: Silver + PWA MVP.
- El repo vive en `main` y los docs de arranque están en [`docs/plan-f2.md`](plan-f2.md) y [`docs/decisions/0012-stack-f2.md`](decisions/0012-stack-f2.md).

---

## 2 · Lo más importante para Databricks

Los notebooks de Databricks viven en el Git folder:

`/Repos/javierportillar/motoshopData`

### Regla operativa

- Si el notebook ya cambió en `main` y la UI no muestra un Pull claro, **sincronizá el notebook por API al path del Git folder** antes de relanzar el job.
- No dependas de la memoria de la UI; el notebook remoto tiene que quedar alineado con el último commit útil.
- Si la UI sí te muestra Pull, usalo; si no, el fallback por API es válido y esperado.

### Qué debe quedar sincronizado

- `notebooks/bronze/04_check_large_tables.py`
- `notebooks/bronze/02_ingest_all_bronze.py`
- `notebooks/bronze/03_validate_counts.py`
- cualquier notebook nuevo de Silver o validación de F2

---

## 3 · Pre-flight mínimo

1. Confirmar que `main` ya tiene el cambio que querés correr.
2. Confirmar que el notebook en Databricks apunta al Git folder correcto.
3. Confirmar que la fecha de ingesta o de validación coincide con la evidencia que querés producir.
4. Confirmar que no estás corriendo una validación antes de los datos.

---

## 4 · F2-A primero

Arrancá por Silver, no por la PWA.

- Materializar hechos y dimensiones.
- Poner reglas de calidad.
- Dejar evidencia legible en `_runs/`.

Después pasás a login/búsqueda/stock en la PWA.

---

## 5 · Política de trabajo

- No inventes stack nuevo sin ADR.
- No mezcles F2-A y F2-B en el mismo commit salvo que el cambio sea mínimo y realmente inseparable.
- Si un notebook de Databricks queda desalineado con GitHub, corregilo antes de ejecutar el job.
- Si un control falla, documentalo en vez de esconderlo.

---

## 6 · Qué leer en este orden

1. [`docs/contexto-proyecto.md`](contexto-proyecto.md)
2. [`SEGUIMIENTO.md`](../SEGUIMIENTO.md)
3. [`docs/plan-f2.md`](plan-f2.md)
4. [`docs/decisions/0012-stack-f2.md`](decisions/0012-stack-f2.md)

---

## 7 · Cierre sano

Cuando F2-A o F2-B quede hecho, no te olvides de:

- actualizar `SEGUIMIENTO.md`,
- dejar evidencia en `_runs/`,
- y empujar el commit a `main`.

