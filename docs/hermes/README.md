# Ingeniería inversa de sgHermes

Documentación del sistema legacy que hoy sostiene la operación (POS/ERP SgHermes 9.1.0 sobre MySQL) y plan de reconstrucción en Next.js + FastAPI.

## Contenido

| Archivo | Para qué sirve |
|---|---|
| [`hermes_reverse_engineering_blueprint.md`](hermes_reverse_engineering_blueprint.md) | **Documento principal.** Ficha técnica, modelo de datos, reglas de negocio, casos de uso, arquitectura propuesta, ETL, riesgos y backlog. |
| [`evidence/`](evidence/) | Evidencia cruda: diccionario de datos, dump del esquema, literales y SQL del binario, manual de usuario, comandos de REA y scripts reproducibles. |

## Estado

| Fase | Estado |
|---|---|
| Identificación técnica del binario | ✅ Completa |
| Introspección de la base (175 tablas) | ✅ Completa |
| Extracción de reglas desde SQL embebido | ✅ Completa (147 sentencias) |
| Lectura de IL / descompilado | ❌ Bloqueada: falta `dotnet` + `ilspycmd` |
| Paridad de cálculo validada contra facturas | 🔲 Pendiente (20 facturas con descuento/IVA) |
| Prueba de comportamiento de stock | 🔲 Pendiente (venta controlada) |

## Cómo leerlo

Cada afirmación está marcada:

- **[V] Verificado** — evidencia directa (binario, `information_schema`, filas reales).
- **[I] Inferido** — deducción del modelo de datos, pendiente de validación.
- **[X] No determinable** — requiere descompilación o prueba dinámica.

No trates una **[I]** como contrato: son hipótesis de trabajo.

## Hallazgos que condicionan el rediseño

1. `totdet = (valuni − dctpes + ivapes + ipopes) × candet` — fórmula extraída del binario, los impuestos son **por unidad**.
2. Los consecutivos viven en `contadores` (`numcon` = próximo), sin bloqueo ni índice único.
3. El stock es un contador único (`productos.exiprod`): **no hay kardex**, y se permite vender en negativo.
4. Los documentos (`facventas`, `detfventas`, `detapago`, `compras`, `detcompras`) **no tienen PK** y el motor es MyISAM.
5. Las contraseñas son **reversibles** y el acceso a datos es SQL concatenado sin parámetros.

## Siguiente paso

Cerrar el backlog de validación de la §9 del blueprint, empezando por la paridad de cálculo y el momento en que se descuenta el stock.
