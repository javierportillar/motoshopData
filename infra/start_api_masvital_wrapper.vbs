' start_api_masvital_wrapper.vbs -- arranca la API del nodo MasVital sin ventana visible.
'
' La tarea programada MasVitalBackendService apunta a este archivo (wscript).
' Run(..., 0, True) = ventana oculta y esperar: no queda ningun CMD, PowerShell ni
' consola de Python en pantalla.
'
' La ruta del .ps1 se resuelve desde la ubicacion del propio .vbs: el repo se puede
' mover o clonar en otro nodo sin editar rutas absolutas.

Dim fso, shell, carpeta, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
script = carpeta & "\start_api_masvital.ps1"

If Not fso.FileExists(script) Then
  WScript.Quit 1
End If

shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """", 0, True
