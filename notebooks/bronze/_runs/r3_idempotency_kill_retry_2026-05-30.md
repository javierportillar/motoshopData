# R3 · Idempotencia kill-y-retry — 2026-05-30

> **Plantilla pendiente de rellenar.** Ejecutar el test en la PC Windows siguiendo los pasos de `docs/plan-f1-hardening.md §3`.

## Setup
- Fecha de prueba: 2026-05-30 (distinta a corridas normales)
- Tablas ya subidas al Volume antes del kill: [PENDIENTE] / 12
- Parquets locales presentes tras kill: [PENDIENTE]

## Run 1 (matado)
- Duración hasta kill: [PENDIENTE]s
- Tablas completadas: [PENDIENTE] / 12
- Última tabla en proceso: terceros (truncado o incompleto)

## Run 2 (retry)
- Duración: [PENDIENTE]s
- Tablas completadas: 12 / 12

## Conteos finales (bronze vs MySQL)
| Tabla | Bronze | MySQL | Diferencia |
|-------|--------|-------|------------|
| facventas | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| detfventas | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| productos | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| auxinventario | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| bodegas | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| terceros | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| compras | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| detcompras | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| sucursales | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| formapago | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| subproduct | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| preciosxpro | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |

## Veredicto
⏳ PENDIENTE — Ejecutar test en PC Windows.

## Trade-off documentado
INSERT REPLACE WHERE en el notebook 02 sobreescribe la partición del día completa
en cada corrida exitosa. El estado intermedio (entre Run 1 matado y Run 2 completo)
no se ingesta a Bronze hasta el notebook 02. Por tanto, el riesgo se limita a
Parquets parciales en el UC Volume entre runs, lo cual el siguiente upload reemplaza
con overwrite=True.

---
*Generado automáticamente por el agente. Rellenar valores reales tras ejecutar el test.*
