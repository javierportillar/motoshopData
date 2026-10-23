' guardian-bus.vbs -- shim sin ventana para el guardian del bus.
'
' Windows muestra una consola al lanzar powershell.exe desde el Programador de
' tareas, aunque el .ps1 use -WindowStyle Hidden: el parpadeo es del proceso
' powershell.exe en si. WScript.Shell.Run con 0 lo crea SIN ventana.
'
' Run(cmd, 0, True): ventana oculta (0) y espera a que el hijo termine (True),
' asi la tarea queda "Running" mientras el guardian vive y el Programador puede
' reiniciarla si muere.
'
' -NonInteractive: si algo pide confirmacion, que falle en vez de colgarse
' invisible para siempre (la tarea tiene ExecutionTimeLimit P3650D).
'
' La ruta del .ps1 sale de WScript.ScriptFullName: mover el repo no deja la
' tarea apuntando a una ruta vieja en silencio.
'
' Uso (accion de la tarea MotoShopBusGuardian):
'     wscript.exe //B //Nologo <repo>\infra\guardian-bus.vbs

Option Explicit

Dim sh, fso, dir, ps1, cmd, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = dir & "\guardian-bus.ps1"

If Not fso.FileExists(ps1) Then
  On Error Resume Next
  Dim log, f
  log = sh.ExpandEnvironmentStrings("%TEMP%") & "\guardian-banco.log"
  Set f = fso.OpenTextFile(log, 8, True)
  f.WriteLine "[" & Now & "] ERROR: no existe " & ps1 & " (shim guardian-bus.vbs)"
  f.Close
  WScript.Quit 3
End If

cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & ps1 & """"

rc = sh.Run(cmd, 0, True)
WScript.Quit rc
