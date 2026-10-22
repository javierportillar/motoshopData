# Revisión post-handoff (MotoShop y MasVital)

Checklist que corro **después** de que cada máquina reporte. Si un ítem falla, no se habilita la
conciliación en esa empresa.

## A. Código y configuración

- [ ] La rama desplegada contiene `matching.py`, `repo.py` y los endpoints `movements` /
      `sync-status` / `reconciliation/{id}/apply` (`GET /api/erp/bank/sync-status` responde 200, no
      500 de política de módulos).
- [ ] `tenants.yaml` del tenant tiene `bank-reconciliation` en `enabled_features` y `erp.enabled: true`.
- [ ] `BANK_TENANT` de la máquina coincide con el tenant del request; un proceso sirve **un** tenant.
- [ ] `BANK_CREDENTIAL_ENTRY` es `bancolombia-<tenant>` y **no** comparte entrada con la otra empresa.
- [ ] `BANK_ACCOUNT_LABEL` es la etiqueta de la cuenta de **esa** empresa (no la del otro tenant).

## B. Persistencia

- [ ] `app_migration_state` tiene `F9-001` a `F9-004` en **cada** base donde corre una API con la
      feature habilitada (son bases distintas: la de MotoShop y la de MasVital).
- [ ] La segunda corrida del runner es no-op (idempotencia del runner).
- [ ] Existen `app_bank_movements` y `app_bank_verification_jobs`, y `app_writer` tiene
      SELECT/INSERT/UPDATE sobre ambas.
- [ ] Hay respaldo de la base previo a la migración.

## C. Forma de pago (el punto que puede bloquear)

- [ ] El `codpag` configurado existe en `formapago` **de esa empresa**:
      `SELECT codpag FROM formapago WHERE codpag = '<valor configurado>';` devuelve una fila.
- [ ] El código corresponde a transferencia/consignación bancaria, confirmado por el negocio (no
      inferido del nombre).
- [ ] Sin `codpag`, `POST /apply` responde **409 `codpag_no_confirmado`** y el movimiento queda
      `PENDIENTE` (fail-closed). Si en cambio postea algo, el deploy está mal.

## D. Aislamiento entre empresas

- [ ] `GET /api/erp/bank/movements` con `X-Tenant: motoshop` no devuelve ningún movimiento de
      MasVital, y viceversa.
- [ ] Un `POST /apply` con un `id` de movimiento del otro tenant responde **404
      `movimiento_no_encontrado`**.
- [ ] La clave de idempotencia es `uuid5(tenant:id_externo)`: el mismo `id_externo` en dos empresas
      produce claves distintas.
- [ ] `empresa` del asiento es la del tenant (`tenant.erp.empresa`), no vacía.

## E. Pruebas

- [ ] `cd motoshop-app/api && uv run pytest tests/ -q -k "not integration"` → 1178 passed; las 7
      fallas de `tests/test_reports.py` son preexistentes en `main`.
- [ ] `uv run ruff check` sin violaciones nuevas.
- [ ] `cd frontfambus && npx vitest run` → 393 passed; `npm run typecheck` limpio.
- [ ] `npx playwright install chromium` instalado y `npx playwright test tests/banco-verificar.spec.ts
      tests/banco-transferencias.spec.ts` en verde (pendiente en este entorno).

## F. Cierre

- [ ] `tasks.md`: checkpoints `3.4` (ADR-0026 `Accepted`) y `4.2` (migraciones) marcados por el
      operador, no por el agente.
- [ ] Una aplicación real de punta a punta por empresa, con un movimiento conocido, verificando que
      el documento generado tenga la **fecha del movimiento** (no la de hoy) y el `codpag` correcto.
