# Cierre definitivo — verificación bancaria en dos modos

Fecha: 2026-10-26. Nodo: SERVER (`MotoShopBackendSvc`, `:8000`, `BANK_DISPATCH_MODE=local`).

## Checklist

| # | Ítem | Evidencia |
|---|------|-----------|
| 1 | `mysql.user` sin `admin` | Se dropearon `admin@%`, `admin@localhost` y `admin@127.0.0.1` (eran nuestros y no los usaba nadie). Quedan `root@%`, `root@127.0.0.1`, `root@localhost`, `root@production` **intactos** y `analytics`, `api_read`, `app_writer`, `javier` en `localhost` |
| 2 | ERP: `servidor.txt` revertido, sin reinicio | Copia de VirtualStore restaurada byte a byte desde el backup (71 bytes, sha256 `816b727a…`): `26.47.101.42` / `root` / clave vacía / `3306` / `motoshop2024` / `MySQL ODBC 5.1 Driver`. El original apunta a la **IP pública**, no a `localhost`. SgHermes **no** se reinició (orden del operador) y sigue con la sesión de KAROL como `root@SERVER` |
| 3 | Sitio sirve el front nuevo | Chunk desplegado `6597-…js` con `nombre_esperado`, `nitter`, `"pago"` y sin `POS-`; POST real por `https://app.fragloesja.uk/api/erp/bank/verificaciones` → 202 |
| 4 | API que sirve producción | El primario `api.fragloesja.uk` (Render) da **503**; el tráfico cae al fallback `motoshop-local.fragloesja.uk` → esta PC. `/openapi.json` por el túnel: `required=["valor"]`, props `modo,factura_id,valor,nitter,nombre_esperado`, `additionalProperties=false` |
| 5 | a–e con arnés corregido (35 s entre casos) | Ver tabla |
| 6 | Punto de entrada publicado en el bus | `0443-motoshop-20261026T2130Z.md` |
| 7 | Guardián restringido + arnés con pausa | `infra/guardian-bus.ps1`: rebase sólo en `bus/banco-handoff`, `merge --ff-only` en main/rama, sin force-push; `infra/pruebas_produccion.py` con `time.sleep(35)` entre casos |
| 8 | Runbook con failover | `docs/runbook-banco.md` sección 9 |

## Pruebas a–e (2026-10-26 16:31, código de `main`)

| Caso | Qué prueba | job_id | Estado | Duración |
|------|-----------|--------|--------|----------|
| a | Modo factura, camino feliz | `3384c3df-4dc1-4e98-880d-465e89e44f29` | `resuelto` | 34.2 s |
| b | Doble clic → misma verificación | `ff0e180a-e541-4598-8355-d7dc6e73d49a` (los dos POST) | `resuelto` | 36.1 s |
| c | Reintento → job nuevo | `282f19a3-07fb-4ece-bf24-572b3878426d` | `resuelto` | 28.1 s |
| d | Nada aplicado | movimiento `7171000c` | `PENDIENTE`, 0 `APLICADO`, total 197011.28 | — |
| e | Modo pago sin match | `d4c612c3-9e43-49a4-a8bb-59f3cb201cc7` | `sin_coincidencia` | 28.1 s |

Caso (a): pagador `VALERIA CASTR`, valor `115000.00`, ref `0092405445`, 4 movimientos, 1 candidato,
`cliente_nombre=CONSUMIDOR FINAL`, sin `nitter`. `qr_duplicado`: ninguno. `errores`: ninguno.

## Punto de entrada (para el failover)

```
navegador → app.fragloesja.uk (Vercel) → /api/[...path] (route handler)
          → PRIMARY  api.fragloesja.uk → CNAME motoshop-cloud-api.onrender.com (Render, hoy 503)
          → FALLBACK motoshop-local.fragloesja.uk (túnel cloudflared de esta PC → :8000)
                     masvital-local.fragloesja.uk (túnel de MasVital, /health 200, sin la cuenta de motoshop)
                     local-api.fragloesja.uk (no resuelve)
```

Prueba de punta a punta: job `8142871b-3aed-417e-9059-e6ad78ba8d97` creado por el proxy de Vercel
(IP 54.221.182.4) y resuelto en 28.9 s en el nodo `motoshop`. Producción corre por el fallback.

## Bloque credenciales: cerrado sin cambios

Decisión del operador del 2026-10-26: el 3306 queda abierto y `root` remoto intacto (es el canal de
los devs de Hermes). La etapa de bind a `127.0.0.1` + `DROP root@%` quedó **CANCELADA** en el runbook
(8.3). Único cambio neto del día: se eliminaron los usuarios `admin` que habíamos creado y se revirtió
el `servidor.txt` del ERP. Ver `docs/runbook-banco.md` 8.3, 8.4 y 9.4.

## Contador de QR duplicados: control positivo

`logs/api_uvicorn.log` no sirve para auditar el 2026-10-22: arranca ese día a las 23:41 y no tiene
líneas `qr_duplicado`. Control positivo con fixture propio (4 líneas, 3 pares únicos): el script
devuelve **3 pares** y la línea repetida cuenta una sola vez. `--desde/--hasta` filtra bien.

## Suite

`281 passed, 19 skipped` (300 seleccionados con `-k bank`) en esta PC. El `290/10` no es
reproducible acá: los 10 tests `@pytest.mark.integration` necesitan `app_bank_account_locks` y
`app_bank_nodes`, que **no existen** en `motoshop2024` ni en `masvital`; con `BANK_TEST_MYSQL=1` dan
9 errores, no skips.

## Pendiente

1. **Primario Render en 503**: mientras siga así, el POS depende del túnel de esta PC.
2. **`app_bank_account_locks` y `app_bank_nodes` no existen** en el esquema de `motoshop2024`: el DDL
   del plano de control nunca se aplicó. Hoy no hay doble scrape sólo porque un único nodo tiene la
   sesión del banco; **antes** de darle la cuenta a MasVital hay que crear esas tablas.
3. **Cuenta de motoshop enrolada en la PC de MasVital**: sin eso, si esta PC se apaga no hay
   verificación.
4. **Afinidad de nodo en el front**: commit `a223013` en `frontfambus` (el 202 una vez más devuelve el
   nodo que tomó el job; los GET de ese job van a ese nodo y `job_no_encontrado` se reintenta 3
   veces). Pendiente de revisión y push.
5. **Firma del contrato de MasVital**: no respondió al 0423.

## SHAs

- Backend `main`: `12c5060` (`8d9d30a` + docs del cierre de credenciales).
- Front `main`: `a300201` publicado; `a223013` local, sin push.
- Bus: `0464-motoshop-20261026T2228Z.md` (corrección del lock por cuenta).
- Runbook: 8.3 cancelado, 8.4 `servidor.txt`, 9.3 lock corregido. Guardián: `infra/guardian-bus.ps1`.
