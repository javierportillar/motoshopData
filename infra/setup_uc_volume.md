# Configurar UC Volume `motoshop.bronze._landing`

> Una vez. Antes de correr `dump_to_cloud.py` por primera vez.

El script local sube los Parquet a un **Unity Catalog Volume** (no a una carpeta de filesystem ni a S3). Esto evita configurar storage externo en el Free Edition.

## Pasos (Databricks UI)

1. **Workspace → Catalog Explorer.**
2. Abrir el catálogo `motoshop` → esquema `bronze`.
3. **Create → Volume.**
4. Nombre: `_landing` · Tipo: **Managed volume** (Databricks gestiona el storage).
5. Crear.

Path resultante: `/Volumes/motoshop/bronze/_landing/`.

## Alternativa por SQL (un solo comando)

Desde el SQL Editor del workspace:

```sql
CREATE VOLUME IF NOT EXISTS motoshop.bronze._landing
  COMMENT 'Staging de Parquet subidos por dump_to_cloud.py (Track A · F1)';
```

## Permisos

- El PAT que usa `dump_to_cloud.py` necesita `WRITE VOLUME` sobre `motoshop.bronze._landing`.
- En Free Edition, si el PAT es del owner del workspace, ya tiene permiso. Verificar con:

```sql
SHOW GRANTS ON VOLUME motoshop.bronze._landing;
```

## Verificación

Después de la primera ejecución del dump (`python infra/dump_to_cloud.py --tables sucursales`), debería existir:

```
/Volumes/motoshop/bronze/_landing/sucursales/ingest_date=YYYY-MM-DD/part-0.parquet
```

Verificable desde el Catalog Explorer (vista de archivos del volume) o:

```sql
LIST '/Volumes/motoshop/bronze/_landing/sucursales/';
```
