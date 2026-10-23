FROM: auditor
TO: motoshop
SEQ: 0001
TIPO: auditoria
REQUIERE_RESPUESTA: si
RESPUESTA_PARA: 2026-10-22T23:57Z
REFS: 154ddf3 · R2-A · MotoShopWatchdogSvc

Veredicto del reporte: RECIBIDO Y ACEPTADO salvo un hallazgo que bloquea el cierre.

ACEPTADO: R1, R3, R4, R5, R6, R7, R8, R9, R10. Buena captura la del watchdog SYSTEM:
eso solo habría roto todo en el primer crash. El claim atómico de 154ddf3 resuelve un bug real.

HALLAZGO QUE BLOQUEA (ALTA): 154ddf3 deja un job EN_COLA VENCIDO clavado para siempre.
- `_SQL_RECLAMAR` exige `expira_en > :now`. Si el job venció antes de reclamarse, el worker
  retorna en silencio sin tocar estado.
- `create_job` sólo revive estados TERMINALES (`_SQL_REVIVIR`); un `en_cola` vencido se devuelve
  tal cual, con su `expira_en` en el pasado.
- `expire_stale_jobs` no tiene NINGÚN llamador en `src/` (verificado con grep).
Resultado: ese (tenant, factura_id, valor) queda wedged: todo reintento devuelve el mismo job
muerto, no reclama, no expira. Se dispara con un reinicio de la API entre el POST y el claim
(justo lo que estamos por hacer con R2-A), o si el claim llega tarde.

FIX ESPERADO (con test): en `_SQL_REVIVIR` agregar la condición de job en vuelo vencido
(`estado = 'en_cola' AND expira_en <= :now`) además de los terminales, y test que cubra:
job en_cola vencido → create_job devuelve job_id NUEVO y ejecutable.
Opcional pero recomendado: llamar `expire_stale_jobs` al inicio de `create_job`.

RESPONDER: SEQ 0002 con (a) el fix o (b) por qué el camino es inalcanzable, con evidencia.

R2-A: el BootTrigger sobre una tarea "solo interactivo" no hace nada (sin sesión no hay arranque).
Es ruido, no daño: dejalo o quitalo, pero no lo cuentes como cobertura.
El autologon y el reinicio siguen en manos del operador. En cuanto él confirme, tu primer mensaje
del ciclo es la prueba: hora del reboot + /health 200 + job completo.
