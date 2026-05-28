# Pendientes del humano

> Lista priorizada de tareas que tiene que ejecutar **Javier** entre sesiones del agente. Cosas que el agente **no puede hacer** (tocan sgHermes, la red local, cuentas externas, decisiones de negocio) o que requieren confirmación humana.
>
> **Convención:** cada sesión añade un bloque nuevo arriba. Los pendientes resueltos se marcan ✅ pero **no se borran** — quedan como historial. Cuando algo cambia de prioridad o se vuelve obsoleto, se reescribe y se anota el motivo.

**Leyenda:** ⬜ pendiente · 🟡 en progreso · ✅ hecho · 🔴 bloqueado · ❌ descartado

---

## Sesión 2026-05-27 · Decisiones P1–P4 aceptadas

### Resumen de esta sesión
- ✅ P1–P4 revisados y aceptados (recomendaciones confirmadas sin cambios)
- ✅ ADRs 0005–0008 actualizados a `Accepted`
- ✅ Script PowerShell `infra/backup_mysql.ps1` generado (alternativa Windows)
- ✅ SQL `infra/create_users.sql` generado con usuarios `analytics` y `api_read`
- ➡️ Pendiente: ejecutar backup, crear usuarios, Databricks, Cloudflare Tunnel, probar scaffolds

---

## Sesión 2026-05-27 · Cierre de andamiaje F0

### 1. ✅ Revisar y confirmar/ajustar P1–P4 *(bloquea F0 → F1)*

Los 4 ADRs fueron aceptados con las recomendaciones originales:
- P1 → **A** · Self-hosted dump → cloud storage
- P2 → **A** · Cloudflare Tunnel
- P3 → **A** · PC local
- P4 → **A** · Login propio (JWT + bcrypt)

---

### 2. ✅ Ejecutar el backup del MySQL *(verificación crítica #6 de F0)*

Desde PowerShell (como Administrador) en el PC donde corre `motoshop2024`:

```powershell
# Asegúrate de que mysqldump está en el PATH
# o ejecuta desde: C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin\
cd C:\Users\MotoShop\Documents\javidevmoto
.\infra\backup_mysql.ps1 -BackupDir "$env:USERPROFILE\Backups\motoshop"
```

> Si `mysqldump` no está en el PATH, usa la ruta completa:
> ```powershell
> $env:PATH += ";C:\Program Files (x86)\MySQL\MySQL Server 5.0\bin"
> .\infra\backup_mysql.ps1
> ```

**Reportar al agente:** tamaño y duración (los imprime el script al final).

---

### 3. ⬜ Probar que el scaffold corre *(opcional, valida los `⚠️` de F0)*

**API (FastAPI):**
```powershell
cd motoshop-app/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn motoshop_api.main:app --reload --port 8000
# abrir http://localhost:8000/health  →  {"status":"ok",...}
```

**Web (Next.js):**
```powershell
cd motoshop-app/web
npm install
copy .env.local.example .env.local
npm run dev
# abrir http://localhost:3000
```

**Reportar al agente:** si todo arranca, se marcan ✅ los dos entregables `⚠️` de F0. Si algo falla, pasar el error.

---

### 4. ⬜ Crear usuarios MySQL read-only

Con P1 = A (dump local), ambos usuarios son `@localhost`:

```sql
-- 1. Reemplazar 'changeme_analytics' y 'changeme_api' por contraseñas seguras
-- 2. Guardarlas en el password manager
-- 3. Ejecutar como root:
mysql -u root < infra\create_users.sql.example
```

**Verificación crítica #1 de F0:** Probar que INSERT/UPDATE/DELETE fallan:
```sql
mysql -u analytics -p -e "INSERT INTO motoshop2024.productos (codprod) VALUES ('test')"
-- debe dar: ERROR 1142 (42000): INSERT command denied...
```

---

### 5. ⬜ Crear cuenta/workspace Databricks

- Crear cuenta en https://databricks.com (Free / Community tier para arrancar).
- Crear catálogo `motoshop` en Unity Catalog con esquemas `bronze`, `silver`, `gold`.
- Generar un Personal Access Token (PAT) y guardarlo en el password manager.
- Pasar al agente: **host** del workspace (URL) y confirmar que el PAT está disponible (sin enviarlo por chat).
- Después de esto, el agente podrá escribir el primer notebook bronze.

---

### 6. ⬜ Configurar el remoto GitHub para CI *(diferible)*

El repo ya está en [github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData). Cuando quieras meter CI:

- Decidir si se mantiene como repo público o se hace privado.
- Confirmar al agente para que escriba `.github/workflows/ci.yml` con ruff + pytest + (más adelante) lint del frontend y typecheck.

---

## Cómo se usa este archivo

- **Al inicio de cada sesión** el agente lo lee y prioriza según lo que esté ⬜.
- **Al cierre de cada sesión** el agente añade un nuevo bloque arriba con los pendientes nuevos generados y marca ✅ los que se resolvieron desde la sesión anterior.
- **Tú** marcas ✅ tú mismo cuando completes algo, o se lo dices al agente y él lo actualiza.
- **Histórico:** los bloques de sesiones pasadas no se borran. Sirven como rastro de qué se pidió y cuándo se cerró.
