# F7-A · Dashboards Content Definition (Discovery)

- **Fecha:** 2026-05-30 (Sesión 50)
- **Status:** ✅ Approved (humano aprobó balde A + balde B + todos los grupos)
- **Total features:** 69 (20 + 18 + 17 + 14) + 1 design system + 4 dashboards nuevos
- **Cronograma:** 3-4 semanas implementación + ~30 días esperando snapshots = **defensa 6-8 semanas**

---

## 1 · Decisión de scope (humano confirmó)

**TODO en F7:** balde A (datos existentes) + balde B (infrastructure nueva: snapshots históricos).

**Trade-off aceptado:**
- Defensa se corre 6-8 semanas (vs 1-2 originales)
- Balde B requiere ~30 días de snapshots para tener data útil
- Hasta entonces dashboards históricos muestran "captura en marcha"

**Justificación:** mejor llegar a defensa con arquitectura completa + algunos datos parciales documentados que con app reducida.

---

## 2 · Inventario completo de features aprobados

### Grupo 1 · Dashboards COMERCIALES (20 features)

#### `/dashboards/ventas` (V1-V6)
- V1: Tendencia mensual REAL (últimos 6-12m, gráfico líneas) — endpoint nuevo `/metrics/sales-trend?periods=6`
- V2: Comparativa YoY (mayo 2026 vs mayo 2025) — cálculo sobre `fact_ventas`
- V3: Ventas por día de semana (heatmap o barras) — `DAYOFWEEK(business_date)`
- V4: Top categorías (no solo SKUs) — JOIN `dim_producto.cod_grupo`
- V5: Top 5 vendedores del mes — JOIN `fact_ventas.nit_vendedor` + `nombre_vendedor`
- V6: Hora pico de ventas (7-19h) — `HOUR(fecha_documento_ts)`

#### `/dashboards/inventario` (I1-I6)
- I1: Inventario por categoría/familia — JOIN `dim_producto.cod_grupo`
- I2: Inventario por proveedor — `fact_compras.nit_proveedor` agregable
- I3: **[BALDE B]** Rotación promedio (días en stock) — requiere serie temporal de `auxinventario`
- I4: Inventario muerto granular (>180d, >365d, >730d tiers) — `mart_productos_dormidos` con tiers
- I5: Valor inmovilizado en dormidos — `SUM(stock × costo) WHERE dias > 90`
- I6: **[BALDE B]** Cobertura de stock (días que aguanta cada SKU) — cruce forecast × inventario

#### `/dashboards/abc` (A1-A4)
- A1: ABC × XYZ matrix (frecuencia × valor) — cálculo sobre `fact_ventas` + `mart_rotacion_abc`
- A2: **[BALDE B]** Migración mensual A→B, B→C — snapshot mensual de `mart_rotacion_abc`
- A3: Valor inmovilizado por bucket — cruce con `mart_inventario_actual`
- A4: % SKUs sin ventas en cada bucket — cruce con `mart_productos_dormidos`

#### `/dashboards/dormidos` (D1, D2, D3, D5 — D4 descartado)
- D1: Stratificación por tier (>90d, >180d, >365d, >730d) — `dias_sin_venta`
- D2: Valor inmovilizado total ($X.XM) — `SUM(stock × costo)`
- D3: Filtros: por categoría / proveedor / bodega — JOINs `dim_producto`
- D5: **[BALDE B]** Histórico: cuándo entró en dormido — snapshot mensual

### Grupo 2 · Dashboards PREDICTIVOS (18 features)

#### `/forecast` (F1-F6)
- F1: Forecast por CATEGORÍA — `gold.forecast_categoria` (existe, ADR-0020)
- F2: Cobertura del modelo (% SKUs con forecast confiable) — calculable
- F3: **[BALDE B]** Backtesting visual (predicho vs real) — historia de forecasts
- F4: Resumen métricas modelo (WAPE 45.83% baseline vs 864% Prophet vs 57% LightGBM) — summary del audit
- F5: Tabla SKUs ordenable (predicción, urgencia, fecha, modelo) — `forecast_demanda_sku`
- F6: Filtros (categoría, modelo, horizon) — `forecast_demanda_sku`

