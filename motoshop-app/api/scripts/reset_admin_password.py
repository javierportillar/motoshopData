#!/usr/bin/env python3
"""
Recuperación de contraseña admin en producción.

En producción los usuarios se sincronizan desde Supabase al arrancar la API,
y Supabase tiene prioridad sobre users.yaml. Este script actualiza el hash de
la contraseña del usuario 'admin' directamente en Supabase.

Uso:
    cd motoshop-app/api
    uv run python scripts/reset_admin_password.py

Requiere:
    - Variables SUPABASE_URL y SUPABASE_SERVICE_KEY en .env
    - Conectividad a Internet (resolución DNS de Supabase)
"""
from __future__ import annotations

import argparse
import os
import sys

import bcrypt
import requests
from dotenv import load_dotenv


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def reset_admin_password(supabase_url: str, service_key: str, new_password: str) -> None:
    hashed = _hash_password(new_password)
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{supabase_url.rstrip('/')}/rest/v1/app_users?username=eq.admin"
    response = requests.patch(url, json={"hashed_password": hashed}, headers=headers, timeout=30)

    if response.status_code not in (200, 204):
        print(f"❌ Error {response.status_code}: {response.text}")
        sys.exit(1)

    print("✅ Contraseña de admin actualizada en Supabase")
    print(f"   Usuario: admin")
    print(f"   Nueva contraseña: {new_password}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset admin password in Supabase")
    parser.add_argument(
        "--password",
        default=os.getenv("ADMIN_RESET_PASSWORD", "MotoShop2026!"),
        help="Nueva contraseña para admin",
    )
    args = parser.parse_args()

    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not service_key:
        print("❌ Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY en .env")
        sys.exit(1)

    reset_admin_password(supabase_url, service_key, args.password)


if __name__ == "__main__":
    main()
