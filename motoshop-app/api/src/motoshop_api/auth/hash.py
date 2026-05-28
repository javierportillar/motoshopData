"""Hash de contraseñas con bcrypt."""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Genera un hash bcrypt de la contraseña."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una contraseña contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False
