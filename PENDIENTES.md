# Pendientes del humano

> Lista priorizada de tareas que tiene que ejecutar **Javier** entre sesiones del agente. Cosas que el agente **no puede hacer** (tocan sgHermes, la red local, cuentas externas, decisiones de negocio) o que requieren confirmación humana.
>
> **Convención:** cada sesión añade un bloque nuevo arriba. Los pendientes resueltos se marcan ✅ pero **no se borran** — quedan como historial. Cuando algo cambia de prioridad o se vuelve obsoleto, se reescribe y se anota el motivo.

**Leyenda:** ⬜ pendiente · 🟡 en progreso · ✅ hecho · 🔴 bloqueado · ❌ descartado

---

## Sesión 2026-05-28 (8) · Remediación de auditoría — 1 acción para cerrar F0

### Resumen
La auditoría detectó dos cosas en el cierre anterior: (a) el commit de cierre filtró la nueva password en su mensaje (**deuda aceptada** — no se va a corregir, ver R1 en SEGUIMIENTO), y (b) el smoke test atestó la verificación #3 con `sucursales` que tenía 0 filas, lo cual no demuestra movimiento de datos. Esta acción cierra (b).

El agente preparó: notebook SQL ejecutable en SQL Warehouse, scripts reproducibles del Volume y del Warehouse, deuda de credenciales documentada como riesgo vivo.

### 1. ⬜ Re-ejecutar el smoke test con una tabla con datos *(bloquea cierre F0)*

**Por qué:** `sucursales` salió con 0 filas. El gate pide *"aunque sea con 10 filas"*. Hay que elegir una tabla pequeña pero **no vacía**. Candidatas:
- `bodegas` (~10 filas, recomendado — modelo mental directo)
- `formapago` (~20 filas — códigos de pago)
- `subproduct` (~? filas — alternativa)

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
.\.venv-infra\Scripts\Activate.ps1