#### `/alerts` (AL1-AL6)
- AL1: Resumen counts por urgencia (alta/media/baja stat cards) — `alertas_quiebre`
- AL2: Acciones tomadas vs pendientes — cruce `alertas_quiebre` × `app_alert_actions`
- AL3: Valor en riesgo ($X.XM en alta) — `demanda_predicha × precio`
- AL4: Distribución por categoría — JOIN `dim_producto`
- AL5: **[BALDE B]** Histórico alertas por día (últimos 30d) — snapshot diario
- AL6: Snooze granular (postponed auto-reactivable) — schema F5 ya soporta `postponed_to`

#### `/plan-compras` NUEVO (PC1-PC6)
- PC1: Tabla decision-oriented (SKU, stock, demanda, **cantidad_a_comprar**, ABC, urgencia, dormido?, supplier)
- PC2: Filtros agregados (proveedor, ABC, urgencia, categoría)
- PC3: Resumen orden propuesta (total SKUs, unidades, valor)
- PC4: Exportar CSV/PDF
- PC5: Sugerencia "ya estaba dormido, no recomprar"
- PC6: **[BALDE B]** Histórico planes guardados — tabla nueva `app_purchase_plans`

### Grupo 3 · Dashboards OPERATIVOS (17 features)

#### Home VENDEDOR (`/` con role=vendedor) (HV1-HV6)
- HV1: Buscador productos autofocus al entrar
- HV2: Top 3 alertas activas (cards con CTA)
- HV3: Top 3 dormidos para liquidar (con margen sugerido)
- HV4: Mis acciones del día (count + última)
- HV5: Top 3 productos rotación A
- HV6: Stale data banner si datos > 24h (componente ya existe)

#### Home GERENTE (`/` con role=admin/gerente) (HG1-HG6)
- HG1: 4 KPI cards arriba (Ventas / Facturas / Ticket / Delta)
- HG2: Gráfico tendencia mensual REAL últimos 6m — endpoint nuevo
- HG3: 5 cards "Decisiones de compra" (Alertas / Forecast / ABC / Dormidos / Inventario)
- HG4: Alerta destacada si hay drift detectado — `gold.alertas_drift`
- HG5: Top 5 vendedores del mes (mini ranking)
- HG6: Resumen "Plan compras sugerido"

#### `/acciones` (AC1-AC5)
- AC1: Counts del día (total / ordered / dismissed / postponed)
- AC2: Filtros (usuario, fecha, tipo)
- AC3: Tabla completa con SKU, action_type, user, qty, supplier, notes
- AC4: Exportar CSV
- AC5: Acciones postponed con countdown ("vence en X días")

### Grupo 4 · Dashboards NUEVOS sin página actual (14 features)

#### `/cohortes` NUEVO (CO1-CO5)
- CO1: Tabla cohortes por mes de primera compra
- CO2: Heatmap retención (cohorte × meses posteriores)
- CO3: Lifetime value por cohorte (LTV)
- CO4: Top 10 clientes recurrentes
- CO5: Distribución nuevos vs recurrentes este mes

#### `/vendedores` NUEVO (VE1-VE5)
- VE1: Ranking vendedores del mes (ventas, facturas, ticket)
- VE2: Comparativa mes vs mes anterior por vendedor
- VE3: Top productos vendidos por cada vendedor
- VE4: Días/horas pico de cada vendedor
- VE5: Conversion rate (calidad de venta)

#### `/drift` NUEVO (DR1-DR4)
- DR1: Tabla alertas de drift (cuándo, qué métrica, magnitud)
- DR2: **[BALDE B]** Gráfico WAPE baseline semana a semana — historia
- DR3: Threshold actual + warnings visible
- DR4: Recommended action: re-train cuando drift > X%

---

## 3 · Resumen ejecutivo

**Total features:** 69
- Balde A (datos existentes): 56 features factibles inmediatamente
- Balde B (snapshots históricos): 13 features con datos vacíos hasta acumular tiempo

**Total dashboards:**
- Migrados con sistema nuevo: 8 (`ventas`, `inventario`, `abc`, `dormidos`, `forecast`, `alerts`, `acciones`, home gerente)
- Nuevos: 4 (`plan-compras`, `cohortes`, `vendedores`, `drift`)
- Home diferenciado por rol: 2 layouts (vendedor / gerente)
- **Total: 12 dashboards + 2 home layouts**

