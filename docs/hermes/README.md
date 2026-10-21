# Ingeniería inversa de sgHermes

Documentación del sistema legacy que hoy sostiene la operación (POS/ERP SgHermes 9.1.0 sobre MySQL) y plan de reconstrucción en Next.js + FastAPI.

## Contenido

| Archivo | Para qué sirve |
|---|---|
| [`hermes_reverse_engineering_blueprint.md`](hermes_reverse_engineering_blueprint.md) | **Documento principal.** Ficha técnica, modelo de datos, reglas de negocio, casos de uso, arquitectura propuesta, ETL, riesgos y backlog. |
| [`code_analysis.md`](code_analysis.md) | Lógica de negocio línea a línea del núcleo (ventas POS, pagos, consecutivos, stock, anulación, arqueo, contabilización), con referencias file:line del código descompilado. |
| [`modules.md`](modules.md) | **Análisis por módulo del 100% del binario** (721 clases): tesorería, notas, compras, kardex virtual, cierre contable, parámetros, nómina, DIAN, restaurante, reportes, migraciones. |
| [`form_catalog.csv`](form_catalog.csv) | Catálogo estructurado de las 721 clases con lógica: líneas, métodos, bloques SQL y tablas tocadas por archivo, agrupadas por dominio. |
| [`evidence/`](evidence/) | Evidencia cruda: diccionario de datos, dump del esquema, literales y SQL del binario, manual de usuario, comandos de REA y scripts reproducibles. |

## Estado

| Fase | Estado |
|---|---|
| Identificación técnica del binario | ✅ Completa |
| Introspección de la base (175 tablas) | ✅ Completa |
| Extracción de reglas desde SQL embebido | ✅ Completa (147 sentencias) |
| Lectura de IL / descompilado | ✅ Completa (.NET SDK 8.0.426 + ILSPY 8.2 — 797 archivos, 1.3M líneas; catálogo total + lectura profunda de los 28 formularios y helpers con lógica core) |
| Paridad de cálculo validada contra facturas | 🔲 Pendiente (20 facturas con descuento/IVA) |
| Prueba de comportamiento de stock | 🟫 Resuelta por evidencia de código: `Edi_CueInvProd` descuenta al guardar, sin validar negativos |
| Cobertura de análisis completo | ✅ Catálogo 100% (`form_catalog.csv`) + módulos con lógica documentados (`modules.md`) |

## Cómo leerlo

Cada afirmación está marcada:

- **[V] Verificado** — evidencia directa (binario, `information_schema`, filas reales, código descompilado).
- **[I] Inferido** — deducción del modelo de datos, pendiente de validación.
- **[X] No determinable** — requiere descompilación o prueba dinámica.

No trates una **[I]** como contrato: son hipótesis de trabajo.

## Hallazgos que condicionan el rediseño

1. `totdet = (valuni − dctpes + ivapes + ipopes) × candet` — fórmula extraída del binario, los impuestos son **por unidad**.
2. Los consecutivos viven en `contadores` (`conres` = próximo número; `numcon` es solo el código numérico del tipo de doc), con bloqueo por `LOCK TABLES` en el código pero sin índice único en la tabla.
3. El stock es un contador único (`productos.exiprod`) alimentado y recalcable desde los asientos de `detcuentas` (el kardex se reconstruye de eventos, nunca está en tabla): se permite vender en negativo.
4. Los documentos (`facventas`, `detfventas`, `detapago`, `compras`, `detcompras`) **no tienen PK** y el motor es MyISAM.
5. Las contraseñas son **reversibles** y el acceso a datos es SQL concatenado sin parámetros.
6. Los reportes/cierres materializan temporalmente en tablas `aux*` desechables (patrón a reemplazar por CTEs/vistas).
7. Anulación = reversa completa (asientos `estcue='A'`, pagos, financiación y **recálculo de stock**), con motivo + audit log en `motanudoc`.

## Siguiente paso

Diseño y construcción del sistema web: la base analítica está completa (`blueprint` + `code_analysis` + `modules`); el backlog de validaciones dinámicas del blueprint queda como verificación opcional, no bloqueante.
