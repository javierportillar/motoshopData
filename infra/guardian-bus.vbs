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
' Uso (accion de la tarea MotoShopBusGuardian):
'     wscript.exe //B //Nologo <repo>\infra\guardian-bus.vbs

Option Explicit

Dim sh, cmd, rc
Set sh = CreateObject("WScript.Shell")

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & _
      """C:\Users\MotoShop\Documents\javidevmoto\motoshopData\infra\guardian-bus.ps1"""

rc = sh.Run(cmd, 0, True)
WScript.Quit rc
