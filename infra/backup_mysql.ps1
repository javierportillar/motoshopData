<#
.SYNOPSIS
  Backup de la BD motoshop2024 (MySQL 5.0, MyISAM) en Windows.
  Verificacion critica #6 de Fase 0.
.DESCRIPTION
  Ejecuta mysqldump y comprime con gzip. El destino debe estar FUERA del repo.
  Imprime tamano y duracion para anotar en SEGUIMIENTO.md.
.PARAMETER BackupDir
  Directorio donde guardar el backup. Default: ~\Backups\motoshop
.PARAMETER Host
  Host de MySQL. Default: localhost
.PARAMETER Port
  Puerto de MySQL. Default: 3306
.PARAMETER User
  Usuario de MySQL. Default: root
.PARAMETER Password
  Contrasena de MySQL. Default: vacio
.PARAMETER Database
  Base de datos. Default: motoshop2024
.EXAMPLE
  .\infra\backup_mysql.ps1 -BackupDir "$env:USERPROFILE\Backups\motoshop"
#>

param(
  [string]$BackupDir = (Join-Path $env:USERPROFILE "Backups\motoshop"),
  [string]$MySQLHost = "localhost",
  [int]$Port = 3306,
  [string]$User = "root",
  [string]$Password = "",
  [string]$Database = "motoshop2024"
)

if (-not (Get-Command mysqldump -ErrorAction SilentlyContinue)) {
  Write-Error "mysqldump no encontrado. Verifica que MySQL este en el PATH."
  exit 1
}

if (-not (Test-Path $BackupDir)) {
  New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutFile = Join-Path $BackupDir "${Database}_${Timestamp}.sql.gz"

Write-Host "Origen:  $User@$MySQLHost`:$Port/$Database"
Write-Host "Destino: $OutFile"

$mysqldumpArgs = @(
  "--host=$MySQLHost"
  "--port=$Port"
  "--user=$User"
  "--lock-tables"
  "--routines"
  "--triggers"
  "--default-character-set=utf8"
  $Database
)

if ($Password) {
  $mysqldumpArgs += "--password=$Password"
}

$Start = Get-Date

Write-Host "Iniciando mysqldump..."

# mysqldump via temp file, capturing both stdout and stderr
$tempFile = Join-Path $env:TEMP "motoshop_dump_$([System.Guid]::NewGuid().ToString('N')).sql"
Write-Host "Ejecutando: mysqldump --host=$MySQLHost --port=$Port --user=$User [password oculto] --lock-tables --routines --triggers $Database"
$result = & mysqldump @mysqldumpArgs 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
  Write-Host "`nERROR de mysqldump ($exitCode):"
  $result | ForEach-Object { Write-Host "  $_" }
  exit 2
}
# guardar dump en archivo (excluyendo stderr)
$result | Where-Object { $_ -is [string] } | Out-File -FilePath $tempFile -Encoding utf8
if (-not (Test-Path $tempFile) -or ((Get-Item $tempFile).Length -eq 0)) {
  Write-Error "No se creo el archivo de dump o esta vacio"
  exit 3
}

Write-Host "Dump completado ($((Get-Item $tempFile).Length) bytes). Comprimiendo..."

# compress
$compressOk = $false
if (Get-Command gzip -ErrorAction SilentlyContinue) {
  $gzOut = & gzip -9 -c $tempFile 2>&1
  $gzExit = $LASTEXITCODE
  if ($gzExit -eq 0) {
    [System.IO.File]::WriteAllBytes($OutFile, [System.Text.Encoding]::UTF8.GetBytes($gzOut))
    $compressOk = $true
  } else {
    Write-Host "gzip fallo (codigo $gzExit), usando fallback .NET..."
  }
}
if (-not $compressOk) {
  Write-Host "Usando compresion nativa .NET (GZipStream)..."
  $zipFile = [System.IO.Path]::ChangeExtension($OutFile, ".zip")
  $fsIn = [System.IO.File]::OpenRead($tempFile)
  $fsOut = [System.IO.File]::Create($zipFile)
  $gzs = New-Object System.IO.Compression.GZipStream $fsOut, ([System.IO.Compression.CompressionMode]::Compress)
  $fsIn.CopyTo($gzs)
  $gzs.Close(); $fsOut.Close(); $fsIn.Close()
  $OutFile = $zipFile
}
Remove-Item $tempFile

$End = Get-Date
$Duration = [math]::Round(($End - $Start).TotalSeconds, 0)
$Size = [math]::Round((Get-Item $OutFile).Length / 1MB, 2)

Write-Host "Tamano:   ${Size}MB"
Write-Host "Duracion: ${Duration}s"

# verify integrity for gz files
if ($OutFile -like "*.gz" -and (Get-Command gzip -ErrorAction SilentlyContinue)) {
  Write-Host "Verificando integridad..."
  $null = & gzip -t $OutFile 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "OK - integridad verificada"
  } else {
    Write-Host "Advertencia: fallo verificacion de integridad"
  }
}

Write-Host ""
Write-Host "Backup completado. Anotar en SEGUIMIENTO.md (F0, metrica de backup):"
Write-Host "  archivo:  $OutFile"
Write-Host "  tamano:   ${Size}MB"
Write-Host "  duracion: ${Duration}s"
