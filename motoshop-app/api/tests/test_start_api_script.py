r"""Contrato del arranque del nodo: nada vive solo en una maquina.

El lanzador de la API vivia en `C:\Users\ProDesk\.masvital\run_api.py`, fuera
del repo: si esa maquina se rompia, el nodo no se podia reconstruir. Ahora el
arranque es `infra/start_api_masvital.ps1` + su wrapper VBS, y este test fija
las tres propiedades que hacen que no aparezca ninguna ventana:

1. el proceso es `pythonw.exe` (no abre consola),
2. stdout/stderr van a archivo (uvicorn no escribe a una consola que no existe),
3. hay un vigilante de arranque con deadline (un boot con la red sin lista deja
   el proceso colgado sin abrir el puerto).

Ademas: la tarea programada no puede lanzar `powershell.exe` directo, tiene que
pasar por el .vbs con `Run(..., 0, True)`, si no la consola parpadea.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
INFRA = RAIZ / "infra"


def _leer(nombre: str) -> str:
    ruta = INFRA / nombre
    assert ruta.is_file(), f"falta {ruta}"
    return ruta.read_text(encoding="utf-8")


def test_el_lanzador_usa_pythonw_y_no_abre_consola() -> None:
    lanzador = _leer("start_api_masvital.ps1")

    assert "pythonw.exe" in lanzador
    # python.exe abriria una consola: solo se permite si esta dentro de un nombre mayor.
    assert ".venv\\Scripts\\python.exe" not in lanzador
    assert "-WindowStyle Hidden" in lanzador


def test_el_lanzador_manda_los_logs_a_archivo() -> None:
    lanzador = _leer("start_api_masvital.ps1")

    assert "-RedirectStandardOutput" in lanzador
    assert "-RedirectStandardError" in lanzador
    # logs/ esta en .gitignore: el nodo escribe ahi, no en el repo.
    assert 'Join-Path $Logs "api_masvital' in lanzador


def test_el_lanzador_tiene_vigilante_de_arranque() -> None:
    lanzador = _leer("start_api_masvital.ps1")

    # Deadline explicito y reintento: sin esto un arranque colgado no muere nunca.
    assert "EsperaSeg = 150" in lanzador
    assert "while (((Get-Date) - $inicio).TotalSeconds -lt $EsperaSeg)" in lanzador
    assert "exit 1" in lanzador


def test_el_wrapper_vbs_oculta_la_ventana() -> None:
    wrapper = _leer("start_api_masvital_wrapper.vbs")

    # 0 = ventana oculta, True = esperar al hijo. Es el patron del proyecto.
    assert ', 0, True' in wrapper
    # La ruta sale del propio .vbs: reconstruible en otra maquina.
    assert "GetParentFolderName(WScript.ScriptFullName)" in wrapper
    assert "start_api_masvital.ps1" in wrapper
