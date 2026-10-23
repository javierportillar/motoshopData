' start_api.vbs -- shim sin ventana para infra\start_api.ps1.
'
' El guardian invoca este VBS (no powershell.exe directo) para que el arranque
' de la API no muestre ninguna consola ni siquiera por un instante.
'
' Uso:
'     wscript.exe //B //Nologo <repo>\infra\start_api.vbs

Option Explicit

Dim sh, cmd, rc
Set sh = CreateObject("WScript.Shell")

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & _
      """C:\Users\MotoShop\Documents\javidevmoto\motoshopData\infra\start_api.ps1"""

rc = sh.Run(cmd, 0, True)
WScript.Quit rc
