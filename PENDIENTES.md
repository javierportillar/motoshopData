# Pendientes del humano

> Lista priorizada de tareas que tiene que ejecutar **Javier** entre sesiones del agente. Cosas que el agente **no puede hacer** (tocan sgHermes, la red local, cuentas externas, decisiones de negocio) o que requieren confirmación humana.
>
> **Convención:** cada sesión añade un bloque nuevo arriba. Los pendientes resueltos se marcan ✅ pero **no se borran** — quedan como historial. Cuando algo cambia de prioridad o se vuelve obsoleto, se reescribe y se anota el motivo.

**Leyenda:** ⬜ pendiente · 🟡 en progreso · ✅ hecho · 🔴 bloqueado · ❌ descartado

---

## Sesión 2026-05-27 · Cierre de andamiaje F0

### 1. ⬜ Revisar y confirmar/ajustar P1–P4 *(bloquea F0 → F1)*

Leer los 4 ADRs propuestos y responder al agente con un OK o con los ajustes que quieras. Mis recomendaciones:

| # | ADR | Recomendación |
|---|-----|----------------|
| P1 | [0005 · Conectividad Databricks ↔ MySQL](docs/decisions/0005-databricks-mysql-connectivity.md) | **A** · self-hosted dump → cloud storage |
| P2 | [0006 · Túnel remoto](docs/decisions/0006-remote-tunnel.md) | **A** · Cloudflare Tunnel |
| P3 | [0007 · Hosting de la API](docs/decisions/0007-api-hosting.md) | **A** · PC local |
| P4 | [0008 · Provider de auth](docs/decisions/0008-auth-provider.md) | **A** · login propio (JWT + bcrypt) |

> *Cuando confirmes, el agente cambia el estado de los ADRs a `Accepted` y lo refleja en [SEGUIMIENTO.md](SEGUIMIENTO.md).*

---

### 2. ⬜ Ejecutar el backup del MySQL *(verificación crítica #6 de F0)*

Desde el PC Windows donde corre `motoshop2024` (o desde donde tengas acceso a la BD):

```bash
cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
MOTOSHOP_BACKUP_DIR=~/Backups/motoshop ./infra/backup_mysql.sh
```

**Reportar al agente:** tamaño del archivo y duración (los imprime el script al final). Se anotan en [SEGUIMIENTO.md → Fase 0 → Métricas mínimas](SEGUIMIENTO.md#métricas-mínimas).

> *Si estás en Windows y no tienes bash, el equivalente con PowerShell se puede armar — avísale al agente y te lo escribe.*

---

### 3. ⬜ Probar que el scaffold corre *(opcional, valida los `⚠️` de F0)*

**API (FastAPI):**
```bash
cd motoshop-app/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn motoshop_api.main:app --reload --port 8000
# abrir http://localhost:8000/health  →  {"status":"ok",...}
```

**Web (Next.js):**
```bash
cd motoshop-app/web
npm install
cp .env.local.example .env.local
npm run dev
# abrir http://localhost:3000
```

**Reportar al agente:** si todo arranca, se marcan ✅ los dos entregables `⚠️` de F0. Si algo falla, pasar el error.

---

### 4. ⬜ Crear usuarios MySQL read-only *(requiere P1 resuelto)*

Toca sgHermes, por eso lo haces tú. El agente te pasa los `CREATE USER` exactos en cuanto confirmes P1 (define si `analytics` se conecta vía túnel directo o solo necesitamos `api_read`).

Plan tentativo:
- `analytics@%` — read-only para Databricks (si P1 = B) **o** no necesario (si P1 = A).
- `api_read@localhost` — read-only para la API FastAPI.

Ambos con contraseña fuerte guardada en el password manager (NO en el repo).

---

### 5. ⬜ Crear cuenta/workspace Databricks

- Crear cuenta (Free / Community para arrancar es suficiente).
- Crear catálogo `motoshop` en Unity Catalog con esquemas `bronze`, `silver`, `gold`.
- Generar un Personal Access Token (PAT) y guardarlo en el password manager.
- Pasar al agente: **host** del workspace (URL) y confirmar que el PAT está disponible (sin enviarlo por chat).

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
