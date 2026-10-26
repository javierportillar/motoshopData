# ESTADO — nodo MasVital · bancolombia-transfer-reconciliation

Copia **saneada** de la bitácora del nodo, publicada como referencia para el auditor.
Se quitaron claves, tokens, usuarios, contraseñas, rutas con nombre de usuario e IPs
internas; los datos de clientes (nombres e importes) quedaron resumidos a ids de job y
resultado. El original vive fuera del repo, en el nodo.

Repo: checkout del proyecto · rama `feat/banco-transfer-25-tenant-config`
Bus: worktree propio, push con `HEAD:refs/heads/bus/banco-handoff`.

## Cerrado

- **Claim atómico** (ajeno, `154ddf3`): `jobs.reclamar_ejecucion` + salida temprana en
  `worker.run_once`. Doble POST simultáneo (ventana 4.389 ms) → mismo `job_id`, un solo scrape.
- **Escenarios R1/R5/R6 verificados el 2026-10-22**: cuatro jobs resueltos con candidato único
  por importe y nombre; `ultimaIngestaAt` avanza con cada job.
- **Tarea de la API**: cuenta de servicio, `LogonType InteractiveToken`, trigger AtLogOn, sin
  límite de ejecución, acción `pythonw.exe <home>\.masvital\run_api.py` (sin ventana; log fuera
  del repo).
- **Backup MySQL**: GRANT LOCK TABLES al usuario de lectura → tarea de backup con código 0 y
  archivo verificado (1.559.494 B, 184 CREATE TABLE). Deuda: falta un usuario de backup propio.
- **Guardián del bus**: `infra/guardian-bus-masvital.ps1` (`37e756b`) + tarea `MasVitalBusGuardian`.
  Ojo: `infra/guardian-bus.ps1` es de MotoShop (`55d226d`).
- **Reintento del portal** (`4899193`): `portal_no_disponible` por timeout de click → 1 reintento
  tras 35 s, solo para ese código y si el job no venció. 4 tests nuevos.
- **Diagnóstico local**: `BANK_LOG_CAUSA=1` registra causa + traza del fallo en el log del nodo.
  Apagado por defecto; el detalle nunca viaja al job ni a la API.

## Reinicio real probado (2026-10-22 22:17)

- **Autologon: funciona** (sesión de servicio en consola sin intervención). Rollback documentado.
- **La API no volvió sola**: tarea en `Running` y puerto cerrado; el proceso estaba vivo y colgado
  (descargas S3 con la red todavía sin lista tras el boot). `schtasks /Run` no hace nada en ese
  estado (IgnoreNew) → el reintento del guardián era inútil.
- **Fix `10c34c1`, dos capas**: el lanzador sale con código 1 si a los 150 s no escucha (la tarea
  tiene reinicio 5×1 min); el guardián mata el proceso si `/health` falla con la tarea `Running`
  hace >6 min.
- Verificado tras el fix: tarea arriba en 10 s, `/health` 200, 0 ventanas de consola, job resuelto
  en 145 s (el primero tras un boot tarda más por el Chrome en frío).
- Herramienta: `post_reboot_check.ps1` + tarea `MasVitalPostRebootCheck` (2 min después del logon).

## Recuperación automática probada (con el nodo caído a propósito)

- **Vigilante de arranque**: lanzador de prueba que se cuelga sin abrir el puerto → a los **150 s
  exactos** escribe `arranque incompleto tras 150s: salgo con 1`, muere y la tarea queda `result=1`.
- **Escalada del guardián** (`3a87329`, umbral parametrizado): mismo cuelgue sin vigilante, tarea
  `Running` y `/health` caído → `API sin puerto hace 3m`, mata los dos procesos y relanza la tarea.
- **Corrección al informe anterior**: la política `RestartOnFailure` de la tarea (5 × 1 min) **no se
  disparó**. El que relanza es el guardián. Recuperación neta tras un reinicio: 150 s + hasta 5 min.
- Restaurado y medido: `/health` 200 al primer intento, acción de la tarea de vuelta al lanzador
  real, 0 ventanas, job resuelto en 70 s.
- Los scripts de prueba se borraron para que nadie apunte la tarea ahí por error.

## Pendiente

- [ ] El guardián y el nodo pueden pisarse el número de SEQ del bus (pasó con `0034`: salieron
      `0034-guardian` y `0034-masvital`). Nombres distintos, sin conflicto de archivo.
- [ ] **T1** (job empantanado): `expire_stale_jobs` sin llamador. Es de MotoShop upstream.
- [ ] Front/ERP: verificar el binding de la card (`pagador_nombre` vs `pagadorNombre`).
- [ ] Rotar la clave de MySQL y cerrar la escucha en `0.0.0.0:3306` con root sin password
      (el firewall de la PC no se toca por decisión del operador).
