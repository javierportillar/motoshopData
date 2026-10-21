# Onboarding DIAN (facturación electrónica)

Estado: **el código está listo; falta la cuenta del proveedor tecnológico.**
Sin cuenta, el ERP se comporta como el Hermes de escritorio: el documento
queda en cola (`PENDING`), el CUFE vacío y el documento **editable**; en
cuanto el proveedor lo acepta (`estfele` 1/2) el documento queda bloqueado.

## 1. Contratar el proveedor

El Hermes legacy usaba uno de estos (ver `docs/hermes/modules.md` §14):

| Proveedor | Endpoints (los que usaba el legacy) |
|---|---|
| **Dataico** (recomendado) | `https://api.dataico.com/direct/dataico_api/v2` → `invoices`, `credit_notes`, `support_docs`, `reception_events`, `payroll-api/payroll-entries` |
| **SoftProp Latam** (host propio) | `http://84.247.183.77` / `http://194.163.144.234` (el legacy usaba HTTP plano: **no Recommended**) |

Dataico pide: NIT, RUT, certificado de facturación electrónica y token +
client key/secret. SoftProp: cuenta y URL base.

## 2. Configurar el entorno

En `motoshop-app/api/.env` (NO en el `.env` raíz: ese es el usuario de solo
lectura `analytics`):

```env
DIAN_PROVIDER=dataico
DIAN_API_BASE=https://api.dataico.com/direct/dataico_api/v2
DIAN_API_TOKEN=...
DIAN_API_KEY=...
DIAN_API_SECRET=...
DIAN_TIMEOUT_SECONDS=30
```

Sin esas variables, el sistema usa el **stub** y todo lo demás funciona
igual (ventas, caja, anulación). Para volver al stub: `DIAN_PROVIDER=stub`.

## 3. Configurar el lado legacy (`sgHermes`)

- `provetecno` — proveedor tecnológico por empresa.
- `formapago.codfele` — las formas de pago que emiten documento electrónico.
- `contadores.envfele = 'S'` — la ventana de numeración de los documentos
  electrónicos (mismo criterio que `envfele` en el legacy).

## 4. Verificar

```powershell
cd motoshop-app\api
.\.venv\Scripts\python.exe -m pytest tests\test_erp_dian_settings.py -q
```

Después de configurar, una factura de prueba debe devolver `cocufe` +
`qrcode` en `respdocfele` y el QR oficial
`https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=<CUFE>`.

## 5. Lo que falta de este entregable

- El payload exacto de cada familia de documento al proveedor: el legacy
  construía el XML/JSON de la DIAN (`WADataico/CreaDoc1-5`,
  `WASofPropLat/Dc1-2/SofP_CreaLatam1-2`). Los adapters actuales envían el
  documento del ERP; hay que mapearlo al esquema que exija el proveedor.
- Reintentos con backoff ya están en la cola (`BACKOFF_DELAYS`).
