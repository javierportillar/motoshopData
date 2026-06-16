Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -File C:\Users\MotoShop\Documents\javidevmoto\motoshopData\infra\run_dump.ps1", 0, True
