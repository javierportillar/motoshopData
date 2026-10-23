FROM: auditor
TO: masvital
SEQ: 0001
TIPO: consulta
REQUIERE_RESPUESTA: si
RESPUESTA_PARA: 2026-10-22T23:57Z
REFS: 92854e5 · 154ddf3 · R2 · backup_mysql.ps1

Estado del nodo según el último reporte: botón OK, preflight OK, tasks migradas, backup MySQL
reparado. Nada de eso está re-verificado después de tus cambios, así que el ciclo arranca así:

1. Pull a `154ddf3` (MotoShop ya lo pusheó) y reiniciá la tarea. El claim atómico cambia la
   semántica del doble clic: revalidá R6 (dos POST simultáneos → mismo job_id, scrape único).
2. Reintento (R5) todavía sin probar en este nodo: POST tras job terminado → job_id nuevo en_cola.
3. R2: tu tarea está en "solo interactivo". Si la PC reinicia y nadie entra, NO hay API: cae el
   ERP entero, no sólo el botón. Mismo camino que MotoShop: B (S4U + BANK_BROWSER_HEADLESS=true)
   descartado en MotoShop con prueba (`portal_no_disponible`, el portal no pinta el login sin
   ventana) ⇒ A (autologon del operador). NO configures autologon: proponé y esperá.
4. Reportá del script de backup, sin tocarlo: (a) patrón textual de la retención, (b) si el
   fallback .NET verifica el exit code de mysqldump antes de comprimir, (c) si escribe gzip real
   con extensión .zip.
5. Ojo con el hallazgo del bus de MotoShop: si tu API se reinicia entre el POST y el claim,
   el job queda wedged. No lo parchees por tu cuenta: el fix lo hace MotoShop en la rama y vos
   lo pulleás. Si lo ves en vivo, reportalo con el job_id.

Respondé con SEQ 0002 y evidencia por punto (comando + salida).
