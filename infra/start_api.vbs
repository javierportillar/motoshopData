' start_api.vbs -- shim sin ventana para infra\start_api.ps1.
'
' Se usa cuando hay que arrancar la API sin que aparezca ninguna consola, ni
' siquiera por un instante (el guardian lo llama como ultimo recurso).
'
' Run(cmd, 0, True): oculto y esperando el resultado.
' -NonInteractive: nada de prompts invisibles.
' Ruta derivada de WScript.ScriptFullName (no literal).
'
' Uso:
'     wscript.exe //B //Nologo <repo>\infra\start_api.vbs

Option Explicit

Dim sh, fso, dir, ps1, cmd, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = dir & "\start_api.ps1"

If Not fso.FileExists(ps1) Then WScript.Quit 3

cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & ps1 & """"

rc = sh.Run(cmd, 0, True)
WScript.Quit rc
