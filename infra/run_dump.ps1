# run_dump.ps1 — RENOMBRADO a motoshop_dump_to_cloud.ps1
# Por favor actualizá el Task Scheduler de Windows para que apunte a:
#   C:\Users\MotoShop\Documents\javidevmoto\infra\motoshop_dump_to_cloud.ps1

Write-Host "⚠️  run_dump.ps1 ha sido renombrado a motoshop_dump_to_cloud.ps1"
Write-Host "   Redirigiendo al nuevo nombre..."

# Redirigir al nuevo script
& "$PSScriptRoot\motoshop_dump_to_cloud.ps1"
exit $LASTEXITCODE
