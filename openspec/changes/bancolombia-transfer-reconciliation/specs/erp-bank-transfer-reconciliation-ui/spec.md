# erp-bank-transfer-reconciliation-ui Specification

## Purpose

Página operativa de transferencias bancarias: listado de movimientos ingeridos con su estado de
conciliación, filtros por estado y rango de fechas, y resolución manual de los movimientos
marcados, respetando el tenant y los permisos de cobranzas de caja. La captura del pago en el
punto de venta se prellena con los datos del movimiento candidato.

## Requirements

### Requirement: Prellenado automático en la captura del pago

Cuando el operador está capturando un pago y existe un movimiento candidato con el mismo valor,
el sistema MUST prellenar el campo de nombre del pagador y el campo de referencia con los datos
del candidato. El prellenado MUST NOT sobrescribir un valor que el operador ya escribió a mano y
MUST NOT contabilizar el pago por sí solo.

#### Scenario: Prellenado con candidato único

- GIVEN el operador captura un pago de 458200 y hay un candidato con ese valor
- WHEN se completa la captura
- THEN el nombre del pagador y la referencia quedan prellenados con los del candidato

#### Scenario: Valor ya escrito por el operador

- GIVEN el operador ya escribió una referencia a mano
- WHEN aparece un candidato con el mismo valor
- THEN la referencia escrita por el operador se conserva

#### Scenario: El prellenado no publica el pago

- GIVEN un pago prellenado desde un candidato
- WHEN el operador revisa la captura
- THEN el pago queda sin contabilizar hasta que el operador lo confirma

### Requirement: Estados sin candidato y con candidatos múltiples

Sin candidato, el formulario MUST permanecer vacío y MUST NOT mostrar un error. Con varios
candidatos, el operador MUST poder elegir uno de forma explícita.

#### Scenario: Sin candidato

- GIVEN el operador captura un pago sin movimientos con ese valor en la ventana
- WHEN se completa la captura
- THEN los campos quedan vacíos y no se muestra error

#### Scenario: Varios candidatos

- GIVEN el operador captura un pago con dos movimientos del mismo valor
- WHEN se completa la captura
- THEN se ofrecen los dos candidatos y el operador elige uno

### Requirement: Prevalencia de la corrección manual

Cuando el operador corrija un campo prellenado, el valor corregido MUST prevalecer sobre el
prellenado y MUST conservarse al confirmar la captura.

#### Scenario: Referencia corregida a mano

- GIVEN el campo de referencia quedó prellenado y el operador lo corrige
- WHEN el operador confirma la captura
- THEN se guarda la referencia corregida, no la prellenada

### Requirement: Listado de movimientos ingeridos

La página MUST listar los movimientos ingeridos con fecha del movimiento, descripción, referencia
saneada, importe, pagador, estado de conciliación y la factura a la que fue aplicado.

#### Scenario: Fila de movimiento

- GIVEN un movimiento conciliado contra una factura
- WHEN el operador abre la página
- THEN la fila muestra fecha, descripción, referencia saneada, importe, pagador, estado y la factura aplicada

### Requirement: Filtros por estado y rango de fechas

La página MUST permitir filtrar por estado de conciliación y por rango de fechas del movimiento.
El resultado MUST reflejar el filtro aplicado.

#### Scenario: Filtro por estado

- GIVEN hay movimientos en estado pendiente y en estado aplicado
- WHEN el operador filtra por estado pendiente
- THEN sólo se listan los movimientos pendientes

#### Scenario: Filtro por rango de fechas

- GIVEN movimientos en dos meses distintos
- WHEN el operador acota el rango de fechas a un mes
- THEN sólo se listan los movimientos de ese mes

### Requirement: Estados vacío, carga y error distinguibles

La página MUST distinguir los estados sin datos, en carga y con error. Un fallo del backend MUST
NOT renderizarse como ausencia de datos.

#### Scenario: Fallo del backend

- GIVEN la consulta de movimientos falla
- WHEN la página se renderiza
- THEN se muestra un estado de error y no un mensaje de lista vacía

### Requirement: Resolución manual de movimientos marcados

La página MUST ofrecer al operador la aplicación manual de un movimiento marcado, y MUST NOT
ofrecer acciones que la API rechazaría, como reaplicar un movimiento ya aplicado.

#### Scenario: Aplicación manual

- GIVEN un movimiento en estado ambiguo
- WHEN el operador lo aplica a una factura elegida
- THEN la página refleja el nuevo estado y la factura aplicada

#### Scenario: Acción no ofrecida

- GIVEN un movimiento ya aplicado
- WHEN se muestra la fila
- THEN no se ofrece la acción de aplicar

### Requirement: Tenant y permisos de la página

La página MUST respetar el tenant activo y el conjunto de permisos de cobranzas de caja: un
usuario sin ese permiso MUST NOT alcanzar la página.

#### Scenario: Usuario sin permiso

- GIVEN un usuario sin el conjunto de permisos de cobranzas de caja
- WHEN navega a la página de transferencias
- THEN el acceso es denegado

#### Scenario: Aislamiento por tenant

- GIVEN el operador pertenece a un solo tenant
- WHEN lista movimientos
- THEN sólo se muestran los movimientos de ese tenant