# Dump de las dos tablas pequeñas a Parquet local + UC Volume
python infra\dump_to_cloud.py --tables bodegas formapago
# El script imprime: filas, tamaño, ruta del Volume. Copiá esa salida.
```

**En Databricks (SQL Editor del SQL Warehouse):**

1. Importar/abrir [`notebooks/bronze/01_ingest_smoke_test.sql`](notebooks/bronze/01_ingest_smoke_test.sql) (o pegar las celdas en un nuevo notebook SQL).
2. Setear los widgets:
   - `table_name = bodegas`
   - `ingest_date = <la fecha del dump>` (por defecto hoy)
3. **Run all.**
4. La última celda 5 (validación) debe devolver:
   ```
   ✅ OK — conteos cuadran y N > 0 (verif. #3 cumplida)
   ```
5. Repetir el run con `table_name = formapago` para confirmar que el patrón funciona en >1 tabla.

### 2. ⬜ Capturar la evidencia en el repo *(2 minutos)*

Crear `notebooks/bronze/_runs/smoke_test_2026-05-28.md` con este contenido base (rellenar valores reales):

```markdown
# Smoke test bronze · 2026-05-28

## bodegas (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## formapago (ingest_date=2026-05-28)
- Dump local: N filas, X KB, Y segundos
- Subida UC Volume: ok
- COUNT(*) parquet:  N
- COUNT(*) bronze:   N
- Verdict: ✅ OK — conteos cuadran y N > 0

## DESCRIBE HISTORY motoshop.bronze.bodegas (5 últimas operaciones)
| version | timestamp | operation        | userName |
|---------|-----------|------------------|----------|
| ...     | ...       | CREATE_OR_REPLACE| ...      |
```

Commit:
```powershell
git add notebooks/bronze/_runs/smoke_test_2026-05-28.md
git commit -m "feat(F0): evidencia smoke test bronze - bodegas y formapago N>0"
git push
```

### 3. Reportar al agente
"Smoke test honesto pasó: bodegas N=X, formapago N=Y, evidencia en `notebooks/bronze/_runs/smoke_test_2026-05-28.md`." El agente marca verificación #3 a ✅, F0 cierra (con #5 como ⚠️ documentado por deuda aceptada), y abre F1.

---

### (Opcional, complementarias) Scripts reproducibles ya en el repo

Si querés re-correr el setup desde cero en otra máquina, ahora hay scripts versionados que reemplazan los clicks de la UI:

```powershell
python infra\create_uc_volume.py        # crea (o verifica) motoshop.bronze._landing
python infra\create_sql_warehouse.py    # crea (o verifica) auto_stop_mins ≤ 10
```

Ambos son idempotentes y validan permisos. La sesión 7 los hizo manualmente; estos scripts dejan el trabajo reproducible para auditoría académica y para F-F del roadmap.

---

## Sesión 2026-05-28 · Cierre estricto de F0 (auditoría)

### Resumen
Auditoría de la entrega F0 detectó **2 violaciones de gate** y **1 ⚠️ de compute** que la metodología obliga a cerrar antes de abrir F1. El agente preparó todo el código y la documentación; faltan **4 acciones humanas** en el PC para sellar el cierre.

> Si todo lo de abajo pasa ✅, F0 queda cerrado limpio y arrancamos F1.

### 1. ✅ Rotar contraseñas MySQL *(violación Regla de Oro #2)*

El `infra/create_users.sql.example` versionado tenía la contraseña real (`123450`). Aunque los 3 usuarios son `@localhost`, esto es deuda pública en GitHub. Pasos detallados en [infra/rotate_mysql_passwords.md](infra/rotate_mysql_passwords.md):

1. Generar 3 contraseñas de 24 caracteres con PowerShell (snippet en el doc).
2. Aplicar `SET PASSWORD FOR ... = PASSWORD('<nueva>')` para los 3 usuarios.
3. Actualizar `MYSQL_PASSWORD=` en los 3 `.env` locales.
4. Verificar: `pytest` en la API + `python infra/test_mysql_connectivity.py`.

**Reportar al agente:** "passwords rotados, todo verde" — sin compartir las contraseñas.

---

### 2. ✅ Crear el UC Volume de aterrizaje *(una vez)*

Pasos en [infra/setup_uc_volume.md](infra/setup_uc_volume.md). Desde el SQL Editor del workspace Databricks:

```sql
CREATE VOLUME IF NOT EXISTS motoshop.bronze._landing
  COMMENT 'Staging de Parquet subidos por dump_to_cloud.py (Track A · F1)';
```

**Reportar al agente:** confirmar que aparece en Catalog Explorer bajo `motoshop > bronze > _landing`.

---

### 3. ✅ Configurar SQL Warehouse con autoapagado 10 min *(verificación F0 #4)*

En el workspace:

1. **SQL → Warehouses → Create SQL Warehouse.**
2. Tamaño: el más pequeño disponible (en Free Edition, "Starter").
3. **Auto stop:** 10 minutos.
4. Permisos: el PAT actual debe poder ejecutarlo.

**Reportar al agente:** capturar el setting de auto-stop (screenshot o copy del valor). Eso cierra la verificación crítica #4.

---

### 4. ✅ Ejecutar el pipeline real Databricks ↔ MySQL *(verificación F0 #3)*

Esto es lo que de verdad sella la verificación #3 (la que el smoke test sintético no cumplía).

**En el PC Windows:**

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
python -m venv .venv-infra
.\.venv-infra\Scripts\Activate.ps1
pip install -r infra\requirements.txt

# Smoke test: 1 tabla, sin subir a Databricks
python infra\dump_to_cloud.py --tables sucursales --dry-run
# → genera _staging/sucursales/ingest_date=YYYY-MM-DD/part-0.parquet

# Smoke test completo: sube al UC Volume
python infra\dump_to_cloud.py --tables sucursales
# → sube al Volume + genera _staging/manifest_YYYY-MM-DD.json
```

**En Databricks (workspace UI):**

5. Importar `notebooks/bronze/01_ingest_smoke_test.py` (o ya está sincronizado si conectaste el repo en la tarea 5 de la sesión anterior).
6. Ejecutar el notebook con el SQL Warehouse pequeño o con serverless compute.
7. La última celda debe imprimir: `✅ Smoke test OK · verificación crítica #3 de F0 cumplida`.

**Reportar al agente:** copia del output de la celda 4 (los conteos coinciden) o screenshot del notebook completo. Esto cierra la verificación #3.

---

### 5. ⬜ (Opcional) Conectar el repo al workspace Databricks

Para que los notebooks se editen en Databricks UI y se versionen en GitHub:

1. **Workspace → User Settings → Linked accounts → GitHub.**
2. Conectar `javierportillar/motoshopData`.
3. **Repos → Add Repo → seleccionar el repo conectado.**
4. Trabajar los notebooks dentro de esa carpeta de `Repos/`.

No es bloqueante para cerrar F0 — se puede ejecutar el notebook importándolo manualmente — pero es lo "limpio".

---

### ✅ Fase 0 cerrada

Las 4 acciones se completaron en la sesión del 2026-05-28. Verificaciones #3, #4, #5 pasan a ✅. Fase 0 cerrada. Pasamos a Fase 1.

---

## Sesión 2026-05-27 · Decisiones P1–P4 aceptadas

### Resumen de esta sesión
- ✅ P1–P4 revisados y aceptados (recomendaciones confirmadas sin cambios)
- ✅ ADRs 0005–0008 actualizados a `Accepted`
- ✅ Script PowerShell `infra/backup_mysql.ps1` generado (alternativa Windows)
- ✅ SQL `infra/create_users.sql.example` generado con usuarios `analytics` y `api_read`
- ✅ Backup MySQL ejecutado (5.02MB, 7s)
- ✅ Usuarios MySQL creados: analytics, api_read, javier
- ➡️ Pendiente: cuenta Databricks, Cloudflare Tunnel, probar scaffolds

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

### 4. ✅ Crear usuarios MySQL read-only

Usuarios creados: `analytics`, `api_read`, `javier` (todos @localhost, password `123450`).
Verificación crítica #1 ✅ — INSERT command denied para los 3.

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