**Endpoints backend nuevos requeridos (Dev A):**
- `/metrics/sales-trend?periods=6` (V1, HG2)
- `/metrics/plan-compras` (PC1-PC6)
- `/metrics/cohortes-detail` (CO1-CO5)
- `/metrics/vendedores-summary` (VE1-VE5)
- `/metrics/drift-summary` (DR1-DR4)
- Posiblemente: `/metrics/forecast-categoria` (F1)

**Jobs nuevos para balde B (Dev A):**
- Snapshot mensual `mart_rotacion_abc` (A2)
- Snapshot mensual `mart_productos_dormidos` (D5)
- Snapshot diario `gold.alertas_quiebre` (AL5)
- Retención de forecasts viejos (F3)
- Cálculo de rotación + cobertura (I3, I6)
- Tabla nueva `app_purchase_plans` con schema + endpoints (PC6)

---

## 4 · Cronograma realista

| Semana | Actor | Entregable |
|--------|-------|-----------|
| **Sem 1 (HOY)** | F6-D-FIX1 (Dev A+T) | 3 bugs producción |
| **Sem 1 (paralelo)** | Humano | Subir branding a `docs/f7/branding/` |
| **Sem 1-2** | Dev T | F7-B Design system (tokens, 8 componentes, stories) |
| **Sem 2** | Dev A | Endpoints backend nuevos (sales-trend, plan-compras, vendedores, cohortes, drift) |
| **Sem 2** | Dev A | Jobs snapshot balde B (workflow actualizado) |
| **Sem 2-3** | Humano | Demo 4G (R6) + Demo gerencia (R8) — APUNTANDO a Render para test SPOF |
| **Sem 3** | Dev T | F7-C parte 1: migrar 8 pages existentes + home por rol |
| **Sem 3-4** | Dev T | F7-C parte 2: crear 4 dashboards nuevos (plan-compras, cohortes, vendedores, drift) |
| **Sem 4** | Dev T | F7-C parte 3: mobile-first responsive + Lighthouse > 85 |
| **Sem 4** | Revisor | E5 memoria con capturas finales |
| **Sem 5-6** | Esperando | Acumular snapshots balde B (mínimo 30 días) |
| **Sem 6-8** | Humano | Ensayar defensa + ajustes finales |
| **Sem 8** | Humano | Defensa académica |

**Total: 6-8 semanas hasta defensa.**

---

## 5 · V críticas F7 actualizadas (12 V-F7)

| ID | Verificación | Pass criterion |
|----|--------------|---------------|
| V-F7-1 | Discovery completo | 4 docs en `docs/f7/` ✅ (este es el 4to) |
| V-F7-2 | Branding subido | `docs/f7/branding/logo.svg` + `colors.md` |
| V-F7-3 | Design system | tokens.ts + 8 componentes base + stories |
| V-F7-4 | Home por rol | Login vendedor → búsqueda; login admin → financiero |
| V-F7-5 | 12 dashboards funcionales | 8 migrados + 4 nuevos cargan sin error |
| V-F7-6 | Bug semántico "tendencia" arreglado | `/ventas` muestra tendencia real |
| V-F7-7 | Mobile-first verificado | Playwright 3 viewports + Lighthouse Mobile > 85 |
| V-F7-8 | A11y AA | Contraste 4.5:1 + focus + labels |
| V-F7-9 | Backend endpoints nuevos | 5+ endpoints funcionando con datos |
| V-F7-10 | Jobs snapshot balde B activos | Workflow modificado, primer snapshot capturado |
| V-F7-11 | Demo mobile 4G post-F7 mejor | Vos validás vs pre-F7 |
| V-F7-12 | Tests pasan | typecheck + playwright + pytest verdes |

**Gate:** V-F7-1 a V-F7-12 PASS → F7 cerrada.

---

## 6 · Aprobación humana

✅ Todo grupo 1 (20 features)  
✅ Todo grupo 2 (18 features)  
✅ Todo grupo 3 (17 features)  
✅ Todo grupo 4 (14 features)  
✅ Cronograma 6-8 semanas total (3-4 implementación + 30d snapshots + buffer defensa)  
✅ Trade-off aceptado: balde B con "captura en marcha" hasta tener datos

**F7-A Discovery cerrado oficialmente.** Próximo: F7-B Design system cuando humano confirme branding o pasen 24h.
