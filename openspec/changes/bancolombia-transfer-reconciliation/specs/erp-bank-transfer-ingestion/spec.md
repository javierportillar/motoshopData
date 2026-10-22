# erp-bank-transfer-ingestion Specification

## Purpose

Captura segura de credenciales, autenticación 2FA, lectura paginada del portal Bancolombia,
parseo de la fila de movimiento e ingesta idempotente.

## Requirements

### Requirement: Captura interactiva de credenciales

El sistema MUST leer usuario, contraseña y frase de paso por prompt local sin eco. El texto
claro MUST NOT persistirse en disco, argv, entorno, logs, trazas ni video. El operador MUST listar,
rotar y eliminar credenciales sin revelar su valor.

#### Scenario: Captura sin eco

- GIVEN el operador ejecuta la herramienta
- WHEN ingresa usuario, contraseña y frase de paso
- THEN no se muestra ni queda en logs ni archivos

#### Scenario: Gestión de una credencial almacenada

- GIVEN existe una credencial almacenada
- WHEN el operador la lista, rota o elimina
- THEN informa su estado sin revelar el valor

### Requirement: Bóveda cifrada con acceso restringido

El sistema MUST almacenar sólo texto cifrado, con un modo de archivo restringido al propietario, y
MUST NOT guardar la clave junto al cifrado. MUST rehusar operar si el cifrado no se descifra,
con error claro y sin estado parcial.

#### Scenario: Round-trip de la bóveda

- GIVEN una credencial cifrada con una frase de paso
- WHEN se descifra con la misma frase de paso
- THEN se obtiene el valor original, sin texto claro

#### Scenario: Frase de paso incorrecta o archivo alterado

- GIVEN una credencial cifrada
- WHEN se descifra con una frase incorrecta o un archivo alterado
- THEN el error es claro y no persiste estado parcial

### Requirement: Autenticación con verificación en dos pasos

El sistema MUST autenticarse con las credenciales de la bóveda. Si el portal exige un código
dinámico, MUST pedirlo interactivamente en el momento y MUST NOT persistirlo.

#### Scenario: Ingreso y código dinámico en vivo

- GIVEN una credencial válida y el portal exige un código
- WHEN el sistema se autentica y alcanza el desafío
- THEN pide el código en el momento y no lo guarda

### Requirement: Reutilización de sesión

El sistema MUST reutilizar un perfil de navegador persistente entre ejecuciones, sin repetir el
desafío en cada corrida. El perfil MUST residir fuera del repositorio y MUST quedar excluido del
control de versiones.

#### Scenario: Segunda corrida y perfil no versionado

- GIVEN una corrida previa dejó un perfil autenticado
- WHEN se ejecuta una nueva corrida
- THEN reutiliza la sesión y el perfil no es versionable

### Requirement: Selección de la cuenta por etiqueta

Cada tenant MUST tener su propia etiqueta de cuenta configurada. El sistema MUST alcanzar la
tabla de movimientos de la cuenta cuya etiqueta coincide con la etiqueta configurada para el
tenant en curso, y MUST NOT seleccionarla por posición ni por índice. Si esa etiqueta no está
presente en la sesión del portal, MUST rehusar la lectura con error explícito en lugar de leer
otra cuenta.

#### Scenario: Cuenta del tenant en curso presente

- GIVEN el portal lista una cuenta con la etiqueta configurada para el tenant en curso
- WHEN la ingesta navega a sus movimientos
- THEN lee los movimientos de esa cuenta y de ninguna otra

#### Scenario: Etiqueta del tenant en curso ausente

- GIVEN el portal no lista ninguna cuenta con la etiqueta configurada para el tenant en curso
- WHEN la ingesta intenta abrir los movimientos
- THEN falla con error de cuenta no encontrada y no registra movimientos

#### Scenario: Etiquetas distintas por tenant

- GIVEN el portal lista una cuenta con la etiqueta de un tenant y otra con la del tenant en curso
- WHEN la ingesta navega a sus movimientos
- THEN lee los movimientos de la cuenta del tenant en curso y ninguno de la otra

### Requirement: Credenciales resueltas por tenant

La bóveda MUST mantener una entrada de credenciales por tenant y MUST NOT una entrada genérica
compartida entre tenants. Cada nodo en ejecución MUST declarar el tenant que sirve y MUST
resolver sólo la entrada registrada bajo ese tenant. Si la entrada no existe, el sistema MUST
fallar de forma explícita y MUST NOT usar la credencial de otro tenant ni ejecutar un scraping
anónimo o sin autenticar.

#### Scenario: Credencial del tenant en curso

- GIVEN la bóveda tiene una credencial registrada para el tenant en curso
- WHEN la ingesta resuelve la credencial
- THEN usa esa credencial para autenticar en el portal

#### Scenario: Credencial del tenant en curso ausente

- GIVEN la bóveda no tiene ninguna credencial registrada para el tenant en curso
- WHEN la ingesta resuelve la credencial
- THEN falla con error explícito de credencial ausente, no usa la credencial de otro tenant y no registra movimientos

#### Scenario: Credenciales de varios tenants en un mismo equipo

- GIVEN un mismo equipo tiene credenciales registradas para más de un tenant
- WHEN la ingesta se ejecuta para un tenant
- THEN usa sólo la credencial registrada para ese tenant

### Requirement: No consulta de cuentas de otro tenant

