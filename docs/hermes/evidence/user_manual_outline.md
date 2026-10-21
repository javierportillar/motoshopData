# Evidencia — Manual de Usuario (SgHermes 9.1.0)

Fuente: `C:\Program Files (x86)\Julio Chaves\SgHermes\Manual de Usuario.pdf` — 26 páginas, ~26.000 caracteres.
Extracción: `extract_pdf.py` (pypdf 6.21.1). Texto completo en `manual_full_text.txt`.

> Nota de calidad: el PDF usa una fuente sin mapa Unicode completo, por lo que algunas vocales acentuadas salen como `�`. El contenido es legible; la pérdida afecta solo tildes.

## Índice

| Sección | Página |
|---|---|
| Copias de Seguridad | 3 |
| Ingreso al Software | 3 |
| Barra de Botones | 4 |
| Parametrización General de la Empresa | 5 |
| Parametrizar información de la Empresa | 5 |
| Crear Terceros (Clientes, proveedores y empleados) | 6 |
| Crear Catálogo de Productos | 7 |
| Crear Usuarios del Sistema | 10 |
| Procesos | 11 |
| Saldos Iniciales | 11 |
| Recibos de Caja (Comprobante de Ingreso) | 12 |
| Recibos de Caja (Comprobante de Egreso) | 13 |
| Facturación | 14 |
| Facturación POS | 15 |
| Compras | 17 |
| Informes | 18 |
| Informe de Comprobantes | 18 |
| Informe de Caja | 19 |
| Informe de Ventas | 20 |
| Informe de Cuentas por Cobrar | 21 |
| Informe de Cuentas por Pagar | 22 |
| Informe de Contabilidad | 23 |
| Informe de Inventario | 24 |
| Kardex | 25 |

## Pasajes relevantes (verbatim)

**Copias de seguridad (p. 3)** — confirmación de que el respaldo es a nivel de archivos, no lógico:

> "Para realizar su copia de seguridad, simplemente copiando la carpeta de base…"
> "Para restaurarla, puede borrar la carpeta anterior, y reemplazarla por la copia."

→ **Riesgo:** backup por copia de carpeta con la base en uso (MyISAM, sin `LOCK TABLES`/`FLUSH`) puede producir un respaldo inconsistente.

**Atajos (p. 4 y ss.):**

- `Ctrl+F7` — copiar o traer ítems/documentos desde otro documento.

**Catálogo de productos (p. 7-9):**

- "asignar una lista de precio"
- "lista el precio de venta según lista de precio, para eliminar presione la tecla Supr, y para modificar seleccione una lista de precio en la casilla Lista de Precio…"
- "La lista de precio ya se encuentra en la lista y si desea modificarla."

→ Confirma el modelo `preciosxpro` + `listapre` observado en la base.

**Facturación POS (p. 15-16):**

> "implementados puntos de venta, que utilizan impresoras tipo tiquete (POS) y una resolución especial de la DIAN."

→ Dos requisitos duros para el reemplazo: impresión térmica y numeración autorizada por DIAN.

**Recibos de caja (p. 12-13):** "Directamente podemos crear anticipos, conceptos y descuentos por medio de…" → los recibos admiten conceptos y descuentos, no solo cobro puro.

**Informe de Caja (p. 19):**

> "Puede filtrar la información por fecha, por arqueo de caja, por usuarios, por…"

→ El arqueo existe como **filtro de reporte**, no como entidad persistida (coherente con `cajaarqueo`/`detcajarq` vacías).

**Informe de Ventas (p. 20):** filtros "por fecha, por consecutivos, por tipo de factura, por…".

**Informes de Contabilidad / Inventario / Kardex (p. 23-25):** se generan contra `detcuentas` y el saldo de productos; "Kardex" es un informe derivado, no una tabla poblada.

## Conclusión operativa

El manual describe un flujo **mono-usuario, mono-caja, con respaldo por copia de carpeta y reportes generados al vuelo**. No documenta:

- cierre de caja formal (solo informe),
- anulación con reversa,
- control de stock negativo,
- multi-sucursal real,
- usuarios/roles más allá de la creación básica.

Todo eso confirma que las brechas detectadas en la base **son también brechas del producto**, no solo de esta instalación.
