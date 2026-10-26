# Cierre definitivo — verificación bancaria en dos modos

Fecha: 2026-10-26. Nodo: SERVER (`MotoShopBackendSvc`, `:8000`, `BANK_DISPATCH_MODE=local`).

## Checklist

| # | Ítem | Evidencia |
|---|------|-----------|
| 1 | `mysql.user` sin `admin@%` | Quedan `admin@localhost` y `admin@127.0.0.1`; `root@%`, `root@127.0.0.1`, `root@localhost`, `root@production` intactos; `analytics`, `api_read`, `app_writer`, `javier` en `localhost` |
| 2 | ERP: ODBC ok, reinicio pendiente | Cadena literal de `servidor.txt` por ODBC 32-bit: `current_user=admin@localhost`, `facturas=7348`, `terceros=166`; SgHermes sigue abierto con la sesión de KAROL (arrancó 08:14, antes del cambio) y conectado como `root@SERVER` |
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

## Pendiente

1. **Reiniciar SgHermes** (sesión de KAROL abierta): después del reinicio tiene que entrar como
   `admin@localhost` en lugar de `root`.
2. **Primario Render en 503**: mientras siga así, el POS depende del túnel de esta PC.
3. **Cuenta de motoshop enrollada en la PC de MasVital**: sin eso, si esta PC se apaga no hay
   verificación.
4. **Firma del contrato de MasVital**: no respondió al 0423.

## SHAs

- Backend `main`: `7d47150` (+ el commit de este cierre).
- Front `main`: `a300201`.
- Runbook sección 9: `docs/runbook-banco.md`. Guardián: `infra/guardian-bus.ps1`.
