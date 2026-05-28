"""CLI utility: genera un hash bcrypt de una contraseña.

Uso:
    python infra/hash_password.py 'mi_password'
"""

from __future__ import annotations

import sys

from motoshop_api.auth.hash import hash_password


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python infra/hash_password.py '<password>'")
        return 1

    plain = sys.argv[1]
    hashed = hash_password(plain)
    print(hashed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
