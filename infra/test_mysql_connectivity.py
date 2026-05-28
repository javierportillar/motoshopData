from __future__ import annotations

import json
import pathlib
import sys

import mysql.connector


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONECTIVIDAD_DIR = PROJECT_ROOT / "conectividad"
ENV_FILE = PROJECT_ROOT / ".env"


def load_env() -> dict:
    env_vars: dict[str, str] = {}
    if not ENV_FILE.exists():
        print(f"[ERROR] .env no encontrado en {ENV_FILE}")
        sys.exit(1)
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_vars[key.strip()] = value.strip()
    return env_vars


def main() -> None:
    env = load_env()

    config = {
        "host": env.get("MYSQL_HOST", "localhost"),
        "port": int(env.get("MYSQL_PORT", 3306)),
        "user": env.get("MYSQL_USER", "analytics"),
        "password": env.get("MYSQL_PASSWORD", ""),
        "database": env.get("MYSQL_DATABASE", "motoshop2024"),
        "charset": "utf8",
    }

    print(f"Conectando a MySQL {config['host']}:{config['port']}/{config['database']} ", end="")
    sys.stdout.flush()

    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS ok")
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    result = {"ok": row[0] == 1, "mysql_host": config["host"], "mysql_database": config["database"], "user": config["user"]}

    CONECTIVIDAD_DIR.mkdir(parents=True, exist_ok=True)
    output_file = CONECTIVIDAD_DIR / "hello_mysql_result.json"
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("OK")
    print(f"Resultado: SELECT 1 -> {row[0]}")
    print(f"Archivo guardado: {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