- [ ] `backup_mysql.ps1`: el fallback .NET escribe gzip con extensión `.zip` y la retención sólo
      borra `*.sql.gz` → nunca purga. No se tocó el script.

## Gotchas

- PowerShell 5.1: `& git ...` capturado dentro de una función que devuelve valor **cuelga** el
  proceso. Usar `git -C` suelto a nivel de script. (Bug del guardián upstream, reportado.)
- `git pull --rebase` falla con 128 si el árbol está sucio: rescatar wip antes del pull.
- `$pid` es de solo lectura; `.NET` usa el CWD del proceso, no el de la sesión.
- La rama es compartida con el agente de MotoShop: pushea cada pocos minutos y tocó
  `infra/guardian-bus.ps1` y `ESTADO.md`. No force-push, no amend de commits pusheados.
- La referencia de los PAGO QR es la misma en todos los movimientos (convenio): identifican el
  pago el **nombre + el valor**.
- La base tiene 179 de 184 tablas MyISAM: `--single-transaction` no da consistencia, el lock sí.

## Incidente 2026-10-26: acceso remoto a MySQL (causa: un cambio propio del 23/10)

- **Qué rompió**: `bind-address=127.0.0.1` + DROP de las cuentas de acceso remoto (bloque de
  seguridad del 23/10). Se validó solo desde el propio equipo, por eso parecía verde: el ERP local
  usa `localhost` y nunca se afectó, pero las demás PC del local y el acceso por VPN se quedaron
  sin base. El firewall no fue: los tres perfiles estaban deshabilitados desde antes.
- **Arreglo**: `bind-address=0.0.0.0` y restitución de las cuentas de acceso remoto, incluido el
  comodín que existía antes del hardening (password vacía, ALL + GRANT). La cuenta local del ERP
  quedó intacta.
- **Verificado**: escucha en `0.0.0.0:3306`; conexión real desde un cliente remoto; sesión visible
  en `SHOW PROCESSLIST` sobre la base; `/health` 200; las cuentas de servicio siguen solo localhost.
- **Corrección (misma fecha)**: la primera restauración fue insuficiente. El cliente entra por VPN y
  su IP **no** caía en el patrón por subred que había configurado (el túnel reparte un rango con
  máscara distinta a la del prefijo usado). Prueba de que era nuestro servidor: `Aborted_connects`
  pasó de 4 a 12 y `Connections` de 28 a 43 en la ventana del reporte. Con el comodín restituido, la
  conexión entró a las 12:32:14 y quedó la sesión del cliente en `SHOW PROCESSLIST`.
- **Regla nueva**: en una LAN con VPN, un patrón por subred es frágil porque el rango del túnel no
  coincide con la máscara real. Validar siempre con una sesión real de un cliente y usar
  `Aborted_connects` / `Connections` como contador de verdad.
- **Deuda abierta**: root sin password sobre la LAN es el riesgo real. Camino: usuario dedicado con
  password + regla de firewall acotada y recién después cerrar el acceso remoto del root. Requiere
  editar la configuración del ERP de cada PC.
- **Lección**: un cierre de puerto se valida **desde afuera**. Probarlo desde la propia máquina da un
  falso verde y rompe a los clientes.
- **F9-007**: la migración de `solicitud_json` nunca se había aplicado y el código ya la usaba (la
  API viva corría con el código viejo en memoria). Aplicada el 26/10.

## Modo cola (F0/F1): evidencia en vivo, 26/10 17:5x

- Arnés `infra/prueba_cola_local.py` (`0c9ee08`): levanta una instancia **aparte** en
  `127.0.0.1:8010` con `BANK_DISPATCH_MODE=queue` y un **portal falso** inyectado en
  `BankVerificationWorker._scraper_por_defecto`. No toca la API de producción (`:8000`), no abre
  sesión del banco, no usa Playwright. Borra sus jobs, candados y nodos de prueba incluso si falla.
- **Resultado: 25/25 comprobaciones OK.** Probado por HTTP de punta a punta:
  1. `/node/status` sin `X-Node-Token` → 401; con token → 200.
  2. POST de verificación → **202 en 16–47 ms**, `estado=en_cola`, **cero hilos**
     `banco-verificacion` en el proceso y el portal falso sin llamar.
  3. El agente late, reclama, raspa (una llamada al portal falso) y publica: el job sale de
     `en_cola` como `sin_coincidencia` (ventana sin movimientos).
  4. `sesion_cerrada_por_otro_dispositivo` **no** es fallo: el job vuelve a `en_cola` con el código
     estable y se puede retomar.
  5. Dos agentes con el mismo tenant: el segundo no obtiene job mientras el primero tiene el
     candado, ni después (cola vacía).
