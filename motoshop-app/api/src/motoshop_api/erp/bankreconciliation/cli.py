"""CLI para gestionar el vault de credenciales de Bancolombia."""

import argparse
import getpass
import sys

from motoshop_api.erp.bankreconciliation.vault import (
    CredentialVault,
    EntryMeta,
    VaultBackendUnavailable,
    VaultCorruptFile,
    VaultDecryptionError,
    VaultError,
    VaultNotFound,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI para gestionar credenciales de Bancolombia encriptadas.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        choices=["passphrase", "keychain"],
        default="passphrase",
        help=(
            "Backend para la custodia de la clave maestra.\n"
            "  passphrase: Se solicita una frase de contraseña al usuario (por defecto).\n"
            "  keychain: Almacena la clave maestra en el Keychain de macOS (solo macOS)."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Set command
    set_parser = subparsers.add_parser("set", help="Guarda o actualiza una credencial.")
    set_parser.add_argument("name", help="Nombre de la credencial (ej. bancolombia).")

    # List command
    subparsers.add_parser(
        "list", help="Lista los nombres de las credenciales guardadas."
    )

    # Check command
    subparsers.add_parser(
        "check", help="Verifica si el vault existe y es accesible."
    )

    # Rotate command
    rotate_parser = subparsers.add_parser(
        "rotate", help="Rota (actualiza) una credencial existente."
    )
    rotate_parser.add_argument("name", help="Nombre de la credencial a rotar.")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Elimina una credencial.")
    delete_parser.add_argument("name", help="Nombre de la credencial a eliminar.")

    # Reveal command
    reveal_parser = subparsers.add_parser(
        "reveal", help="Muestra una credencial en texto plano (¡CUIDADO!)."
    )
    reveal_parser.add_argument("name", help="Nombre de la credencial a revelar.")
    reveal_parser.add_argument(
        "--yes-i-understand",
        action="store_true",
        help="Confirma que entiendes los riesgos de seguridad al mostrar una credencial.",
    )

    args = parser.parse_args()

    try:
        vault = CredentialVault(custody_backend=args.backend)

        if args.command == "set":
            username = getpass.getpass("Ingrese el usuario: ")
            password = getpass.getpass("Ingrese la clave: ")
            vault.set_entry(args.name, username, password)
            print(f"Credencial '{args.name}' guardada/actualizada con éxito.")
        elif args.command == "list":
            entries: list[EntryMeta] = vault.list_entries()
            if not entries:
                print("No hay credenciales guardadas.")
                return
            print("Credenciales guardadas:")
            for entry in entries:
                print(f"  - {entry.name} (última actualización: {entry.updated_at.isoformat()})")
        elif args.command == "check":
            if vault.check():
                print("Vault: OK. Accesible y desencriptable.")
            else:
                print(
                    "Vault: NO ACCESIBLE o NO DESENCRIPTACIÓN. Puede que no exista, "
                    "esté corrupto o la clave maestra sea incorrecta."
                )
                sys.exit(1)
        elif args.command == "rotate":
            username = getpass.getpass("Ingrese el nuevo usuario: ")
            password = getpass.getpass("Ingrese la nueva clave: ")
            vault.rotate_entry(args.name, username, password)
            print(f"Credencial '{args.name}' rotada con éxito.")
        elif args.command == "delete":
            vault.delete_entry(args.name)
            print(f"Credencial '{args.name}' eliminada con éxito.")
        elif args.command == "reveal":
            if not args.yes_i_understand:
                print(
                    "ERROR: Para revelar una credencial, debe confirmar explícitamente "
                    "pasando la bandera --yes-i-understand.",
                    file=sys.stderr,
                )
                sys.exit(2)
            print(
                "ADVERTENCIA: La credencial se mostrará en texto plano. "
                "¡Asegúrese de que nadie esté mirando!",
                file=sys.stderr,
            )
            username, password = vault.reveal_entry(args.name)
            print(f"Usuario para '{args.name}': {username}")
            print(f"Clave para '{args.name}': {password}")

    except EOFError:
        print(
            "ERROR: no se pudo leer la clave maestra: la entrada estándar no es interactiva.",
            file=sys.stderr,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nERROR: operación cancelada por el usuario.", file=sys.stderr)
        sys.exit(1)
    except VaultNotFound as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except VaultDecryptionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except VaultCorruptFile as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except VaultBackendUnavailable as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except VaultError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR inesperado: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
