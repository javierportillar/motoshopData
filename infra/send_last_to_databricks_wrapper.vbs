Set objShell = CreateObject("WScript.Shell")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -NoProfile -NonInteractive -File C:\Users\MotoShop\Documents\javidevmoto\infra\send_last_to_databricks.ps1", 0, True