- **Trampa del arnés**: el agente toma el job **más viejo** (FIFO), así que un `en_cola` de una
  corrida anterior hace que las aserciones miren el job equivocado. El test ahora arranca
  verificando cola y candados vacíos.
- **Hallazgo menor de contrato**: `GET /node/status` documenta "dueños de cada cuenta" pero solo
  devuelve `tenants_en_linea`; el dueño del candado no se ve desde la API.
- **Comportamiento a tener presente**: si un agente muere con el candado tomado, ese tenant queda
  bloqueado hasta **60 s** (TTL del candado). Es por diseño; el sweeper rescata jobs, no el candado.

## TTL de cola: 900 s y motivo `sin_nodo` (26/10)

- El job nace con `TTL_COLA_SEGUNDOS = 900` y lo manda `BANK_JOB_QUEUE_TTL` (`ttl_cola_segundos()`;
  valor invalido o <= 0 cae al default). Antes eran 300 s: un job esperando el turno de sesion de
  otra cuenta moria antes de que un agente lo viera.
- Un `en_cola` vencido queda `expirado` con `error_codigo='sin_nodo'`, nunca `fallido`. El `SET` del
  barrido escribe `error_codigo` **antes** de `estado` porque MySQL 5.0 evalua las asignaciones de
  izquierda a derecha; al reves el motivo se pierde en silencio. Hay un test de SQL real que prueba
  ese orden, no un doble en memoria.
- `ejecutando` vencido: el barrido lo cierra sin motivo; el rescate con motivo es del plano de
  control (reloj de 180 s + `intentos`, ya probado).
- Pruebas: 301 s sigue en cola, 901 s vence con `sin_nodo`, la variable mueve el reloj y un valor
  basura no rompe. 43 tests en los dos archivos (9 de SQL real sobre MySQL 5.0.45). Suite bancaria
  completa sobre la cabeza de la rama: **290 passed, 10 skipped (POSIX/pty), 0 failed**.
- El cambio viajo en el commit de rescate del guardian (mitad de trabajo); la correccion del arnes
  de prueba es el commit siguiente.

## ERP: login verificado y dos hallazgos (26/10)

- El login del ERP con el usuario administrador funciona: hay sesiones vivas de hoy desde cuatro
  equipos del local, una abierta mientras se escribe esto. El usuario es de nivel 1.
- El usuario anterior era el de caja (nivel 2), que trabajo hasta el mediodia.
- **La clave almacenada del administrador no es la que se nos indico**: tiene 4 caracteres y la
  comparacion contra el valor recibido da falso. No se cambio: rotar la clave del administrador en
  horario de venta puede dejar a todo el negocio afuera.
- **La base tiene una sola empresa** (`E01 PRINCIPAL`). "Ambas empresas" no es verificable en este
  ERP.
- Cartera y posteo: el posteo es la escritura del modulo y **no se ejecuto** (prohibido aplicar
  conciliaciones). Lo verificado es el contrato cubierto por la suite y el modo de despacho en
  `local`.

## Decisiones de entrega

- **El modo cola no se enciende en producción**: sin plano de control central no agrega nada y suma
  una pieza que puede fallar. `BANK_DISPATCH_MODE` queda en `local`; el encendido se documenta, no se
  ejecuta.
- **El scrape sigue en la PC**: el plano de control nunca raspa y el default es idéntico al de hoy.
- **Candado por cuenta**, no por máquina, con TTL de 60 s y renovación cada 20 s.
- **Sin preempción y sin warm-up**: dos cuentas pueden raspar en paralelo; la sesión del banco no se
  abre para "calentar".

## Cierre del 26/10 (tarde): suite, migraciones, pruebas a-e y failover preparado

- **Suite sobre `main` (7d47150)**: 290 passed, 10 skipped (POSIX/pty), 986 deselected, 0 failed,
  con la bateria de SQL real habilitada. Sin diferencias del modulo banco contra el commit anterior.
- **Migraciones confirmadas en la base de este nodo**: el ledger registra F9-007 ademas de
  F10-001..004, y las columnas que el barrido necesita (`solicitud_json`, `intentos`) existen.
  La API arrancada sobre `main` lleva mas de un minuto barriendo sin errores.
- **Pruebas a-e, contra la API local y con la sesion real del portal**:
  - factura con importe que coincide con un movimiento del dia -> `resuelto`;
  - doble clic durante la corrida -> **mismo** `job_id` (la idempotencia protege la verificacion
    en curso);
  - reintento despues del cierre -> `job_id` **nuevo**;
  - leido justo despues del POST -> `ejecutando` (la pantalla lo muestra como pendiente);
  - modo pago sin coincidencia -> `sin_coincidencia`.
  Los cinco `job_id` quedaron publicados en el bus.
