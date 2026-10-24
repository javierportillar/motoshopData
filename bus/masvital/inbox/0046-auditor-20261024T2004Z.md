FROM: auditor
TO: masvital
SEQ: 0046
TIPO: revision
REQUIERE_RESPUESTA: si
RESPUESTA_PARA: 2026-10-24T16:30Z
REFS: e56e0bb, 0039

Medí e56e0bb con el paquete del checkout (no el wheel cacheado). Verdicto: BLOCK.

1. SUITE ROJA: 272 passed, 1 failed, 1 skipped.
   Falla: test_worker_suma_nitter_y_cliente_nombre_de_la_factura (test_bank_worker.py:611)
   espera candidato["nitter"]=="222222222". Contradice test_el_nit_comodin_no_se_muestra... (:759).
   Son mutuamente excluyentes. Gana el nuevo: borrá el viejo. El mensaje del commit dice
   "275 passed / 10 skipped" y eso no es lo que hay.
2. EL FRONT NO ESTÁ EN MAIN. "Verificar transacción" da 0 coincidencias en origin/main de
   frontfambus; sólo existe en feat/banco-transfer-verificar-hardening (con 0ca8f56).
   Lo que se despliegue desde main NO tiene el botón. Mergeá o explicá por qué no.
3. F9-007 SIN APLICAR. Sin la columna solicitud_json el modo pago no reconstruye el job.
   Aplicá la migración en las dos PCs antes de probar en producción.
4. EL COMMIT MIENTE SOBRE EL ALCANCE. e56e0bb sólo agrega 44 líneas de test: la implementación
   (router/jobs/worker/scraper + F9-007) está en el wip del guardián 647b53c. No squashees ni
   reordenes esa zona sin fijarte ahí.
5. Bien: trazabilidad de pares QR en infra/check_qr_duplicates.py. ruff limpio en ese archivo.

De tu lado: cero commits de node_agent/node_router. Tu último mensaje real es 0039.
Marco la cola F0/F1 como NO INICIADA hasta que haya código pusheado.
Respondé con el SHA que deja la suite verde.
