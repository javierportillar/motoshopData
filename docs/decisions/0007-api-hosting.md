# ADR-0007 · Hosting de la API (P3)

- **Estado:** **Proposed** — bloquea F0 → F1
- **Fecha:** 2026-05-27
- **Bloquea:** F0 (entregable Track T · "FastAPI corriendo")
- **Decide:** Humano (responsable del proyecto)

## Contexto

La API necesita hablar con el MySQL `motoshop2024`. Hay dos lugares donde puede vivir.

## Opciones consideradas

### A · En el mismo PC, junto a MySQL *(recomendado por PLAN §4)*

- Servicio gestionado por `systemd`/`NSSM`/Windows Service.
- Túnel remoto expone el puerto 8000.
- **Pros:** latencia mínima a la BD (loopback); cero coste; simplicidad operativa; coherente con la decisión de "no tocar la fuente".
- **Contras:** la API depende de que el PC esté encendido; contiende por CPU/RAM con sgHermes; un crash del PC = caída total.

### B · VPS pequeño con túnel inverso al PC

- API en la nube; el PC abre un túnel saliente para que la API pueda leer el MySQL.
- **Pros:** la API sigue arriba aunque el PC se reinicie (los endpoints devolverán error de BD, pero el servicio responde); más cerca del modelo "producción".
- **Contras:** coste mensual; latencia red→PC→MySQL; un eslabón más que mantener; el túnel inverso es justamente lo que P2 quiere evitar.

## Recomendación

**Opción A — PC local.** Para F0–F4 es lo correcto: simple, gratis y alineado con que la fuente sigue siendo el PC. Si en F6 se valida que la operación pasa por la API y la disponibilidad importa, se revalúa moverla a un VPS o a una managed function que lea de la BD ya replicada (atado a F-F del roadmap).

## Consecuencias si se acepta A

- Hay que dejar la API como servicio (auto-arranque con el sistema).
- Hay que monitorear consumo de recursos del PC.
- El backup del PC (F0 verificación #6) cubre también la API.
- La caída del PC sigue siendo un riesgo aceptado documentado en `PLAN.md §12`.