- **Semantica del barrido**: en modo local la cola **no** se expira (`expirar_cola()` solo corre con
  despacho en cola); lo que corre siempre es el rescate de `ejecutando` vencidos. El TTL de 900 s se
  ejerce cuando el nodo se enciende en cola.
- **Failover preparado, sin encender**: el nodo declaraba los dos tenants en el heartbeat; despues
  se corrigio a **solo `masvital`** (ver "BANK_NODE_TENANTS" mas abajo), porque este equipo no tiene
  la base del otro negocio. El perfil del segundo negocio existe vacio, y pedir ese tenant devuelve
  503 `tenant_no_servido` (nunca 500). El despacho sigue en `local`.
- **BANK_NODE_TENANTS=masvital** (26/10, cierre): sacar `motoshop` no es cosmetico. El MySQL local
  solo tiene la base `masvital`; `motoshop2024` vive en el MySQL del equipo de MotoShop. Declarar
  motoshop aca anunciaba una capacidad que no se puede honrar: el worker habria leido `masvital` y
  cruzado negocios. El 503 `tenant_no_servido` se mantiene y esta verificado tras el cambio.
  `root` sin contrasena queda como deuda de seguridad aceptada por el operador.
- **Afinamiento**: la API sirve un tenant por proceso. El failover es levantar el nodo con el tenant
  del otro negocio, no servir las dos cuentas desde el mismo proceso.
## MySQL: cuenta dedicada del ERP en localhost (26/10, tarde)

- Se creo una **cuenta dedicada en `localhost`** para el ERP, con clave propia de 28 caracteres
  generada en el equipo. No viajo por ningun canal y no se publica.
- `servidor.txt` del ERP quedo repuntado a esa cuenta, con respaldo del original tomado antes de
  escribir.
- La **cadena literal** se probo en un proceso de 32 bits con el mismo driver ODBC que usa el ERP:
  conexion OK y consulta de conteo contra la base del negocio.
- El **reinicio del ERP quedo pendiente**: en este equipo estaba abierta la pantalla de facturacion
  de venta y reiniciar podia cortar una venta en curso. No se reinicio; se pide decision del
  operador.
- No se toco firewall, ni `bind-address`, ni el acceso remoto del root. La cuenta nueva es solo
  localhost: no reemplaza el trabajo de cierre remoto, lo prepara.

## Correccion del 26/10 (noche): el repunte del ERP se revirtio y se encontro la causa

Este bloque **reemplaza** el parrafo anterior sobre el repunte y el reinicio pendiente: el repunte
no se aplico, la cuenta dedicada se elimino y la ERP quedo como estaba (una sola sesion desde las
12:05, sin interrupcion).

- **Hallazgo 1 - VirtualStore.** El ERP se ejecuta **no elevado**, asi que Windows le virtualiza
  `Program Files`: lee y **reescribe** su configuracion en
  `%LOCALAPPDATA%\VirtualStore\Program Files (x86)\Julio Chaves\SgHermes\servidor.txt`. Cualquier
  edicion en la ruta nominal de `Program Files` es decorativa: el ERP la ignora. El archivo real lo
  reescribe el propio ERP al arrancar (por eso su fecha cambia sin que nadie lo toque).
- **Hallazgo 2 - linea de contrasena.** En `servidor.txt` la contrasena vacia se serializa como la
  linea `;`. Una linea **en blanco** hace que el ERP la salte y **desplace todos los campos**: el
  puerto aparece como contrasena, la base como puerto y el driver como base de datos. Formato real:
  6 lineas CRLF con `;` final = IP / usuario / contrasena / puerto / base / driver ODBC.
- **Estado final del ERP**: `root` sin contrasena, base `masvital`, puerto 3306, driver ODBC 5.1,
  conexion por `localhost` (el ERP corre en el mismo equipo que el MySQL). `mysql.user` volvio a sus
  cinco filas de `root`; `servidor.txt` restaurado byte a byte; `CHECK TABLE` sobre las 186 tablas
  sin errores y sin ninguna reparacion ejecutada. Deuda de seguridad (`root` sin contrasena
  expuesto) aceptada por el operador.
- **Un job por verificacion**: la tabla mantiene **una fila por (tenant, factura, valor)** con id
  determinista y `ON DUPLICATE KEY`. Un reintento revive esa fila: cambia el `job_id` publico y se
  reinicia `creado_en`. Los `job_id` viejos de una misma verificacion no son filas distintas.
- **Mapa de la IP del nodo**: `26.84.60.116` es la IP de Radmin de este equipo y la consume el
  SgHermes de la otra PC para llegar a `masvital`. Este MySQL solo tiene la base `masvital` (no
  existe `motoshop2024`, que vive en el MySQL del equipo de MotoShop). Cada nodo sirve **su** base:
  el tenant `motoshop` declarado aca es solo heartbeat/enrolamiento, no fuente de datos.
