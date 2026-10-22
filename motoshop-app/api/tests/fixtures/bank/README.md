# Fixtures offline del portal (bancolombia)

Estos archivos son una **APROXIMACIÓN** del DOM del portal de Bancolombia,
construida a partir de las capturas que el operador/envió y de la semántica de
las columnas que se ven en pantalla. **No son una captura del portal real y
nadie verificó que reproduzcan su HTML.**

| Fixture | Qué representa |
|---|---|
| `cuentas.html` | La sección **"Cuentas (2)"** con dos tarjetas de cuenta (`Distribuidora del Norte S.A.` y `MasVital`). |
| `movimientos_pagina1.html` | Primera página de la tabla **"Tus movimientos"** (columnas `Fecha \| Descripción \| Referencia \| Valor`) con el botón *Siguiente* habilitado. |
| `movimientos_pagina2.html` | Segunda página de la misma tabla, con *Siguiente* deshabilitado. |
| `login_otp.html` | La pantalla de verificación de dos pasos (el código se pide en la consola del nodo, no en el navegador). |

Valores, descripciones y referencias provienen de lo que el operador vio en
el portal (importes con separador de miles y dos decimales, negativos con el
signo adelante, referencias con el sufijo `" null"`).

## Lo que rompería si el DOM real difiere

- Los **selectores** viven todos en `portal_pages.py` (`PortalContract`): un
  rediseño del portal se corrige en ese único archivo.
- El **parser** (`parser.py`) no depende del DOM: recibe las celdas de una
  fila. Si el portal cambia el *número* de columnas o el *significado* de
  alguna, hay que tocar el parser y sus tests.
- La suite offline **no puede** detectar un cambio real del DOM: hace falta
  una corrida viva contra el portal para confirmar los selectores.
