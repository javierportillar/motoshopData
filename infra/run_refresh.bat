@echo off
REM MotoShop V1.5 - Daily Refresh Pipeline
REM Corre: pipeline → upload R2 → refresh API
REM Si el DuckDB ya se generó hoy, saltea pipeline y upload (solo refresh).

cd /d "%~dp0.."
set PYTHONPATH=%CD%

REM Verificar si ya se corrió hoy (DuckDB actualizado hoy?)
for /f %%i in ('dir /b out\motoshop_gold.duckdb 2^>nul') do set TODAY=yes
if defined TODAY (
    REM Ver si el archivo tiene fecha de hoy
    for /f %%t in ('dir /tc /a-d out\motoshop_gold.duckdb 2^>nul ^| find "%DATE:~0,10%"') do set FRESH=yes
)

if not defined FRESH (
    echo [1/3] Running pipeline...
    .venv-infra\Scripts\python.exe pipeline\run_all.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Pipeline failed with exit code %ERRORLEVEL%
        exit /b %ERRORLEVEL%
    )
    echo [OK] Pipeline completed

    echo [2/3] Uploading DuckDB to R2...
    .venv-infra\Scripts\python.exe scripts\upload_duckdb_to_r2.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Upload failed with exit code %ERRORLEVEL%
        exit /b %ERRORLEVEL%
    )
    echo [OK] Upload successful
) else (
    echo [SKIP] Pipeline y upload ya se ejecutaron hoy. Solo refresh.
)

echo [3/3] Refreshing API...
powershell -ExecutionPolicy Bypass -File "infra\refresh_v15.ps1" -ApiBaseUrl "http://localhost:8000"
if %ERRORLEVEL% neq 0 (
    echo [WARN] API refresh failed (puede que la API no esté corriendo)
)
echo [OK] All done!
