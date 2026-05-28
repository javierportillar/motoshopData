# Rotación de contraseñas MySQL · cierre F0

> El `create_users.sql.example` original tenía la contraseña real (`123450`) committeada en el repo público. Esto viola la **Regla de Oro #2** (credenciales fuera de Git). Aunque los 3 usuarios son `@localhost` y el puerto 3306 no está expuesto por el túnel, hay que rotar **antes** de cerrar F0.

## Pasos para Javier (PC Windows, 5 minutos)

### 1 · Generar 3 contraseñas fuertes

Una opción rápida en PowerShell:

```powershell
# Genera 3 contraseñas de 24 caracteres alfanuméricos
1..3 | ForEach-Object { -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_}) }
```

O en la web: [1password password generator](https://1password.com/password-generator/) / [bitwarden password generator](https://bitwarden.com/password-generator/).

**Guárdalas en tu password manager** antes de seguir.

### 2 · Aplicar las rotaciones

```powershell
# Reemplaza <NEW_*> por las contraseñas generadas. NO copies este bloque tal cual.
mysql -u root -e "SET PASSWORD FOR 'analytics'@'localhost' = PASSWORD('<NEW_ANALYTICS>'); SET PASSWORD FOR 'api_read'@'localhost' = PASSWORD('<NEW_API_READ>'); SET PASSWORD FOR 'javier'@'localhost' = PASSWORD('<NEW_JAVIER>'); FLUSH PRIVILEGES;"
```

> MySQL 5.0 usa `SET PASSWORD FOR ... = PASSWORD('<plaintext>')`. En MySQL 5.7+ se usaría `ALTER USER`. Para 5.0 esto es lo correcto.

### 3 · Actualizar los `.env` locales

Hay 3 archivos `.env` en el PC (gitignored). Cambiar `MYSQL_PASSWORD=` con la nueva contraseña que corresponda:

| Archivo | Usuario | Para |
|---------|---------|------|
| `.env` (raíz del repo) | `analytics` | Script `dump_to_cloud.py` |
| `motoshop-app/api/.env` | `api_read` | API FastAPI |
| `motoshop-app/web/.env.local` | (no usa MySQL) | — |

### 4 · Verificar que la API y el script siguen funcionando

```powershell
# API
cd motoshop-app\api
.\.venv\Scripts\Activate.ps1
pytest    # debe seguir verde
uvicorn motoshop_api.main:app --reload --port 8000
# Probar http://localhost:8000/health  (no toca MySQL todavía pero debe arrancar)

# Conectividad
cd ..\..
python infra\test_mysql_connectivity.py   # debe seguir devolviendo SELECT 1 -> 1
```

### 5 · Reportar al agente

Confirmar que los 4 pasos pasaron, sin compartir las contraseñas nuevas. El agente marca **verificación crítica F0 limpia**.

---

## Para el futuro

- Las contraseñas NUNCA vuelven a aparecer en archivos trackeados. Solo en `.env` locales y en el password manager.
- Si en algún momento se sube `motoshop2024` a una instancia con IP pública (F-F del roadmap), antes hay que rotar **otra vez** y restringir los usuarios a IPs específicas, no `@localhost`.
- El `infra/create_users.sql.example` versionado solo tiene placeholders. Cualquier archivo `infra/create_users.sql` (sin `.example`) está en `.gitignore` para evitar que se commitee por accidente.
