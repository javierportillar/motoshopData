# Configurar Cloudflare Tunnel (P2 · Opción A)

## Requisitos
- Cuenta Cloudflare (gratis en https://dash.cloudflare.com)
- PC Windows con la API FastAPI corriendo en `localhost:8000`

## Pasos

### 1. Instalar cloudflared
```powershell
# Descargar e instalar cloudflared
winget install cloudflare.cloudflared
```
O descargar manualmente de: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

### 1b. Agregar al PATH (solo si winget no lo dejó en el PATH)
```powershell
# Si al escribir cloudflared dice que no se reconoce, usa la ruta completa:
$env:PATH += ";$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe"
```
O ejecuta los comandos con la ruta completa:
```powershell
& "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe" tunnel login
```

### 2. Autenticar
```powershell
cloudflared tunnel login
```
Se abre el navegador. Inicia sesión en Cloudflare y selecciona tu dominio (o crea uno gratis).

### 3. Crear el túnel
```powershell
cloudflared tunnel create motoshop-api
```
Guarda el **token** que aparece (se ve una sola vez).

### 4. Configurar el servicio
```powershell
cloudflared service install <TOKEN_DEL_TUNEL>
```
Esto deja el túnel corriendo como servicio de Windows (arranque automático).

### 5. Probar
La API queda expuesta en una URL como:
```
https://motoshop-api.<tu-dominio>.trycloudflare.com
```
o en un subdominio propio si configuras DNS.

### 6. Verificar
```powershell
curl https://<URL_DEL_TUNEL>/health
# → {"status":"ok","version":"0.0.0","env":"dev"}
```

## Token seguro
El token del túnel se guarda en `.env`:
```
CLOUDFLARE_TUNNEL_TOKEN=<token>
```
NUNCA en Git.
