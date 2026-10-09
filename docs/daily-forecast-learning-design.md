# Pronóstico diario con vintages y calibración

## Objetivo

Mostrar, para cada día del mes, la predicción disponible antes de conocer sus ventas; comparar esa predicción con el resultado real y utilizar errores históricos para ajustar la curva de meses posteriores. Como cambio independiente de interfaz, el proveedor de una factura debe enlazar al perfil existente usando su NIT.

La curva actual no es un modelo entrenable: usa una tasa mensual basada en ventas recientes y la distribuye 75% por día de semana y 25% por tramo del mes. La primera versión de aprendizaje será una calibración determinística y auditable, no un modelo opaco.

## Comportamiento confirmado

- Para los días ya transcurridos, mostrar la predicción original congelada al inicio del mes y las ventas reales por separado.
- Para el mes en curso, la primera predicción puede reconstruirse desde los datos disponibles hasta el último día del mes anterior. Debe etiquetarse como **reconstruida**, porque no se guardó cuando se emitió originalmente.
- Los días sin ventas dentro de un periodo observado valen cero; los días posteriores al corte de ventas son desconocidos, no cero.
- La proyección con inventario es un escenario hipotético y no se usa para aprender la curva base.
- El proveedor se enlaza por NIT válido a la página de perfil ya existente; con NIT ausente o inválido se muestra texto normal.

## Requisitos funcionales (EARS)

- Cuando se crea un pronóstico mensual, el sistema debe guardar la curva diaria completa, el mes objetivo, fecha de origen, versión del modelo/calibración y cortes de las fuentes.
- Cuando una persona consulta el mes actual, la API debe devolver el pronóstico original para todos los días del mes y las ventas reales para los días cubiertos por el corte de ventas.
- Cuando un día observado no tenga factura válida, la venta real debe ser cero; cuando el día exceda el corte de ventas, la venta real debe ser `null`.
- Cuando el corte de ventas alcance el fin de un mes, el sistema debe evaluar el vintage congelado contra las ventas reales diarias y guardar sus errores.
- Cuando se genere el pronóstico siguiente, el sistema debe usar solo evaluaciones anteriores al origen de ese pronóstico; con evidencia insuficiente o fuentes desactualizadas debe mantener la curva base y marcar la calibración como no disponible.
- Cuando el usuario vea una factura con NIT válido, el nombre del proveedor debe enlazar a su perfil; cuando no haya NIT válido, debe permanecer como texto sin enlace.

## Diseño

```text
DuckDB/R2 (ventas reales + cortes)
       │
       ├─ tasa mensual y perfil 75/25
       ├─ vintage diario congelado por mes
       └─ ventas reales al cierre ──> WAPE / MAE / sesgo
                                      │
                         calibración con meses cerrados
                                      │
                                      └─> curva siguiente mes
                                              │
                         API daily_series ──> gráfico: barras reales + línea vintage

Factura (nombre + NIT) ──> enlace validado ──> perfil de proveedor existente
```

### Vintages y almacenamiento

- DuckDB es un snapshot de solo lectura que se reemplaza desde R2; no se debe usar como almacén de aprendizaje.
- Guardar vintages en Supabase, siguiendo el patrón actual de tablas privadas con `service_role`, `tenant_id`, RLS y filtros por tenant.
- `sales_forecast_vintages`: un vintage canónico por tenant/mes, con origen, modelo/calibración ganadores, cortes, tipo de ejecución (`issued` o `reconstructed`) y perfil diario.
- `sales_forecast_evaluations`: resultado append-only de la comparación al cierre del mes, vinculado al vintage y con corte real utilizado.
- Una clave única por tenant y mes arbitra atómicamente el vintage canónico y hace idempotente el backfill, incluso ante solicitudes concurrentes. El modelo y la calibración ganadores quedan registrados en el vintage; una corrida histórica alternativa por otra versión no reemplaza este benchmark canónico.
- El endpoint guarda las reconstrucciones walk-forward y sus evaluaciones. La calibración se deriva de las evaluaciones persistidas anteriores al mes objetivo; si el almacén no está configurado o falla, la respuesta marca el vintage actual como provisional y no afirma que quedó congelado.
- La primera corrida retrospectiva de un mes se calcula con los datos disponibles hasta el fin del mes anterior, se marca `reconstructed` y no se presenta como forecast emitido en tiempo real.

### Error y calibración

- Medir WAPE, MAE y sesgo firmado por día y por mes. No usar MAPE para días con venta cero.
- Calibrar el **nivel mensual** por separado de la **forma diaria**; una corrección de forma se aplica a los pesos por día de semana/tramo del mes y luego se normaliza para conservar el total.
- Aprender solo del pronóstico base; una venta limitada por stock no representa demanda potencial y no debe entrenar ese pronóstico.
- Usar una ventana de meses cerrados, mínimo de muestras, suavizado hacia factor 1 y límites configurables. Si la fuente de ventas está atrasada, el mes no se evalúa.
- El forecast original es el benchmark inmutable. El escenario con inventario sigue siendo contrafactual y mantiene su etiqueta actual.

### Interfaz

- En `VentasView`, dibujar ventas reales como barras y `Pronóstico original` como línea sobre todo el mes. El tooltip compara predicción, real y diferencia.
- Distinguir el total previsto al inicio del mes del total reestimado al corte (ventas observadas + estimación restante); no reutilizar la misma etiqueta para ambos.
- Mostrar fecha de origen, versión/calibración y número de meses de backtest. El estado debe indicar `base sin calibrar`, `calibrado` o `fuentes desactualizadas`.
- Mantener la curva con inventario como escenario, inicialmente solo para días futuros si no existe un vintage histórico confiable de stock.
- En `CompraDetalleContent`, reutilizar `isValidSupplierNit` y `supplierProfileHref`; no buscar proveedor por nombre ni crear un endpoint duplicado.

## Rollout

1. Persistencia de vintages y contrato API, sin cambiar todavía la calibración base.
2. Mostrar línea original en días transcurridos y distinguirla de la reestimación al corte.
3. Backfill walk-forward de 6–12 meses y evaluación diaria en modo sombra.
4. Activar calibración solo si el backtest reduce WAPE/sesgo frente al baseline; mantener bandera/fallback para revertir.
5. Enlace de proveedor por NIT y pruebas de NIT válido/ausente/inválido y navegación móvil/accesible.

## Criterios de aceptación

- En un mes de 31 días, la línea del vintage tiene 31 puntos incluso si solo hay ventas observadas en los primeros días.
- Cada barra real coincide con la consulta de ventas válidas; días observados sin factura muestran cero y fechas posteriores al corte muestran `null`.
- El pronóstico original no cambia cuando llegan ventas posteriores; las predicciones reconstruidas quedan etiquetadas y separadas de las emitidas.
- Los errores solo se calculan cuando el corte real cubre el mes completo y las fuentes requeridas están frescas.
- La siguiente curva usa una versión de calibración explícita; si hay pocos meses o no mejora el backtest, conserva el modelo 75/25.
- La suma diaria del vintage coincide al centavo con su total mensual.
- El escenario con inventario no se usa como etiqueta de entrenamiento.
- Un NIT válido abre el perfil correcto; sin NIT no se genera un enlace roto y se conserva el nombre visible.
