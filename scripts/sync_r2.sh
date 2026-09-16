#!/bin/bash
# sync_r2.sh - Sincroniza DuckDB desde Cloudflare R2
# Uso: ./scripts/sync_r2.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
API_ENV_FILE="$PROJECT_DIR/motoshop-app/api/.env"
DATA_DIR="$PROJECT_DIR/out"
MASVITAL_DIR="$PROJECT_DIR/../masvital"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🔄 Sincronizando datos desde Cloudflare R2...${NC}"

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ No se encontró $ENV_FILE${NC}"
    exit 1
fi

# Copy .env to API directory if needed
if [ ! -f "$API_ENV_FILE" ] || ! diff -q "$ENV_FILE" "$API_ENV_FILE" > /dev/null 2>&1; then
    echo -e "${YELLOW}📋 Copiando .env al directorio del API...${NC}"
    cp "$ENV_FILE" "$API_ENV_FILE"
fi

# Run Python sync script
python3 - << 'EOF'
import os
import sys
import boto3
from botocore.config import Config
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

endpoint = os.getenv('R2_ENDPOINT')
key = os.getenv('R2_ACCESS_KEY_ID')
secret = os.getenv('R2_SECRET_ACCESS_KEY')
bucket = os.getenv('R2_BUCKET')

if not all([endpoint, key, secret, bucket]):
    print("❌ Faltan credenciales R2 en .env")
    sys.exit(1)

# Connect to R2
s3 = boto3.client('s3',
    endpoint_url=endpoint,
    aws_access_key_id=key,
    aws_secret_access_key=secret,
    config=Config(signature_version='s3v4')
)

# Files to sync
project_dir = os.path.dirname(os.path.dirname(__file__))
files = [
    ('motoshop_gold.duckdb', os.path.join(project_dir, 'out', 'motoshop_gold.duckdb')),
    ('masvital_gold.duckdb', os.path.join(project_dir, '..', 'masvital', 'masvital_gold.duckdb')),
]

for key_name, local_path in files:
    local = Path(local_path)
    print(f"\n📥 Sincronizando {key_name}...")
    
    # Get R2 file info
    try:
        response = s3.head_object(Bucket=bucket, Key=key_name)
        r2_size = response['ContentLength']
        r2_modified = response['LastModified']
    except Exception as e:
        print(f"  ⚠️ No se encontró {key_name} en R2: {e}")
        continue
    
    # Check local file
    if local.exists():
        local_size = local.stat().st_size
        if local_size == r2_size:
            print(f"  ✅ Ya está actualizado ({local_size} bytes)")
            continue
    
    # Download
    print(f"  📥 Descargando {r2_size} bytes...")
    local.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, key_name, str(local))
    print(f"  ✅ Descargado: {local}")

print("\n✅ Sincronización completada!")
EOF

echo -e "${GREEN}✅ Listo! Reiniciá el backend para usar los datos frescos.${NC}"
echo -e "${YELLOW}   cd motoshop-app/api && uv run uvicorn motoshop_api.main:app --reload${NC}"
