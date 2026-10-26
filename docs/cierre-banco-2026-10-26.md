# Cierre a producción — verificación bancaria en dos modos

Fecha: 2026-10-26. Nodo: SERVER (`MotoShopBackendSvc`, `:8000`, modo `local`).

## 1. Checklist con evidencia

| # | Ítem | Estado | Evidencia |
|---|------|--------|-----------|
| 1 | Contrato en dos modos (`factura` / `pago`) | OK | `POST /api/erp/bank/verificaciones` → 202; OpenAPI con `modo/factura_id/valor/nitter/nombre_esperado`, `required=["valor"]`, `additionalProperties=false` |
| 2 | `modo=pago` exige `valor` y prohíbe `factura_id` | OK | Job `2e3c7132-76e4-4c7b-9e9a-2aa600921b66`: 202 → `resuelto` en 28.1 s |
| 3 | NIT comodín no viaja y se etiqueta consumidor final | OK | Mismo job: `nitter_presente=false`, `cliente="CONSUMIDOR FINAL"`; test `test_worker_etiqueta_consumidor_final_sin_nit` |
| 4 | La verificación nunca aplica nada | OK | Movimiento `7171000c` (ref `0092405445`) sigue `PENDIENTE`; total del día sin cambios por la verificación |
| 5 | Front en `main` con el modo pago | OK | `frontfambus` `main` = `a300201` (origin); ya no manda `facturaId: POS-<timestamp>` |
| 6 | Front: tests, typecheck y lint | OK | 63 archivos / 399 tests verdes; `tsc --noEmit` sin salida; eslint sólo warnings previos |
| 7 | Backend mergeado a `main` | OK | `motoshopData` `main` = `b997113` (origin). El `--no-ff` `90dccec` lo aplanó el guardián con un `pull --rebase`; el árbol es idéntico |
| 8 | Suite bancaria sobre `main` | OK | `281 passed, 19 skipped, 986 deselected` (`uv run --with pytest --with pytest-cov python -m pytest tests/ -q -k bank`) |
| 9 | Pruebas de producción a–e | OK | Corrida completa 14:56 (`prod_tests_out.json`) + caso (a) re-confirmado sobre `main` a las 15:33 |
| 10 | Cero ventanas visibles | OK | Sólo el Chrome del operador (WhatsApp Business); 2 procesos `python` sin ventana |
| 11 | Migraciones aplicadas | OK (esta PC) | F9-007 y F10-004 en `motoshop2024`; el barrido dejó de fallar (último error 15:04:54) |
| 12 | Runbook con cola y firewall | OK | `docs/runbook-banco.md` sección 8 |
| 13 | Firewall exportado antes de tocar | OK | `infra/firewall/firewall-20261026-1515.wfw` + perfiles; ninguna regla modificada |
| 14 | MySQL: usuario de aplicación | OK | `admin@localhost` y `admin@%`, `ALL` sobre `motoshop2024`/`motoshop`/`capacitacion` |
| 15 | ERP apuntando a `admin@127.0.0.1` | OK (falta reiniciar) | `servidor.txt` reescrito; ODBC 32-bit: `facturas=7347`, `terceros=166` |
| 16 | MySQL: bind local + limpieza de `root` | BLOQUEADO | `CU19881` (`26.216.80.104`) sigue conectado como `root@%` a `motoshop2024` |
| 17 | Aviso y firma del contrato en el bus | OK / sin respuesta | `0423-motoshop-20261026T2015Z.md`; sin respuesta a las 20:27Z, se siguió igual |

## 2. Pruebas a–e (corrida completa, 2026-10-26 14:56)

| Caso | Qué prueba | Resultado |
|------|-----------|-----------|
| a | Modo factura, camino feliz | `resuelto` 28.1 s, `VALERIA CASTR`, `115000.00`, ref `0092405445`, 4 movimientos, 1 candidato |
| b | Dos POST seguidos, misma verificación | Mismo `job_id` en las dos respuestas, `resuelto` 28.1 s |
| c | POST nuevo sobre un job terminado | `job_id` nuevo, `resuelto` 28.1 s |
| d | No se aplica nada | Movimiento `7171000c` en `PENDIENTE`, cero `APLICADO` |
| e | Sin coincidencia | `sin_coincidencia` limpio en 28.5 s |

Re-confirmación sobre `main` (15:33): caso (a) → `2e3c7132-76e4-4c7b-9e9a-2aa600921b66`, `resuelto` 28.1 s,
`CONSUMIDOR FINAL`, sin `nitter`.

Nota de arnés: la corrida de las 15:30 sobre `main` hizo caer el caso (c) con `intervalo_minimo` porque
`prod_tests.py` no espera los 30 s entre casos. Es ritmo del arnés, no del contrato: el POST devuelve
202 y el job termina en `fallido` con ese código.

## 3. Estado operativo

- `BANK_DISPATCH_MODE=local` (el hilo corre dentro de la API).
- `.env` sin `BANK_WINDOW_START/END`: la ventana es el día en curso.
- Intervalo mínimo entre barridos: 30 s. Lock por cuenta en `app_bank_account_locks`.
- API reiniciada desde `main` a las 15:34:48, `/health` 200.

## 4. Pendiente y bloqueado

1. **MySQL bind y limpieza de `root`**: `CU19881` entra como `root@%`. Antes hay que migrarlo a
   `admin` (ya existe) y verificar el corte desde otra PC. Comandos y rollback en el runbook, 8.3.
2. **Reiniciar SgHermes** para que tome el `servidor.txt` nuevo (paso del operador, no hay GUI acá).
3. **Otra PC (ProDesk/MasVital)**: `pull` de `main`, aplicar F9-007/F10-004, reiniciar y re-correr a–e.
4. **Firma del contrato**: MasVital no respondió al 0423.

## 5. SHAs

- Backend `main`: `b997113` (merge `--no-ff` `90dccec` aplanado por el guardián; mismo árbol).
- Front `main`: `a300201`.
- Runbook: `e9c7bfe`. Firewall: `b997113`.
