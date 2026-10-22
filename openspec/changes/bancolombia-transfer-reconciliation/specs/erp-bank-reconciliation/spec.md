# erp-bank-reconciliation Specification

## Purpose

Conciliación de transferencias contra facturas abiertas por puntaje explicable, y coincidencia
por valor para la captura del pago en el punto de venta.

## Requirements

### Requirement: Coincidencia por valor dentro de la ventana

Dado un importe que se está cobrando y un conjunto de movimientos ingeridos, el sistema MUST
devolver como candidatos los movimientos cuyo valor sea igual a ese importe dentro de la ventana
de consulta. Si la ventana no contiene ningún movimiento con ese valor, MUST NOT devolver
candidato alguno.

#### Scenario: Valor que coincide dentro de la ventana

- GIVEN un importe de 458200 y un movimiento de 458200 dentro de la ventana
- WHEN se buscan candidatos por valor
- THEN devuelve ese movimiento como candidato

#### Scenario: Sin coincidencias en la ventana

- GIVEN un importe de 458200 y ningún movimiento con ese valor dentro de la ventana
- WHEN se buscan candidatos por valor
- THEN no devuelve candidato alguno

### Requirement: Frontera de la ventana de consulta

Un movimiento con el mismo valor fuera de la ventana de consulta MUST NOT ser candidato. La
ventana por defecto MUST ser el día en curso.

#### Scenario: Mismo valor de un día anterior

- GIVEN un importe de 458200 y un movimiento de 458200 fechado ayer
- WHEN se buscan candidatos por valor en la ventana del día en curso
- THEN ese movimiento no es candidato

### Requirement: Ambigüedad de valor entre movimientos

Si más de un movimiento de la ventana tiene el mismo valor, el sistema MUST reportar la
coincidencia como ambigua, MUST listar todos los candidatos y MUST NOT elegir uno por su cuenta.
Esta ambigüedad es por coincidencia de valor y es distinta de la ambigüedad entre facturas.

#### Scenario: Dos movimientos con el mismo valor

- GIVEN dos movimientos de 458200 dentro de la ventana
- WHEN se buscan candidatos por valor
- THEN el resultado es ambiguo, lista ambos y no selecciona ninguno

### Requirement: Datos del candidato para la captura del pago

El candidato por valor MUST exponer el nombre del pagador extraído después de "PAGO QR" y la
referencia saneada, sin el sufijo " null". Una fila que no sea "PAGO QR" MUST exponer el pagador
vacío.

#### Scenario: Candidato con pagador y referencia

- GIVEN el movimiento "PAGO QR CRISTOPHER BENAMIDES P" con referencia "0092055984 null"
- WHEN se expone el candidato
- THEN expone el pagador "CRISTOPHER BENAMIDES P" y la referencia "0092055984"

### Requirement: Matching explicable por puntaje

El sistema MUST puntuar cada factura candidata con señales ponderadas — referencia 100, NIT 80,
nombre normalizado 60, importe exacto 40, importe parcial 20 — y MUST explicar las señales que
coincidieron.

#### Scenario: Por referencia

- GIVEN una factura abierta con la referencia del movimiento
- WHEN se evalúan las candidatas
- THEN encabeza el puntaje con motivo de referencia exacta

#### Scenario: Por NIT del pagador

- GIVEN una factura abierta del mismo NIT pagador
- WHEN se evalúan las candidatas
- THEN alcanza 80 puntos por NIT del pagador

### Requirement: Aplicación condicionada a confirmación humana

El sistema MUST NOT generar ni aplicar un documento contable sin confirmación explícita del
operador. La confirmación MUST ser requisito previo a la aplicación. Un movimiento con puntaje ≥ 80
y candidata única MUST quedar disponible para aplicar, no aplicado por el sistema.

(Previously: el sistema auto-aplicaba con puntaje ≥ 80 y candidata única.)

#### Scenario: Movimiento listo para aplicar

- GIVEN un movimiento con puntaje 80 y candidata única
- WHEN se ejecuta la conciliación
- THEN queda listo para aplicar y no genera documento hasta la confirmación

#### Scenario: Confirmación del operador

- GIVEN un movimiento listo para aplicar
- WHEN el operador confirma el pago
- THEN se genera el documento y el movimiento queda aplicado

### Requirement: Estados marcados distinguibles

El sistema MUST distinguir el estado ambiguo (varias facturas igual de plausibles) del sobrepago
(importe mayor al saldo) y MUST NOT aplicar ninguno.

#### Scenario: Ambigüedad entre facturas

- GIVEN dos facturas abiertas con el mismo puntaje máximo
- WHEN se ejecuta la conciliación
- THEN queda ambiguo, con candidatas listadas, y no se aplica

#### Scenario: Sobrepago

- GIVEN una factura con saldo 50 000 y un movimiento de 60 000
- WHEN se ejecuta la conciliación
- THEN queda en sobrepago y no se aplica

### Requirement: Escritura por los caminos de caja existentes

Con match, MUST postear el recibo por el camino de cobranzas existente, con el mismo tipo y
validaciones que un recibo manual. Sin match, MUST aterrizar como consignación bancaria. MUST NOT
inventar un camino contable paralelo.

#### Scenario: Recibo con match

- GIVEN un movimiento con factura candidata única
- WHEN se aplica la conciliación
- THEN se genera un recibo como uno manual, con la fecha del movimiento

#### Scenario: Consignación sin match

- GIVEN un movimiento sin factura candidata
- WHEN se aplica la conciliación
- THEN queda como consignación bancaria, no como recibo

### Requirement: Fecha del recibo y periodo cerrado

La fecha del recibo MUST ser la fecha del movimiento. Un movimiento en un periodo cerrado MUST
rechazarse con 409 y quedar pendiente y reintentable hasta reabrirlo.

#### Scenario: Movimiento en periodo cerrado

- GIVEN un movimiento dentro de un periodo cerrado
- WHEN se intenta aplicar la conciliación
- THEN responde 409 y no se escribe documento

#### Scenario: Reintento tras reabrir

- GIVEN el movimiento quedó pendiente por periodo cerrado
- WHEN se reintenta con el periodo reabierto
- THEN se aplica con la fecha del movimiento

### Requirement: Idempotencia de la conciliación

El sistema MUST NOT crear documentos duplicados al reejecutar la conciliación; la idempotencia MUST
definirse por tenant e identificador externo.

#### Scenario: Reejecución sin duplicados

- GIVEN un movimiento ya conciliado y aplicado
- WHEN se reejecuta la conciliación
- THEN no se genera un segundo documento y conserva su estado

### Requirement: Aislamiento por tenant y permisos

El sistema MUST conciliar un movimiento sólo contra facturas de su tenant. Los endpoints MUST exigir
el guard de tenant ERP y los permisos de cobranzas de caja.

#### Scenario: Factura de otro tenant

- GIVEN un movimiento del tenant A y una factura del tenant B
- WHEN se evalúan las candidatas
- THEN la factura del tenant B no es candidata

#### Scenario: Usuario sin permiso

- GIVEN un usuario sin los permisos de cobranzas de caja
- WHEN intenta listar o aplicar movimientos
- THEN la respuesta es 403
