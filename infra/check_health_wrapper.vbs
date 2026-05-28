Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -File C:\Users\MotoShop\Documents\javidevmoto\infra\check_health.ps1", 0, True
