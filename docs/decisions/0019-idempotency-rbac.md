# ADR-0019: Idempotency + RBAC para escrituras PWA → MySQL

**Status**: Proposed
**Date**: 2026-05-30
**Deciders**: Revisor + Dev A + Dev T
**Sprint**: F5 · Operación bidireccional

---

## Context

F5 abre el primer canal de escritura PWA → MySQL con tablas `app_*` en InnoDB
(ver ADR-0018, ADR-0004). La red del PC con MySQL es inestable (pre-internet-estable
según R5), y hay 3 roles de usuario con distintos permisos de negocio.

Se requieren dos mecanismos:
1. **Idempotency**: evitar duplicados cuando el cliente reintenta tras timeout o
   fallo de red (patrón kill-y-retry, validado en R3).
2. **RBAC**: asegurar que cada rol solo pueda ejecutar las acciones de negocio
   que le corresponden.

---

## Decision · Idempotency-key UUID v4 + UNIQUE constraint

**Decisión**: toda escritura en `app_alert_actions` requiere header HTTP
`Idempotency-Key` con un UUID v4 generado por el cliente. Se almacena en columna
`idempotency_key VARCHAR(64) NOT NULL UNIQUE`. Si el mismo key llega de nuevo,
el router devuelve el registro existente con HTTP 200 (no 201, no error).

**Implementación**:
- El `RealAlertActionsRepo.create_action()` hace un `SELECT` por `idempotency_key`
  antes de insertar; si existe, retorna el registro.
- Entre el `SELECT` y el `INSERT`, una `IntegrityError` de la UNIQUE constraint
  sirve como protección en caso de race condition.
- El router en `alerts/router.py` chequea antes de llamar al repo y retorna
  `Response(status_code=200, ...)` para replay, `Response(status_code=201, ...)`
  para creación.

**Alternativa descartada — Redis-based dedup**:
  - Usar Redis TTL para idempotency keys.
  - **Motivo de descarte**: Redis no está en el stack de producción (MySQL 5.0
    en PC local + Cloudflare Tunnel). Agregar Redis agrega latencia, una
    dependencia más, y un punto de fallo adicional. La UNIQUE constraint de
    InnoDB es suficiente para el volumen esperado (< 1k acciones/día).

**Alternativa descartada — idempotency server-side (auto-generated)**:
  - Generar un `request_id` en el servidor y usarlo como clave de idempotencia.
  - **Motivo de descarte**: el cliente no sabe qué key generó el servidor, así
    que no puede reintentar con el mismo identificador. Rompe el patrón
    kill-y-retry.

---

## Decision · RBAC por JWT claims, no en DB

**Decisión**: el rol del usuario viaja en el JWT claim `role` (`admin`/`gerente`/`vendedor`).
El endpoint `POST /alerts/{id}/action` usa `require_role("admin", "gerente")`
para autorizar. No hay tabla de permisos en DB.

**Implementación**:
- `users.yaml` ya tiene el campo `role`; se incluye en el JWT al hacer login.
- `require_role(*roles)` en `motoshop_api/auth/deps.py` ya existe y verifica
  contra el JWT decodificado.
- Si en el futuro se necesitan permisos granulares (ej. "vendedor puede pedir
  pero no descartar"), se migra a tabla `app_role_permissions`.

**Alternativa descartada — tabla `app_user_roles` con permisos finos**:
  - Modelar cada permiso como fila en DB.
  - **Motivo de descarte**: overkill para 3 roles fijos con ~2-3 acciones cada
    uno. La validación en middleware es más rápida, más simple y no requiere
    round-trip a DB.

---

## Consequences

### Positive
- Idempotency probada en R3 con kill-y-retry: 12 tablas con conteos exactos
  tras reintentos.
- Sin dependencias nuevas (no Redis, no tabla extra).
- RBAC en JWT → cero latency de autorización.
- Patrón replicable para F6+ (próximos canales de escritura).

### Negative
- Si el volumen crece (> 10k acciones/día), la tabla `app_alert_actions` puede
  necesitar particionamiento y el `SELECT ... WHERE idempotency_key = ?` puede
  necesitar índice dedicado (ya existe `uq_idempotency` como UNIQUE KEY).
- Sin tabla de permisos, cambiar políticas requiere deploy del backend (no es
  configurable en caliente).
- El rol viaja en el JWT; si se cambia el rol de un usuario, necesita
  re-login para obtener un nuevo token.

### Technical debt creada
- Si F7 introduce permisos granulares, migrar a tabla `app_role_permissions`.
- Idempotency key sin TTL de expiración → la UNIQUE KEY retiene keys
  indefinidamente. Para el volumen esperado no es problema, pero documentar
  como deuda (R-F5-5).

---

## Related artifacts

- [ADR-0018 Stack F5](0018-stack-f5.md) — decisiones marco del sprint
- [ADR-0004 Tablas app_* en InnoDB](0004-innodb-app-tables-f5.md) — materializado en F5
- [R3 Idempotency kill-y-retry](../notebooks/gold/_runs/r3_idempotency_kill_retry_2026-05-30.md)
- [Plan F5-FIX1](../plan-f5-fix1.md) — auditoría que motiva este ADR
