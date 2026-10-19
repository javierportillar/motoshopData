#!/usr/bin/env python3
"""Script seguro para actualizar la API Key de OpenCode en Supabase y verificarla en vivo."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

# Añadir el src de la API al path
repo_root = Path(__file__).resolve().parent.parent
api_src = repo_root / "motoshop-app" / "api" / "src"
sys.path.insert(0, str(api_src))

from motoshop_api.users import supabase_repo
import httpx


def main():
    print("=" * 60)
    print("ACTUALIZADOR SEGURO DE CREDENCIALES LLM (OPENCODE)")
    print("=" * 60)

    if not supabase_repo.is_configured():
        print("[ERROR] Supabase no está configurado en .env")
        sys.exit(1)

    try:
        new_key = getpass.getpass("Pegá tu nueva OPENCODE_API_KEY (la escritura estará oculta): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        sys.exit(0)

    if not new_key:
        print("[ERROR] No ingresaste ninguna clave.")
        sys.exit(1)

    print("\n1. Verificando clave directamente contra OpenCode AI...")
    try:
        r = httpx.post(
            "https://opencode.ai/zen/go/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {new_key}",
                "Content-Type": "application/json",
                "x-opencode-session": "test-verify",
            },
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "Respondé solo la palabra LISTO"}],
                "max_tokens": 10,
            },
            timeout=15.0,
        )
        if r.status_code != 200:
            print(f"[ERROR] OpenCode rechazó la clave (HTTP {r.status_code}): {r.text}")
            print("Verificá haber copiado la clave completa desde la consola de OpenCode.")
            sys.exit(1)
        
        reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"   [OK] OpenCode respondió 200 OK: '{reply}'")
    except Exception as exc:
        print(f"[ERROR] Falló la conexión con OpenCode: {exc}")
        sys.exit(1)

    print("\n2. Guardando en Supabase (_system_config)...")
    try:
        cfg = supabase_repo.get_user("_system_config") or {}
        current_modules = cfg.get("allowed_modules") or []
        new_modules = [m for m in current_modules if not m.startswith("opencode_api_key=")]
        new_modules.insert(0, f"opencode_api_key={new_key}")

        supabase_repo.update_user("_system_config", {"allowed_modules": new_modules})
        print("   [OK] Supabase actualizado exitosamente.")
    except Exception as exc:
        print(f"[ERROR] Falló la actualización en Supabase: {exc}")
        sys.exit(1)

    print("\n3. Actualizando .env local...")
    api_env = repo_root / "motoshop-app" / "api" / ".env"
    if api_env.exists():
        lines = api_env.read_text(encoding="utf-8").splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith("OPENCODE_API_KEY="):
                new_lines.append(f"OPENCODE_API_KEY={new_key}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"OPENCODE_API_KEY={new_key}")
        api_env.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print("   [OK] .env local actualizado.")

    print("\n" + "=" * 60)
    print("¡COMPLETADO CON ÉXITO!")
    print("La nueva clave quedó activa en Supabase.")
    print("Ambos PCs (MotoShop y MasVital) y la app en producción")
    print("usarán esta clave de inmediato en la próxima consulta.")
    print("=" * 60)


if __name__ == "__main__":
    main()
