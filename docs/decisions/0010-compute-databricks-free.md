# ADR-0010 · Compute en Databricks Free Edition

- **Estado:** Accepted
- **Fecha:** 2026-05-28
- **Bloquea:** F0 (verificación crítica #4) y F1 (toda la ingesta)
- **Decide:** Humano, con recomendación del agente

## Contexto

Al crear el workspace Databricks se descubrió que la **Free Edition** no incluye clusters de propósito general tradicionales. Lo que ofrece es:

- **Serverless SQL Warehouses** con autoapagado configurable (10 min, 1 h, etc.).
- **Serverless notebooks** (Python/SQL) con tiempo limitado mensual.
- **Unity Catalog completo** (catálogos, esquemas, volúmenes, linaje).
- **Workflows** programados ejecutables contra serverless.
- **Delta Lake / MLflow** disponibles.

Lo que **no** está disponible:

- Clusters all-purpose ni job clusters dimensionables.
- `mysql-connector-java` JDBC desde Databricks contra un MySQL fuera del workspace (no hay forma de instalar drivers JDBC en serverless de Free).

Esto afecta directamente a la pregunta del gate F0 #4 ("¿el cluster se apaga solo?") y a F1 entera (ingesta).

## Opciones consideradas

### A · Extracción en PC local → Parquet → UC Volume; transformaciones en Databricks Serverless *(recomendado)*

- El PC corre un script Python (`infra/dump_to_cloud.py`) que lee tablas vía `mysql-connector-python`, escribe Parquet local, y sube a un **Unity Catalog Volume** (`/Volumes/motoshop/bronze/_landing/`) con `databricks fs cp` o el SDK.
- Databricks (serverless notebook) lee el Parquet del volume y escribe a `motoshop.bronze.<tabla>` particionado por `ingest_date`. Cero conexión Databricks → MySQL.
- Workflow programado nocturno orquesta el paso 2 (el paso 1 se programa en el PC con Task Scheduler de Windows).
- **Pros:** funciona en Free Edition tal cual; consistente con D5 (Opción A); el camino crítico no depende de drivers JDBC; el upload se beneficia del CDN de Cloudflare/Databricks.
- **Contras:** dos puntos de orquestación (PC + Databricks Workflow); el PC tiene que estar encendido a la hora del dump.

### B · Migrar a un plan de pago con compute tradicional

- Pasar a "Trial Premium" (14 días gratis) o a un plan con clusters.
- **Pros:** notebook único hace todo (JDBC al MySQL via Cloudflare Tunnel + write Delta).
- **Contras:** coste mensual ($$); el túnel JDBC sigue siendo más frágil que el dump local; el trial expira y volveríamos al problema.

### C · No usar Databricks · sustituir por DuckDB + Delta local

- Reemplazar toda la capa analítica con DuckDB local + Delta. Sin nube.
- **Pros:** cero coste; latencia mínima.
- **Contras:** revierte D1 (medallion en lakehouse cloud) y la decisión arquitectural de fondo del proyecto. No alineado con el visión del PLAN (escalabilidad, Unity Catalog, MLflow). Descartada.

## Decisión

Adoptar **A** · extracción en PC local → UC Volume → notebook serverless.

Concretamente:

| Pieza | Dónde corre | Periodicidad |
|-------|-------------|---------------|
| `infra/dump_to_cloud.py` | PC Windows (Task Scheduler) | Nocturna, antes del Workflow |
| Subida al Volume | El propio script vía Databricks SDK o CLI | Inmediata tras el dump |
| Notebook `bronze/<tabla>` | Databricks serverless | Nocturna, programada en Workflow |
| SQL Warehouse | Databricks serverless | Bajo demanda (BI + queries ad-hoc) |

El SQL Warehouse se configura con autoapagado de **10 minutos** (cumple verificación crítica F0 #4 de forma equivalente: el "cluster" se apaga solo).

## Consecuencias

- F0 verificación crítica #4 queda ✅ una vez se configure el SQL Warehouse con autoapagado y se documente la captura.
- F0 verificación crítica #3 queda ✅ una vez se ejecute el primer `dump_to_cloud.py` real y el notebook lo lea del Volume.
- F1 podrá empezar sin sorpresas de plan: el camino crítico es claro.
- Si en F-F del roadmap se quiere migrar a un plan con clusters, basta cambiar el script local por un job Databricks que use el driver JDBC contra el MySQL ya replicado en cloud — el resto (bronze→silver→gold) no cambia.

## Sub-decisiones aún por confirmar

- **Cloud storage:** se usa **UC Volume managed** (Databricks gestiona el storage). Si se quiere bring-your-own-bucket (S3/ADLS/GCS) más adelante, se documenta como ADR aparte. UC Volume managed cubre F1.
- **Periodicidad inicial:** nocturna, 02:00 hora COL (sgHermes ya cerró el día). Revisable si los datos no llegan a tiempo al dashboard.
