@echo off
REM MotoShop V1.9 - Incremental Sales Capture
REM Corre cada ~2 minutos entre 17:50 y 23:59 COL
REM Busca ventas nuevas en MySQL, las inserta en silver, rebuild gold, sube a R2, refresh API.

cd /d "%~dp0.."
set PYTHONPATH=%CD%

REM Cargar .env (variables: MYSQL_*, DUCKDB_PATH, R2_*, REFRESH_TOKEN, API_BASE_URL)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

.venv-infra\Scripts\python.exe scripts\capture_new_sales.py
exit /b %ERRORLEVEL%
