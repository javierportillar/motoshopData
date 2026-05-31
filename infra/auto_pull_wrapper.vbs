Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -NoProfile -NonInteractive -File C:\Users\MotoShop\Documents\javidevmoto\infra\auto_pull_and_apply.ps1", 0, True
