# ADR-0018: Stack técnico F5 · Operación bidireccional

**Status**: Proposed (a ratificar al cierre del sprint)
**Date**: 2026-05-30
**Deciders**: Revisor + Dev A + Dev T
**Sprint**: F5 · Operación bidireccional

---

## Context

Hasta F4 la PWA es solo lectura. F5 abre el primer canal de escritura PWA → MySQL con tablas `app_*` en InnoDB, manteniendo sgHermes intocable (ADR-0002). Una sola acción de negocio en F5 ("gestionar alerta de quiebre") para mantener scope acotado.

Se requiere definir 10 decisiones técnicas (DT-F5-1 a DT-F5-10) antes de implementar.

---

## Decisión técnica DT-F5-1 · Tablas `app_*` en InnoDB

**Decisión:** crear `app_alert_actions` y `app_audit_log` en MySQL con `ENGINE=InnoDB` + `utf8mb4`.

**Alternativa descartada:** MyISAM como el resto de sgHermes → no soporta transacciones ni FOREIGN KEYs.

**Rationale:** InnoDB da ACID para escrituras críticas; el costo en MySQL 5.0 es asumible para el volumen esperado (< 1k acciones/día).

---

## Decisión técnica DT-F5-2 · Idempotency-key obligatorio

**Decisión:** todas las escrituras requieren header `Idempotency-Key: <UUID v4>` generado por el cliente. UNIQUE constraint en DB. Replay de mismo key devuelve registro original con 200 (no 201, no error).

**Alternativa descartada:** server-generated ID + retry sin protección → riesgo de duplicar registros cuando red falla y cliente reintenta.

**Rationale:** patrón estándar (Stripe, Twilio) que cubre redes inestables y cliente offline.

---

## Decisión técnica DT-F5-3 · RBAC en JWT claims, no en DB

**Decisión:** JWT incluye claim `role` (`admin`/`gerente`/`vendedor`). Middleware `require_role(*roles)` verifica antes de procesar.

**Alternativa descartada:** tabla `app_user_roles` con permisos finos → overkill para 3 roles fijos.

**Rationale:** users.yaml ya tiene role; basta incluirlo en JWT. Si en F7 se necesitan permisos granulares, se migra a tabla.

---

## Decisión técnica DT-F5-4 · Audit trail dual (structlog + tabla)

**Decisión:** cada escritura genera (a) structlog event para Cloudflare logs y (b) insert en `app_audit_log` para audit trail persistente.

**Alternativa descartada:** solo structlog → logs se rotan; (b) solo tabla → si DB se cae, no hay registro de lo que se intentó.

**Rationale:** redundancia barata para auditoría.

---

## Decisión técnica DT-F5-5 · Offline queue con idb-keyval + retry exponencial

**Decisión:** PWA persiste acciones offline en IndexedDB store `pending-actions` con retry 1s → 5s → 30s → 5min → 30min → 6h (máx 6 intentos).

**Alternativa descartada:** Background Sync API → no soportado en Safari iOS (gran porcentaje de móviles del mercado).

**Rationale:** queue manual con setInterval + listener `online` event funciona en todos los browsers.

---

## Decisión técnica DT-F5-6 · Sin transacciones distribuidas

**Decisión:** F5 escribe solo a `app_*` (InnoDB local). NO toca sgHermes (MyISAM).

**Alternativa descartada:** XA / 2PC → no soportado en MySQL 5.0 + MyISAM no participa de transacciones.

**Rationale:** scope aislado; si después F6/F7 necesitan cross-engine, se implementa staging pattern (escribir a `app_staging_*` y job nocturno copia).

---

## Decisión técnica DT-F5-7 · Migration scripts SQL puros, idempotentes

**Decisión:** `infra/migrations/F5-XXX-*.sql` con `CREATE TABLE IF NOT EXISTS` + rollback documentado en comentario.

**Alternativa descartada:** Alembic o Liquibase → overkill para 3 archivos SQL.

**Rationale:** auditable + sin nueva dependencia + sin overhead de runtime.

---

## Decisión técnica DT-F5-8 · R14 cleanup como parte de F5

**Decisión:** archivar Prophet/LightGBM en mismo sprint. `git mv` a `docs/archive/infra/` y `docs/archive/notebooks-gold/`. Workflow gold ajustado para skip tasks. README explicativo.

**Alternativa descartada:** sprint dedicado F5.5-Hardening → fragmenta sin beneficio.

**Rationale:** scope F5 ya tiene cleanup natural; no vale un sprint aparte.

---

## Decisión técnica DT-F5-9 · Tests honestos

**Decisión:** unit (FakeRepos), integration (DB MySQL test real con rollback), E2E Playwright. Incluye offline simulation y idempotency replay.

**Alternativa descartada:** solo unit → no valida contrato real con DB.

**Rationale:** F4-C nos enseñó que cerrar con FakeRepos en prod es trampa (R12). E2E + integration son obligatorios.

---

## Decisión técnica DT-F5-10 · UI mobile-first minimalista

**Decisión:** modal con 3 tabs (Pedir/Descartar/Posponer), página "Mis acciones del día", sin charts. Tailwind raw, sin librerías nuevas.

**Alternativa descartada:** dashboards de acciones agregadas → diferido a F6.

**Rationale:** scope acotado; F6 puede agregar visualizaciones.

---

## Consequences

### Positive
- Primer canal de escritura PWA → MySQL probado end-to-end con patrón replicable.
- Audit trail desde día 1 → cumple gobernanza (Módulo 5 del curso).
- Idempotency previene duplicados de red.
- Offline queue da UX de "siempre disponible" sin conexión.
- R14 cleanup deja el pipeline limpio (solo baseline + classifier).

### Negative
- Nuevo usuario MySQL `app_writer` agrega superficie de auth (mitigable con password en `.env`).
- Patrón de retry puede acumular acciones obsoletas si API está caída por días (cap 100 items + warning UI).
- MySQL 5.0 puede tener limitaciones para JSON column type (fallback a TEXT documentado).

### Technical debt creada
- Tabla `app_audit_log` no particionada → crecimiento ilimitado (R-F5-6, F6).
- Sin lock optimista para concurrent writes en misma alerta (R-F5-4, F6 si negocio lo pide).
- Sin walk-forward de classifier (heredado F4).

---

## Related artifacts

- [Plan F5](../plan-f5.md)
- [ADR-0019 Idempotency + RBAC](0019-idempotency-y-rbac.md) (pendiente)
- [ADR-0002 Frontend solo lectura F1-F4](0002-frontend-read-only-f1-f4.md) — supersede parcial para F5+
- [ADR-0004 Tablas app_* en InnoDB cuando llegue F5](0004-innodb-app-tables-f5.md) — esta decisión materializa la D4
- [Lecciones aprendidas F4](../lecciones-aprendidas-f4.md) — input para R14 cleanup
