"""Lanzador de la API para pythonw.exe: cero consola, logs a archivo.

Uso (accion de la tarea MotoShopBackendSvc):

    pythonw.exe <repo>\\infra\\api_launcher.py

Por que existe: ``pythonw.exe`` no tiene stdout/stderr, asi que ``uvicorn`` no
puede escribir nada en consola. Este lanzador redirige el logger raiz (y
stdout/stderr) a ``logs/api_uvicorn.log`` con rotacion, y arranca la app
programaticamente. Si la app revienta al importar, la excepcion queda en el log
en vez de perderse.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

INFRA = Path(__file__).resolve().parent
PROJECT = INFRA.parent
API_DIR = PROJECT / "motoshop-app" / "api"
LOG_FILE = PROJECT / "logs" / "api_uvicorn.log"
PUERTO = int(os.environ.get("MOTOSHOP_API_PORT", "8000"))


class _AlArchivo:
    """Reemplazo de stdout/stderr: pythonw no tiene consola."""

    def __init__(self, logger: logging.Logger, nivel: int) -> None:
        self._logger = logger
        self._nivel = nivel
        self._escribiendo = False

    def write(self, texto: str) -> int:
        # Reentrante: si el handler falla, logging escribe en sys.stderr, que
        # somos nosotros mismos. Sin esta guarda se recursa hasta el infinito.
        if self._escribiendo or not texto or not texto.strip():
            return len(texto)
        self._escribiendo = True
        try:
            self._logger.log(self._nivel, texto.rstrip())
        finally:
            self._escribiendo = False
        return len(texto)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def _configurar_logs() -> logging.Logger:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # httpx loguea cada request con la URL completa (query strings de Supabase):
    # no tiene redaccion de PII y ademas hace rotar el archivo sin aportar nada.
    for ruidoso in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    return logging.getLogger("api_launcher")


def main() -> int:
    log = _configurar_logs()
    try:
        os.chdir(API_DIR)
        origen = str(API_DIR / "src")
        if origen not in sys.path:
            sys.path.insert(0, origen)
        sys.stdout = _AlArchivo(log, logging.INFO)
        sys.stderr = _AlArchivo(log, logging.ERROR)

        log.info(
            "arrancando API puerto=%s cwd=%s python=%s", PUERTO, API_DIR, sys.executable
        )
        import uvicorn

        # log_config=None: sin dictConfig, los loggers de uvicorn propagan al
        # logger raiz que ya escribe al archivo.
        uvicorn.run("motoshop_api.main:app", port=PUERTO, log_config=None)
    except BaseException:
        # pythonw no tiene stderr: sin este except la falla de arranque se
        # perderia en silencio.
        log.exception("la API termino con excepcion")
        return 1
    log.info("la API termino normalmente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
