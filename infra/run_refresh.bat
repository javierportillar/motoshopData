@echo off
REM V1.5 - Daily Refresh Pipeline (multi-tenant)
REM Corre: pipeline -> upload R2 -> refresh API
REM Si el DuckDB ya se generó hoy, saltea pipeline y upload (solo refresh).
REM
REM Uso:
REM   run_refresh.bat [tenant]
REM   tenant: motoshop (default) | masvital

set TENANT=%~1
if "%TENANT%"=="" set TENANT=motoshop

cd /d "%~dp0.."
set PYTHONPATH=%CD%

REM Verificar si ya se corrió hoy (DuckDB actualizado hoy?)
set DUCKDB_FILE=out\%TENANT%_gold.duckdb
for /f %%i in ('dir /b "%DUCKDB_FILE%" 2^>nul') do set TODAY=yes
if defined TODAY (
    for /f %%t in ('dir /tc /a-d "%DUCKDB_FILE%" 2^>nul ^| find "%DATE:~0,10%"') do set FRESH=yes
)

if not defined FRESH (
    echo [1/3] Running pipeline for %TENANT%...
    REM Cargar variables del .env para MySQL, R2, API, etc.
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
    set TENANT=%TENANT%
    .venv-infra\Scripts\python.exe pipeline\run_all.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Pipeline failed with exit code %ERRORLEVEL%
        exit /b %ERRORLEVEL%
    )
    echo [OK] Pipeline completed for %TENANT%

    echo [2/3] Uploading %TENANT% DuckDB to R2...
    set TENANT=%TENANT%
    .venv-infra\Scripts\python.exe scripts\upload_duckdb_to_r2.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Upload failed with exit code %ERRORLEVEL%
        exit /b %ERRORLEVEL%
    )
    echo [OK] Upload successful for %TENANT%
) else (
    echo [SKIP] Pipeline y upload ya se ejecutaron hoy para %TENANT%. Solo refresh.
)

echo [3/3] Refreshing API...
powershell -ExecutionPolicy Bypass -File "infra\refresh_v15.ps1" -ApiBaseUrl "https://api.fragloesja.uk" -Tenant "%TENANT%"
if %ERRORLEVEL% neq 0 (
    echo [WARN] API refresh failed (puede que la API no esté corriendo)
)
echo [OK] All done for %TENANT%!
