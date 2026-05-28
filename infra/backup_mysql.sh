#!/usr/bin/env bash
# Backup de la BD motoshop2024 (MySQL 5.0, MyISAM).
#
# Verificación crítica #6 de Fase 0: tener un dump válido FUERA del repo
# antes de tocar nada más. Este script NO se ejecuta automáticamente — lo
# corre el humano y deja registrada la métrica (tamaño, duración) en
# SEGUIMIENTO.md.
#
# Uso:
#   chmod +x infra/backup_mysql.sh
#   MOTOSHOP_BACKUP_DIR=~/Backups/motoshop ./infra/backup_mysql.sh
#
# Variables de entorno opcionales:
#   MYSQL_HOST       (default: localhost)
#   MYSQL_PORT       (default: 3306)
#   MYSQL_USER       (default: root)
#   MYSQL_PASSWORD   (default: vacío)
#   MYSQL_DATABASE   (default: motoshop2024)
#   MOTOSHOP_BACKUP_DIR (default: ~/Backups/motoshop)
#
# Notas:
# - El destino debe estar FUERA del repo (nunca commitear dumps).
# - Tablas MyISAM: el dump usa --lock-tables para consistencia. Acordar
#   ventana con el usuario de sgHermes para evitar contención.
# - Compresión gzip por defecto.

set -euo pipefail

MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DATABASE="${MYSQL_DATABASE:-motoshop2024}"
BACKUP_DIR="${MOTOSHOP_BACKUP_DIR:-$HOME/Backups/motoshop}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTFILE="$BACKUP_DIR/${MYSQL_DATABASE}_${TIMESTAMP}.sql.gz"

echo "→ Origen:  $MYSQL_USER@$MYSQL_HOST:$MYSQL_PORT/$MYSQL_DATABASE"
echo "→ Destino: $OUTFILE"

PASSWORD_ARG=()
if [[ -n "$MYSQL_PASSWORD" ]]; then
  PASSWORD_ARG=(--password="$MYSQL_PASSWORD")
fi

START=$(date +%s)

mysqldump \
  --host="$MYSQL_HOST" \
  --port="$MYSQL_PORT" \
  --user="$MYSQL_USER" \
  "${PASSWORD_ARG[@]}" \
  --single-transaction=false \
  --lock-tables \
  --routines \
  --triggers \
  --events \
  --default-character-set=utf8 \
  "$MYSQL_DATABASE" \
  | gzip -9 > "$OUTFILE"

END=$(date +%s)
DURATION=$((END - START))
SIZE=$(du -h "$OUTFILE" | cut -f1)

echo "→ Tamaño:   $SIZE"
echo "→ Duración: ${DURATION}s"

echo "→ Verificación de integridad..."
gunzip -t "$OUTFILE"
echo "✓ gunzip -t OK"

echo ""
echo "Backup completado. Anotar en SEGUIMIENTO.md (F0, métrica de backup):"
echo "  archivo:  $OUTFILE"
echo "  tamaño:   $SIZE"
echo "  duración: ${DURATION}s"
