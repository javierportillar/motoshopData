#!/usr/bin/env python3
"""Preflight del nodo bancario: valida la configuración de la máquina local.

Uso (desde `motoshop-app/api`):

    uv run python scripts/bank_verify.py --tenant motoshop
    uv run python scripts/bank_verify.py --tenant motoshop --check

`--check` NO accede al vault (no pide la clave maestra): sólo valida la
configuración, la etiqueta de cuenta y el directorio del perfil.

Código de salida: 0 si el nodo está listo, 1 con el motivo explícito si no lo
está. El resultado nunca muestra el usuario ni la contraseña del vault.
"""

from __future__ import annotations

import argparse
import os
import sys

from motoshop_api.erp.bankreconciliation.node_config import (
    CODIGO_ANTIBOT,
    CODIGO_CONFIGURACION_INVALIDA,
    CODIGO_CREDENCIAL_AUSENTE,
    CODIGO_CUENTA_NO_ENCONTRADA,
    CODIGO_PERFIL_DENTRO_DEL_REPO,
    CODIGO_PERFIL_INEXISTENTE,
    CODIGO_PERFIL_PERMISOS,
    CODIGO_PORTAL_NO_DISPONIBLE,
    CODIGO_SESION_EXPIRADA,
    CODIGO_TENANT_NO_CONFIGURADO,
    CODIGO_VAULT_NO_ACCESIBLE,
    ENV_SCRAPER_ENABLED,
    ENV_TENANT,
    NodeConfigError,
    load_node_config,
    run_preflight,
)

#: Explicación en español de cada motivo (el código es el que se documenta).
EXPLICACIONES = {
    CODIGO_CREDENCIAL_AUSENTE: "no existe la entrada de credenciales de este tenant en el vault",
    CODIGO_CUENTA_NO_ENCONTRADA: (
        "falta BANK_ACCOUNT_LABEL o la etiqueta no existe en la sesión del portal"
    ),
    CODIGO_SESION_EXPIRADA: "la sesión del portal expiró (lo detecta el scraper, no el preflight)",
    CODIGO_ANTIBOT: "el portal pidió una verificación antibot (lo detecta el scraper)",
    CODIGO_PORTAL_NO_DISPONIBLE: "el portal no respondió (lo detecta el scraper)",
    CODIGO_VAULT_NO_ACCESIBLE: "el vault no se pudo leer (frase de contraseña o archivo alterado)",
    CODIGO_PERFIL_DENTRO_DEL_REPO: "el perfil del navegador está dentro del repositorio",
    CODIGO_PERFIL_INEXISTENTE: "el directorio del perfil del navegador no existe",
    CODIGO_PERFIL_PERMISOS: "el perfil del navegador no tiene permisos 700",
    CODIGO_TENANT_NO_CONFIGURADO: "este nodo no declara el tenant que sirve",
    CODIGO_CONFIGURACION_INVALIDA: "la configuración del nodo es inválida",
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica la configuración del nodo que raspa el portal de Bancolombia.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--tenant", required=True, help="Tenant que sirve este nodo.")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "No acceder al vault (no pide la clave maestra):\n"
            "  sólo valida la configuración, la etiqueta de cuenta y el perfil."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el preflight y devuelve el código de salida (0 = ok, 1 = fallo)."""
    args = _parse_args(argv)

    env = dict(os.environ)
    env[ENV_TENANT] = args.tenant
    # El operador está verificando un nodo local: si no dijo lo contrario, se
    # comprueba como nodo con scraper habilitado.
    env.setdefault(ENV_SCRAPER_ENABLED, "true")

    try:
        config = load_node_config(env, estricto=False)
    except NodeConfigError as error:
        print(f"[FALLO] configuracion → {CODIGO_CONFIGURACION_INVALIDA}", file=sys.stderr)
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    resultado = run_preflight(config, verificar_credencial=not args.check)

    print(f"Nodo: {config.tenant or '(sin tenant)'}")
    print(f"  scraper:    {'habilitado' if config.scraper_enabled else 'deshabilitado'}")
    print(f"  credencial: {config.credential_entry or '(sin credencial)'}")
    print(f"  etiqueta:   {config.account_label or '(sin etiqueta)'}")
    print(f"  vault:      {config.vault_backend}")
    print(f"  perfil:     {config.profile_dir}")
    print(
        f"  ventana:    {config.window_start:%Y-%m-%d %H:%M:%S} → "
        f"{config.window_end:%Y-%m-%d %H:%M:%S} ({config.ventana_por_defecto})"
    )
    print("")

    for check in resultado.checks:
        estado = "OK   " if check.ok else "FALLO"
        motivo = f" → {check.motivo}" if check.motivo else ""
        print(f"[{estado}] {check.name}{motivo}")
        explicacion = EXPLICACIONES.get(check.motivo) if check.motivo else None
        if explicacion:
            print(f"          {explicacion}")

    print("")
    if resultado.ok:
        print(f"PREFLIGHT OK: el nodo '{config.tenant}' está listo.")
        return 0
    # Se vacía el buffer de salida para que el motivo no aparezca antes del resumen.
    sys.stdout.flush()
    print(f"PREFLIGHT FALLO: {resultado.motivo}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