El sistema MUST NOT consultar la cuenta de otro tenant, aunque esa cuenta sea visible en la
misma sesión del portal. La sesión puede listar todas las cuentas asociadas al ingreso al
portal, pero sólo la cuenta del tenant en curso es admisible para la lectura.

#### Scenario: Cuenta de otro tenant visible en la sesión

- GIVEN la sesión del portal lista la cuenta del tenant en curso y la cuenta de otro tenant
- WHEN la ingesta recorre las cuentas disponibles
- THEN sólo consulta la cuenta del tenant en curso y no pide movimientos de la otra

### Requirement: Cobertura paginada de la ventana de consulta

El sistema MUST recorrer todas las páginas de la tabla necesarias para cubrir la ventana
solicitada —el día en curso por defecto— y MUST exponer los límites de página y de ventana en el
resultado de la lectura.

#### Scenario: Movimiento en una página posterior

- GIVEN el movimiento buscado está en la segunda página de la tabla
- WHEN la ingesta recorre la ventana
- THEN lo encuentra y lo expone con su página

#### Scenario: Ventana por defecto de un día

- GIVEN la ingesta se ejecuta sin ventana explícita
- WHEN se determina el rango de fechas
- THEN la ventana cubre el día en curso y queda expuesta

### Requirement: Campos del movimiento leídos de la tabla

El sistema MUST convertir cada fila en un movimiento con fecha, descripción, referencia sin el
sufijo " null", valor decimal y nombre del pagador sólo cuando la descripción empieza con
"PAGO QR". Una referencia de sólo ceros MUST quedar como referencia no utilizable y una
descripción que no sea "PAGO QR" MUST quedar sin pagador, sin error.

#### Scenario: Fila de pago QR

- GIVEN la fila "PAGO QR LIZETH STEPHANIA PORTI" con referencia "0092055984 null" y valor "$ 458.200,00"
- WHEN la ingesta parsea la fila
- THEN guarda el pagador "LIZETH STEPHANIA PORTI", la referencia "0092055984" y el valor 458200.00

#### Scenario: Referencia nula y descripción no pagadora

- GIVEN la fila "ABONO INTERESES AHORROS" con referencia "0000000000"
- WHEN la ingesta parsea la fila
- THEN la referencia queda no utilizable, el pagador queda vacío y la ingesta no falla

### Requirement: Dirección del movimiento según el signo del valor

El sistema MUST distinguir ingreso de egreso por el signo del valor y MUST tratar como candidato
de pago sólo el movimiento de valor positivo. Comisiones, traslados e intereses negativos MUST
NOT ser candidatos de pago.

#### Scenario: Comisión con valor negativo

- GIVEN la fila "COMISION TRASLADO OTROS BANCOS" con valor "- $ 7.590,00"
- WHEN la ingesta clasifica la fila
- THEN queda como egreso y no es candidato de pago

#### Scenario: Consignación con valor positivo

- GIVEN la fila "CONSIGNACION CORRESPONSAL CB" con valor positivo
- WHEN la ingesta clasifica la fila
- THEN queda como ingreso

### Requirement: Importe con aritmética decimal

El sistema MUST leer el importe en formato colombiano —punto de miles y coma decimal— y MUST
operarlo con aritmética decimal exacta. El importe MUST NOT ser alterado por redondeo de punto
flotante.

#### Scenario: Importe con separadores

- GIVEN el valor "$ 458.200,00"
- WHEN la ingesta lo convierte
- THEN el importe es 458200.00 exacto

#### Scenario: Importe negativo con signo

- GIVEN el valor "- $ 7.590,00"
- WHEN la ingesta lo convierte
- THEN el importe es -7590.00 y la fila se marca como egreso

### Requirement: Ingesta idempotente de movimientos

El sistema MUST extraer de cada transferencia entrante su identificador externo, fecha, importe,
pagador y referencia bancaria, y MUST ser idempotente por tenant e identificador.

#### Scenario: Extracción de los datos del movimiento

- GIVEN el portal muestra una transferencia entrante
- WHEN la ingesta lee la sesión
- THEN el movimiento guarda identificador, fecha, importe, pagador y referencia

#### Scenario: Re-ingesta sin duplicados

- GIVEN un movimiento ya ingerido para el tenant
- WHEN la ingesta vuelve a correr
- THEN no se crea un segundo registro del movimiento

### Requirement: Estados de error distinguibles

El sistema MUST distinguir credencial ausente, credencial inválida, sesión expirada, desafío
anti-bot y portal no disponible. Ningún error MUST dejar movimientos o filas parciales.

#### Scenario: Credencial ausente

- GIVEN no hay credencial almacenada
- WHEN se inicia la ingesta
- THEN indica credencial ausente y no registra movimientos

#### Scenario: Desafío anti-bot

- GIVEN el portal presenta un desafío anti-bot
- WHEN se intenta la ingesta
- THEN el error indica anti-bot y no deja movimientos parciales

### Requirement: Límite de frecuencia de ejecución

El sistema MUST NOT ejecutar sesiones concurrentes y MUST garantizar un intervalo mínimo entre
ejecuciones.

#### Scenario: Corridas concurrentes

- GIVEN una ejecución en curso
- WHEN se inicia otra ejecución
- THEN se rechaza y no abre sesión paralela

#### Scenario: Intervalo mínimo

- GIVEN una ejecución reciente
- WHEN se inicia otra antes del intervalo mínimo
- THEN se rechaza: aún no corresponde
