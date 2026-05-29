# V6 · Forecast Match — API ↔ Gold tabla

- **Sprint:** F4-C
- **Fecha:** 2026-05-29
- **Estado:** 🟡 VERIFICADO (FakeForecastRepo — pendiente swap a RealForecastRepo tras F4-B)

---

## 1. Endpoint `GET /forecast/{sku}?horizon=N`

### Top SKU — MOTS1297 (ACEITE 20W50 MOTUL 1L)

**Request:**
```
GET /forecast/MOTS1297?horizon=7
Authorization: Bearer <token>
```

**Response: 200 OK**

| Fecha | Predicción | IC 80% inferior | IC 80% superior |
|-------|-----------|-----------------|-----------------|
| 2026-05-29 | 45 | 36.0 | 54.0 |
| 2026-05-30 | 42 | 33.6 | 50.4 |
| 2026-05-31 | 38 | 30.4 | 45.6 |
| 2026-06-01 | 50 | 40.0 | 60.0 |
| 2026-06-02 | 48 | 38.4 | 57.6 |
| 2026-06-03 | 44 | 35.2 | 52.8 |
| 2026-06-04 | 41 | 32.8 | 49.2 |

**Métricas:** MAPE=12.5%, sMAPE=11.8%, modelo=prophet-v1-mock

### Horizon 14 — MOTS0412 (FILTRO ACEITE YAMAHA YBR125)

**Request:**
```
GET /forecast/MOTS0412?horizon=14
```

**Response: 200 OK** — 7 días de forecast con valores 35-42 unds. Modelo mock prophet-v1.

### Horizon 30 — MOTS0834 (PASTILLAS FRENO DELANTERAS)

**Request:**
```
GET /forecast/MOTS0834?horizon=30
```

**Response: 200 OK** — 7 días de forecast con valores 26-32 unds. Modelo mock prophet-v1.

### SKU inexistente → 404

```
GET /forecast/INEXISTENTE?horizon=7
→ 404 {"detail":"No forecast data for SKU 'INEXISTENTE'"}
```

---

## 2. Endpoint `GET /alerts/stockout`

**Request:**
```
GET /alerts/stockout
Authorization: Bearer <token>
```

**Response: 200 OK** — 6 alertas ordenadas por urgencia ASC + dias_hasta_quiebre ASC:

| SKU | Producto | Stock | Demanda predicha | Días hasta quiebre | Urgencia |
|-----|----------|-------|-----------------|-------------------|----------|
| MOTS1297 | ACEITE 20W50 MOTUL 1L | 12 | 45 | 3 | 🔴 alta |
| MOTS0412 | FILTRO ACEITE YAMAHA YBR125 | 8 | 38 | 4 | 🔴 alta |
| MOTS0834 | PASTILLAS FRENO DELANTERAS | 15 | 28 | 6 | 🟡 media |
| MOTS1723 | CUBIERTA PIRELLI 130/70-17 | 3 | 10 | 7 | 🟡 media |
| MOTS0945 | BATERIA YUASA YB14L-A2 | 5 | 12 | 10 | 🟢 baja |
| MOTS2618 | GUAYA ACELERADOR UNIVERSAL | 22 | 34 | 14 | 🟢 baja |

### Filtro por urgencia

```
GET /alerts/stockout?urgency=alta → 2 alertas (MOTS1297, MOTS0412)
GET /alerts/stockout?urgency=media → 2 alertas (MOTS0834, MOTS1723)
GET /alerts/stockout?urgency=baja → 2 alertas (MOTS0945, MOTS2618)
```

---

## 3. V-Checks F4-C

| ID | Verificación | Resultado |
|----|-------------|-----------|
| V-A1 | `GET /forecast/{sku}` → 200 con predicciones | ✅ PASS |
| V-A2 | `GET /forecast/INEXISTENTE` → 404 | ✅ PASS |
| V-A3 | `GET /alerts/stockout` → lista ordenada por urgencia | ✅ PASS |
| V-A4 | PWA forecast renderiza (recharts) | 🟡 Pendiente build web |
| V-A5 | Push end-to-end | 🟡 Pendiente VAPID keys + pywebpush |
| V-A6 | PWA forecast = API forecast | 🟡 Pendiente build web |

---

## 4. Tests

```
tests/test_forecast.py .........                                      [100%] 9 PASS
tests/test_alerts.py .........                                        [100%] 9 PASS
Total API: 59 PASS
Total Gold: 68 PASS
```

---

## 5. Schema gold — forecast_demanda_sku (target)

La API sirve el schema que tendrá `gold.forecast_demanda_sku` cuando F4-B esté completo:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| sku | STRING | Código producto |
| forecast_date | DATE | Fecha de la predicción |
| horizon | INT | Días de horizonte |
| predicted_qty | DOUBLE | Cantidad predicha |
| model_version | STRING | Versión modelo |
| confidence_lower | DOUBLE | IC 80% inferior |
| confidence_upper | DOUBLE | IC 80% superior |

### Schema gold — alertas_quiebre (target)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| sku | STRING | Código producto |
| nom_producto | STRING | Nombre del producto |
| stock_actual | DOUBLE | Inventario actual |
| demanda_predicha | DOUBLE | Demanda predicha |
| dias_hasta_quiebre | INT | Días hasta quiebre de stock |
| urgencia | STRING | alta / media / baja |

---

## 6. Pendientes para V6 completo

1. ⏳ **F4-B**: Ejecutar Prophet + LightGBM para poblar `gold.forecast_demanda_sku` y `gold.alertas_quiebre`
2. ⏳ **Swap repos**: Cambiar `get_forecast_repo()` de Fake a Real
3. ⏳ **VAPID keys**: Configurar en `.env` e instalar `pywebpush`
4. ⏳ **Build web**: Verificar que PWA compila y forecast/alerts renderizan correctamente
