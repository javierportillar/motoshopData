' Lanza un script de PowerShell sin ninguna ventana visible.
'
' Uso (asi lo invocan las tareas programadas):
'   wscript.exe "C:\...\infra\run_hidden.vbs" "C:\...\script.ps1" [arg1 arg2 ...]
'
' Por que existe: cuando la tarea ejecuta powershell.exe directamente, aunque sea
' con -WindowStyle Hidden, Windows crea la consola un instante y se ve un parpadeo
' cada vez que corre. Con el host wscript y la ventana 0 del Run no se crea nunca.
' El llamador espera (True) y hereda el codigo de salida del script.
Option Explicit

Dim fso, shell, script, cmd, i, extra, code

If WScript.Arguments.Count < 1 Then
  WScript.Quit 2
End If

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

script = WScript.Arguments(0)
If Not fso.FileExists(script) Then
  WScript.Quit 3
End If

extra = ""
For i = 1 To WScript.Arguments.Count - 1
  extra = extra & " " & WScript.Arguments(i)
Next

cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & script & """" & extra
code = shell.Run(cmd, 0, True)

WScript.Quit code
