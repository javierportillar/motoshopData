# Bus de coordinación — handoff banco (nodo ↔ auditor)

Rama **huérfana** `bus/banco-handoff`. No se mergea nunca con `feat/banco-transfer-25-tenant-config`.
El código viaja por la rama de trabajo; por acá viaja **coordinación**: avances, dudas, bloqueos, auditorías.

## Cadencia
- Cada **5 minutos** cada parte: `git fetch` + leer su `inbox/` + escribir un mensaje en su `outbox/`.
- Sin novedades también se escribe: un `avance` de una línea que diga "sin cambios".
- El auditor responde los mensajes con `REQUIERE_RESPUESTA: sí` dentro de **12 minutos**.

## Formato (archivo nuevo por mensaje, nunca editar uno enviado)
Nombre: `bus/<nodo>/outbox/NNNN-<de>-<AAAAMMDDTHHMMZ>.md` — `NNNN` correlativo de 4 dígitos.

```
FROM: motoshop | masvital | auditor
TO: auditor | motoshop | masvital
SEQ: 0007
TIPO: avance | consulta | auditoria | bloqueo | cierre
REQUIERE_RESPUESTA: si | no
RESPUESTA_PARA: 2026-10-22T23:52Z   (sólo si REQUIERE_RESPUESTA: si)
REFS: 154ddf3 · R2-A · job 3fd6d149

<cuerpo: máximo 25 líneas, con evidencia en una línea por punto>
```

## Reglas
1. **Nunca** credenciales, contraseñas, tokens ni claves de autologon en el bus. Sólo rutas y nombres.
2. Máximo 25 líneas por mensaje. Si no entra, es dos mensajes.
3. Toda afirmación lleva evidencia: comando + salida, o el SHA + hora.
4. El bus **no autoriza** nada: aplicar conciliaciones, tocar catálogos legacy, cambiar cuentas o F9 sigue
   prohibido sin orden explícita del operador (R8 de los prompts).
5. Un mensaje sin respuesta en 12 minutos se reintenta cambiando de canal (avisar al operador en el chat).
6. Al cerrar un requisito: `TIPO: cierre` con el ✅ y la evidencia; el auditor confirma o rechaza.

## Montaje (worktree aparte para no ensuciar el árbol de trabajo)
```powershell
git worktree add ..\bus-wt bus/banco-handoff
cd ..\bus-wt
# leer:      Get-ChildItem bus\motoshop\inbox | Sort-Object Name | Select-Object -Last 5
# escribir:  nvim bus\motoshop\outbox\0007-motoshop-20261022T2340Z.md
git pull --rebase origin bus/banco-handoff
git add bus && git commit -m "bus(motoshop): 0007 avance" && git push origin bus/banco-handoff
```
Si el worktree no existe todavía en la máquina:
`git fetch origin && git worktree add ..\bus-wt origin/bus/banco-handoff`
