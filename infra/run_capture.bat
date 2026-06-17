@echo off
REM V1.9 - Incremental Sales Capture (multi-tenant)
REM Corre cada ~2 minutos en horario comercial.
REM Busca ventas nuevas en MySQL, las inserta en silver, rebuild gold, sube a R2, refresh API.
REM
REM Uso:
REM   run_capture.bat [tenant]
REM   tenant: motoshop (default) | masvital

set TENANT=%~1
if "%TENANT%"=="" set TENANT=motoshop

cd /d "%~dp0.."
set PYTHONPATH=%CD%

REM Log file for debugging
set LOG_DIR=out\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set LOGFILE=%LOG_DIR%\capture_%TENANT%.log

echo [%DATE% %TIME%] === Starting capture for %TENANT% === >> "%LOGFILE%"

REM Cargar .env (variables: MYSQL_*, DUCKDB_PATH, R2_*, REFRESH_TOKEN, API_BASE_URL)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

set TENANT=%TENANT%
.venv-infra\Scripts\python.exe scripts\capture_new_sales.py >> "%LOGFILE%" 2>&1
set EXITCODE=%ERRORLEVEL%
echo [%DATE% %TIME%] Exit code: %EXITCODE% >> "%LOGFILE%"
echo ======================================== >> "%LOGFILE%"
exit /b %EXITCODE%
