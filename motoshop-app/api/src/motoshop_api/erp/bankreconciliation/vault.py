# type: ignore # dynamic types, platform-specific for cryptography
import base64
import dataclasses
import datetime
import getpass
import hashlib
import json
import os
import select
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

try:  # pragma: no cover - POSIX only: `pty`/`termios` no existen en Windows
    import pty
    import termios
except ImportError:  # pragma: no cover - Windows
    pty = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

# --- Errors ---


class VaultError(Exception):
    """Base para errores del vault."""


class VaultNotFound(VaultError):
    """El vault o la entrada no se encontraron."""


class VaultDecryptionError(VaultError):
    """Error al desencriptar, clave maestra incorrecta o archivo corrupto/alterado."""


class VaultBackendUnavailable(VaultError):
    """El backend de custodia de la clave maestra no está disponible en esta plataforma."""


class VaultCorruptFile(VaultError):
    """El archivo del vault está corrupto o mal formado."""


# --- Constants ---

DEFAULT_KDF_ITERATIONS = 600_000
KDF_ALGORITHM = "pbkdf2_hmac_sha256"
# El backend `keychain` no deriva nada: la clave maestra es aleatoria y la custodia
# vive en el Keychain. El envelope debe describir lo que realmente se hizo.
KDF_ALGORITHM_RANDOM = "random"
VAULT_VERSION = 1
MIN_PASSPHRASE_LENGTH = 8

# --- Data Structures ---


@dataclasses.dataclass(frozen=True)
class Entry:
    username: str
    password: str
    updated_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class EntryMeta:
    name: str
    updated_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class _KeyDerivationParams:
    algo: str
    iterations: int
    salt: str  # base64 encoded


@dataclasses.dataclass(frozen=True)
class _VaultEnvelope:
    version: int
    kdf: _KeyDerivationParams
    key_custody: Literal["passphrase", "keychain", "dpapi"]
    ciphertext: str  # base64 encoded Fernet token
    created_at: str  # ISO-8601


@dataclasses.dataclass(frozen=True)
class _VaultContent:
    entries: dict[str, Entry]


# --- Utility Functions ---


def _get_config_dir() -> Path:
    """Retorna el directorio de configuración para la aplicación.

    NO se cachea: la ruta depende del entorno (`XDG_CONFIG_HOME`/`APPDATA`) y un
    valor cacheado ignoraría los cambios de configuración del proceso.
    """
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", r"~\AppData\Roaming")).expanduser() / "motoshop"
    # POSIX (macOS, Linux)
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "motoshop"
    return Path("~/.config").expanduser() / "motoshop"


def _get_vault_path() -> Path:
    """Retorna la ruta completa al archivo del vault."""
    return _get_config_dir() / "credentials.enc"


def _validate_master_passphrase(passphrase: str) -> None:
    """Rechaza frases de contraseña vacías o demasiado cortas.

    Sin este control, PBKDF2 derivaría una clave a partir de una cadena vacía:
    el vault existiría pero cualquiera que conozca el formato podría abrirlo.
    """
    if not passphrase:
        raise VaultError(
            "La frase de contraseña no puede estar vacía. "
            f"Debe tener al menos {MIN_PASSPHRASE_LENGTH} caracteres."
        )
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise VaultError(
            "La frase de contraseña es demasiado corta: "
            f"debe tener al menos {MIN_PASSPHRASE_LENGTH} caracteres."
        )


def _load_envelope_salt(vault_path: Path) -> bytes | None:
    """Lee el `salt` (base64) del envelope del vault.

    El salt pertenece al SOBRE (es un modificador de la derivación, no un secreto),
    no al backend de custodia. Devuelve `None` si el archivo del vault todavía no
    existe. Un envelope ilegible es un archivo corrupto, no una excepción cruda.
    """
    if not vault_path.exists():
        return None
    try:
        with vault_path.open("r", encoding="utf-8") as f:
            envelope_data = json.load(f)
        salt_b64 = envelope_data["kdf"]["salt"]
        salt = base64.b64decode(salt_b64, validate=True)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise VaultCorruptFile(
            "Archivo del vault corrupto o mal formado al leer el salt."
        ) from e
    if not salt:
        raise VaultCorruptFile("Archivo del vault corrupto o mal formado al leer el salt.")
    return salt


def derive_key(passphrase: str, salt: bytes, iterations: int = DEFAULT_KDF_ITERATIONS) -> bytes:
    """
    Deriva una clave Fernet (AES-128-CBC + HMAC-SHA256) a partir de una frase de contraseña
    y un salt usando PBKDF2-HMAC-SHA256, luego la codifica en base64 urlsafe.
    """
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations, dklen=32)
    return base64.urlsafe_b64encode(key)


def _build_fernet(master_key: bytes) -> Fernet:
    """Construye el objeto Fernet, convirtiendo el `ValueError` en un error tipado."""
    try:
        return Fernet(master_key)
    except (TypeError, ValueError) as e:
        raise VaultError("Clave maestra inválida: no se pudo construir la clave de cifrado.") from e


def encrypt_payload(plaintext_bytes: bytes, master_key: bytes) -> bytes:
    """Encripta un payload usando Fernet."""
    f = _build_fernet(master_key)
    return f.encrypt(plaintext_bytes)


def decrypt_payload(token: bytes, master_key: bytes) -> bytes:
    """Desencripta un payload usando Fernet."""
    f = _build_fernet(master_key)
    try:
        return f.decrypt(token)
    except InvalidToken as e:
        raise VaultDecryptionError(
            "Error de desencriptación: clave maestra incorrecta o archivo alterado."
        ) from e


# --- Master Key Custody Backends ---


class _MasterKeyCustody:
    """Abstract base for master key custody."""

    def get_master_key(self, prompt: str) -> bytes:
        raise NotImplementedError

    def store_master_key(self, master_key: bytes) -> None:
        raise NotImplementedError

    def delete_master_key(self) -> None:
        raise NotImplementedError


class _PassphraseCustody(_MasterKeyCustody):
    """Custodia de clave maestra via frase de contraseña.

    Este backend NO custodia ninguna clave almacenada: la clave maestra se deriva
    en cada uso a partir de la frase del operador y del `salt` guardado en el
    envelope (el salt pertenece al sobre, no a la custodia).
    """

    def get_master_key(self, prompt: str) -> bytes:
        raise VaultBackendUnavailable(
            "El backend 'passphrase' deriva la clave maestra dentro del flujo del vault "
            "(frase del operador + salt del envelope); no se puede obtener de forma aislada."
        )

    def store_master_key(self, master_key: bytes) -> None:
        raise VaultBackendUnavailable(
            "El backend 'passphrase' no almacena la clave maestra: se deriva de la frase."
        )

    def delete_master_key(self) -> None:
        # No hay clave almacenada que eliminar: se deriva de la frase en cada uso.
        return None


class _KeychainCustody(_MasterKeyCustody):
    """Custodia de clave maestra via macOS Keychain."""

    SERVICE = "motoshop-bank-vault"
    ACCOUNT = "master-key"
    SECURITY_TIMEOUT_SECONDS = 20.0

    def get_master_key(self, prompt: str) -> bytes:
        if sys.platform != "darwin":
            raise VaultBackendUnavailable(
                "Keychain no está disponible en esta plataforma (solo macOS)."
            )
        # security find-generic-password -a "master-key" -s "motoshop-bank-vault" -w
        cmd = [
            "security",
            "find-generic-password",
            "-a",
            self.ACCOUNT,
            "-s",
            self.SERVICE,
            "-w",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise VaultError(
                "El comando 'security' no se encontró. Asegúrese de que las herramientas "
                "de línea de comandos de Xcode estén instaladas."
            ) from exc
        if result.returncode != 0:
            # Un ítem ausente NO es un error genérico: se conserva el tipo específico.
            raise VaultNotFound("Clave maestra no encontrada en Keychain.")
        key = result.stdout.strip()
        if not key:
            raise VaultNotFound("Clave maestra no encontrada en Keychain.")
        # La clave se guarda y se recupera en base64 urlsafe (formato de clave Fernet).
        try:
            return key.encode("ascii")
        except UnicodeEncodeError as exc:
            raise VaultError("La clave maestra del Keychain no tiene un formato válido.") from exc

    def store_master_key(self, master_key: bytes) -> None:
        if sys.platform != "darwin":
            raise VaultBackendUnavailable(
                "Keychain no está disponible en esta plataforma (solo macOS)."
            )
        b64_key = base64.urlsafe_b64encode(master_key).decode("ascii")
        # `-w` SIN valor y como ÚLTIMA opción: el propio `security` pide la clave por
        # terminal. La clave NUNCA viaja en argv (quedaría visible en `ps` para
        # cualquier usuario local). `-U` = actualiza el ítem si ya existe.
        cmd = [
            "security",
            "add-generic-password",
            "-a",
            self.ACCOUNT,
            "-s",
            self.SERVICE,
            "-U",
            "-w",
        ]
        returncode, output = _run_security_prompt(cmd, b64_key, self.SECURITY_TIMEOUT_SECONDS)
        if returncode != 0:
            raise VaultError(f"Error al almacenar la clave maestra en Keychain: {output}")

    def delete_master_key(self) -> None:
        if sys.platform != "darwin":
            raise VaultBackendUnavailable(
                "Keychain no está disponible en esta plataforma (solo macOS)."
            )
        try:
            # security delete-generic-password -a "master-key" -s "motoshop-bank-vault"
            cmd = ["security", "delete-generic-password", "-a", self.ACCOUNT, "-s", self.SERVICE]
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if (
                process.returncode != 0
                and "The specified item could not be found in the keychain" not in process.stderr
            ):
                raise VaultError(
                    f"Error al eliminar la clave maestra de Keychain: {process.stderr}"
                )
        except FileNotFoundError as exc:
            raise VaultError(
                "El comando 'security' no se encontró. Asegúrese de que las herramientas "
                "de línea de comandos de Xcode estén instaladas."
            ) from exc
        except subprocess.CalledProcessError as e:
            if "The specified item could not be found in the keychain" not in (e.stderr or ""):
                raise VaultError(
                    f"Error al eliminar la clave maestra de Keychain: {e.stderr}"
                ) from e
        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Error inesperado al eliminar de Keychain: {e}") from e


def _disable_terminal_echo(fd: int) -> None:
    """Desactiva el eco del terminal para que la clave no se reflecta en la salida."""
    if termios is None:  # pragma: no cover - Windows
        return
    try:
        attrs = termios.tcgetattr(fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except (termios.error, OSError):  # pragma: no cover - depende del terminal
        pass


def _run_security_prompt(
    cmd: list[str], secret: str, timeout: float = 20.0
) -> tuple[int, str]:
    """Ejecuta `cmd` respondiendo a su prompt con `secret` vía pseudo-terminal.

    El secreto se escribe en el maestro de la pty: nunca forma parte de `argv`, por
    lo que no es visible para otros usuarios del sistema mediante `ps`. El proceso
    hijo se lanza en una sesión nueva (`start_new_session`) para que NO tenga
    terminal de control: así `security` lee de la pty y no del terminal real del
    operador.

    Devuelve `(returncode, salida)` con la salida saneada (el secreto nunca aparece).
    """
    if pty is None:  # pragma: no cover - Windows
        raise VaultError(
            "No se puede usar el prompt del Keychain en esta plataforma "
            "(la pseudo-terminal sólo existe en POSIX)."
        )
    try:
        master_fd, slave_fd = pty.openpty()
    except OSError as e:
        raise VaultError("No se pudo crear la pseudo-terminal para el prompt de Keychain.") from e

    try:
        _disable_terminal_echo(slave_fd)
        try:
            process = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise VaultError(
                "El comando 'security' no se encontró. Asegúrese de que las herramientas "
                "de línea de comandos de Xcode estén instaladas."
            ) from exc
        finally:
            os.close(slave_fd)

        output = bytearray()
        try:
            os.write(master_fd, secret.encode("ascii") + b"\n")
        except OSError as e:
            process.kill()
            process.wait(timeout=5)
            raise VaultError("No se pudo escribir la clave en el prompt de Keychain.") from e

        deadline = time.monotonic() + timeout
        resent = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait(timeout=5)
                raise VaultError("El prompt del Keychain no respondió a tiempo.")
            ready, _, _ = select.select([master_fd], [], [], min(0.25, remaining))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            if not resent and b"retype" in bytes(output).lower():
                # `security` pide la clave dos veces (crear/actualizar un ítem).
                resent = True
                try:
                    os.write(master_fd, secret.encode("ascii") + b"\n")
                except OSError as e:
                    process.kill()
                    process.wait(timeout=5)
                    raise VaultError(
                        "No se pudo escribir la clave en el prompt de Keychain."
                    ) from e

        try:
            returncode = process.wait(timeout=5)
        except subprocess.TimeoutExpired as e:
            process.kill()
            process.wait(timeout=5)
            raise VaultError("El prompt del Keychain no respondió a tiempo.") from e

        text = output.decode("utf-8", errors="replace")
        # Red de seguridad: el secreto jamás debe quedar en la salida (ni en logs).
        return returncode, text.replace(secret, "<redacted>").strip()
    finally:
        os.close(master_fd)


class _DpapiCustody(_MasterKeyCustody):
    """Custodia de clave maestra via Windows DPAPI (NO IMPLEMENTADA)."""

    MESSAGE = (
        "El backend 'dpapi' no está implementado: la custodia de la clave maestra "
        "mediante Windows DPAPI todavía no existe."
    )

    def get_master_key(self, prompt: str) -> bytes:
        raise VaultBackendUnavailable(self.MESSAGE)

    def store_master_key(self, master_key: bytes) -> None:
        raise VaultBackendUnavailable(self.MESSAGE)

    def delete_master_key(self) -> None:
        raise VaultBackendUnavailable(self.MESSAGE)


def _get_custody_backend(backend: Literal["passphrase", "keychain", "dpapi"]) -> _MasterKeyCustody:
    if backend == "passphrase":
        return _PassphraseCustody()
    if backend == "keychain":
        return _KeychainCustody()
    if backend == "dpapi":
        return _DpapiCustody()
    raise ValueError(f"Backend de custodia desconocido: {backend}")


def _assert_backend_available(backend: str) -> None:
    """Falla rápido si el backend de custodia no existe en esta plataforma."""
    if backend == "keychain" and sys.platform != "darwin":
        raise VaultBackendUnavailable(
            "El backend 'keychain' sólo está disponible en macOS (Keychain)."
        )
    if backend == "dpapi" and sys.platform != "win32":
        raise VaultBackendUnavailable("El backend 'dpapi' sólo está disponible en Windows.")


# --- CredentialVault Class ---


class CredentialVault:
    """
    Gestiona el almacenamiento seguro de credenciales bancarias cifradas.
    """

    _vault_path: Path
    _custody_backend: Literal["passphrase", "keychain", "dpapi"]
    _master_key: bytes | None = None

    def __init__(
        self, custody_backend: Literal["passphrase", "keychain", "dpapi"] = "passphrase"
    ) -> None:
        _assert_backend_available(custody_backend)
        self._vault_path = _get_vault_path()
        self._custody_backend = custody_backend
        self._master_key_custody = _get_custody_backend(custody_backend)
        self._master_key: bytes | None = None
        self._new_salt: bytes | None = None

    # --- helpers de envelope ---

    def _read_envelope_salt(self) -> bytes | None:
        """Salt del envelope del vault (pertenece al sobre, no al backend de custodia)."""
        return _load_envelope_salt(self._vault_path)

    def _expected_kdf(self) -> tuple[str, int]:
        """Parámetros de derivación que el envelope DEBE declarar para este backend."""
        if self._custody_backend == "passphrase":
            return KDF_ALGORITHM, DEFAULT_KDF_ITERATIONS
        # `keychain`: la clave es aleatoria y la custodia vive en el Keychain.
        return KDF_ALGORITHM_RANDOM, 0

    def _require_vault_exists(self) -> None:
        """Falla rápido si el vault no existe, ANTES de pedir la clave maestra."""
        if not self._vault_path.exists():
            raise VaultNotFound(
                "El archivo del vault no existe. Use el comando 'set' para crear la credencial."
            )

    def _load_and_decrypt_content(self, master_key: bytes) -> _VaultContent:
        if not self._vault_path.exists():
            raise VaultNotFound("El archivo del vault no existe.")

        try:
            with self._vault_path.open("r", encoding="utf-8") as f:
                envelope_data = json.load(f)
            envelope = _VaultEnvelope(
                version=envelope_data["version"],
                kdf=_KeyDerivationParams(**envelope_data["kdf"]),
                key_custody=envelope_data["key_custody"],
                ciphertext=envelope_data["ciphertext"],
                created_at=envelope_data["created_at"],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise VaultCorruptFile("Archivo del vault corrupto o mal formado.") from e

        if envelope.version != VAULT_VERSION:
            raise VaultCorruptFile(
                f"Versión de vault incompatible: {envelope.version}. Se espera {VAULT_VERSION}."
            )

        if envelope.key_custody != self._custody_backend:
            raise VaultError(
                f"El vault fue creado con el backend '{envelope.key_custody}', "
                f"pero se intentó acceder con '{self._custody_backend}'."
            )

        expected_algo, expected_iterations = self._expected_kdf()
        if (
            envelope.kdf.algo != expected_algo
            or envelope.kdf.iterations != expected_iterations
        ):
            raise VaultCorruptFile("Parámetros de derivación de clave incompatibles.")

        try:
            decoded_ciphertext = base64.b64decode(envelope.ciphertext, validate=True)
        except (TypeError, ValueError) as e:
            raise VaultCorruptFile("El ciphertext del vault está corrupto o mal formado.") from e

        try:
            decrypted_json_bytes = decrypt_payload(decoded_ciphertext, master_key)
            content_data = json.loads(decrypted_json_bytes)
            entries = {
                name: Entry(
                    username=e["username"],
                    password=e["password"],
                    updated_at=datetime.datetime.fromisoformat(e["updated_at"]),
                )
                for name, e in content_data["entries"].items()
            }
            return _VaultContent(entries=entries)
        except (InvalidToken, VaultDecryptionError) as e:
            raise VaultDecryptionError(
                "Clave maestra incorrecta o archivo del vault alterado."
            ) from e
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise VaultCorruptFile(
                "Contenido desencriptado del vault corrupto o mal formado."
            ) from e

    def _encrypt_and_save_content(
        self, content: _VaultContent, master_key: bytes, salt: bytes
    ) -> None:
        # Prepare content for encryption
        entries_serializable = {
            name: {
                "username": entry.username,
                "password": entry.password,
                "updated_at": entry.updated_at.isoformat(),
            }
            for name, entry in content.entries.items()
        }
        plaintext_json_bytes = json.dumps({"entries": entries_serializable}, indent=2).encode()
        encrypted_payload = encrypt_payload(plaintext_json_bytes, master_key)

        # Create envelope: el KDF declarado debe describir lo que realmente se hizo.
        algo, iterations = self._expected_kdf()
        envelope = _VaultEnvelope(
            version=VAULT_VERSION,
            kdf=_KeyDerivationParams(
                algo=algo,
                iterations=iterations,
                salt=base64.b64encode(salt).decode(),
            ),
            key_custody=self._custody_backend,
            ciphertext=base64.b64encode(encrypted_payload).decode(),
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        # Ensure directory exists with correct permissions
        config_dir = _get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        # Set restrictive permissions for the directory
        current_mode = stat.S_IMODE(config_dir.stat().st_mode)
        if (current_mode & 0o777) != 0o700:  # Check only lower 9 bits
            config_dir.chmod(0o700)

        # Write to temporary file first, then atomically replace. The temporary file
        # is CREATED with the final mode (0600): no window where it exists as 0644.
        temp_vault_path = self._vault_path.with_name(f"{self._vault_path.name}.{os.getpid()}.tmp")
        try:
            if temp_vault_path.exists():
                temp_vault_path.unlink()
            fd = os.open(temp_vault_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                # `os.fchmod` is POSIX-only. On Windows `os.open` already applied
                # the mode and NTFS inherits the ACL from the config directory.
                fchmod = getattr(os, "fchmod", None)
                if fchmod is not None:
                    fchmod(fd, 0o600)  # immune to the process umask
                # `os.fdopen` takes ownership of the fd: from here the `with` closes it.
                handle = os.fdopen(fd, "w", encoding="utf-8")
            except BaseException:
                os.close(fd)
                raise
            with handle:
                json.dump(dataclasses.asdict(envelope), handle, indent=2)
            # os.replace preserves the mode of the source file (0600).
            os.replace(temp_vault_path, self._vault_path)
        except Exception as e:
            if temp_vault_path.exists():
                temp_vault_path.unlink()  # Clean up temp file on error
            raise VaultError(f"Error al guardar el vault en disco: {e}") from e

    def _get_master_key(self, prompt: str, for_write: bool = False) -> bytes:
        if self._master_key and not for_write:
            return self._master_key

        if self._custody_backend == "keychain":
            if for_write and not self._vault_path.exists():
                # Primera escritura: se genera una clave maestra aleatoria y se guarda
                # en el Keychain. NO se intenta leerla antes de crearla.
                new_key = Fernet.generate_key()  # 32 bytes aleatorios en base64 urlsafe
                raw_key = base64.urlsafe_b64decode(new_key)
                self._master_key_custody.store_master_key(raw_key)
                self._master_key = new_key
                return new_key
            master_key = self._master_key_custody.get_master_key(prompt)
            self._master_key = master_key
            return master_key
        elif self._custody_backend == "passphrase":
            if (
                for_write and not self._vault_path.exists()
            ):  # First time writing, need to generate salt
                salt = os.urandom(16)
                passphrase = getpass.getpass(prompt + " (para establecer nueva): ")
                passphrase_confirm = getpass.getpass("Confirme la frase de contraseña: ")
                if passphrase != passphrase_confirm:
                    raise VaultError("Las frases de contraseña no coinciden.")
                _validate_master_passphrase(passphrase)
                self._new_salt = salt
                self._master_key = derive_key(passphrase, salt)
                return self._master_key
            else:  # Existing vault: the salt lives in the envelope
                salt = self._read_envelope_salt()
                if salt is None:
                    raise VaultNotFound("El archivo del vault no existe.")
                passphrase = getpass.getpass(prompt + ": ")
                _validate_master_passphrase(passphrase)
                self._master_key = derive_key(passphrase, salt)
                return self._master_key
        elif self._custody_backend == "dpapi":
            return self._master_key_custody.get_master_key(prompt)
        else:
            raise ValueError(f"Backend de custodia desconocido: {self._custody_backend}")

    def set_entry(self, name: str, username: str, password: str) -> None:
        """
        Guarda una entrada de credenciales encriptada. Si existe, la actualiza.
        Solicita la clave maestra al operador.
        """
        master_key_read = None
        current_content = _VaultContent(entries={})
        salt = os.urandom(16)  # Default new salt

        if self._vault_path.exists():
            # Una clave maestra incorrecta NO debe sobrescribir el vault: el error se propaga.
            master_key_read = self._get_master_key("Ingrese la clave maestra", for_write=False)
            current_content = self._load_and_decrypt_content(master_key_read)

        if self._custody_backend == "keychain" and not self._vault_path.exists():
            # For keychain, if vault doesn't exist, we'll generate a new random key and store it
            # and then use that key for encryption.
            master_key_for_write = self._get_master_key(
                "Generando nueva clave maestra para Keychain", for_write=True
            )
            # El salt no se usa para derivar (la clave es aleatoria), pero se mantiene
            # estable entre escrituras para que el envelope describa una sola operación.
            salt = os.urandom(16)
        elif self._custody_backend == "passphrase" and not self._vault_path.exists():
            # For passphrase, a new vault derives the key from a new passphrase and salt.
            # El salt DEBE ser el mismo con el que se derivó la clave, si no el vault
            # quedaría ilegible en la siguiente lectura.
            master_key_for_write = self._get_master_key(
                "Establezca la clave maestra", for_write=True
            )
            salt = self._new_salt if self._new_salt else os.urandom(16)
        else:  # Existing vault (passphrase or keychain)
            master_key_for_write = (
                master_key_read
                if master_key_read
                else self._get_master_key(
                    "Ingrese la clave maestra para actualizar", for_write=False
                )
            )
            # El salt viene SIEMPRE del envelope existente (nunca del backend de custodia).
            existing_salt = self._read_envelope_salt()
            if existing_salt is not None:
                salt = existing_salt

        updated_at = datetime.datetime.now(datetime.UTC)
        current_content.entries[name] = Entry(username, password, updated_at)

        try:
            self._encrypt_and_save_content(current_content, master_key_for_write, salt)
        except VaultBackendUnavailable as e:
            raise VaultError(f"Error al guardar: {e}") from e
        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Error al guardar la entrada en el vault: {e}") from e

    def get_entry(self, name: str) -> Entry:
        """Recupera una entrada de credenciales desencriptada. Solicita la clave maestra."""
        self._require_vault_exists()
        master_key = self._get_master_key("Ingrese la clave maestra", for_write=False)
        content = self._load_and_decrypt_content(master_key)
        entry = content.entries.get(name)
        if not entry:
            raise VaultNotFound(f"Entrada '{name}' no encontrada en el vault.")
        return entry

    def list_entries(self) -> list[EntryMeta]:
        """Lista las entradas disponibles (solo metadatos, sin secretos)."""
        self._require_vault_exists()
        master_key = self._get_master_key("Ingrese la clave maestra", for_write=False)
        content = self._load_and_decrypt_content(master_key)
        return [
            EntryMeta(name=name, updated_at=entry.updated_at)
            for name, entry in content.entries.items()
        ]

    def delete_entry(self, name: str) -> None:
        """Elimina una entrada del vault. Solicita la clave maestra."""
        self._require_vault_exists()
        master_key = self._get_master_key("Ingrese la clave maestra", for_write=False)
        content = self._load_and_decrypt_content(master_key)
        if name not in content.entries:
            raise VaultNotFound(f"Entrada '{name}' no encontrada para eliminar.")
        del content.entries[name]
        try:
            # El salt viene del envelope (nunca del backend de custodia).
            salt = self._read_envelope_salt()
            if salt is None:
                raise VaultNotFound("El archivo del vault no existe.")
            self._encrypt_and_save_content(content, master_key, salt)
        except VaultBackendUnavailable as e:
            raise VaultError(f"Error al eliminar: {e}") from e
        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Error al eliminar la entrada del vault: {e}") from e

    def rotate_entry(self, name: str, new_username: str, new_password: str) -> None:
        """Rota una entrada existente con nuevas credenciales. Solicita la clave maestra."""
        self._require_vault_exists()
        master_key = self._get_master_key("Ingrese la clave maestra", for_write=False)
        content = self._load_and_decrypt_content(master_key)
        if name not in content.entries:
            raise VaultNotFound(f"Entrada '{name}' no encontrada para rotar.")
        updated_at = datetime.datetime.now(datetime.UTC)
        content.entries[name] = Entry(new_username, new_password, updated_at)
        try:
            # El salt viene del envelope (nunca del backend de custodia).
            salt = self._read_envelope_salt()
            if salt is None:
                raise VaultNotFound("El archivo del vault no existe.")
            self._encrypt_and_save_content(content, master_key, salt)
        except VaultBackendUnavailable as e:
            raise VaultError(f"Error al rotar: {e}") from e
        except VaultError:
            raise
        except Exception as e:
            raise VaultError(f"Error al rotar la entrada en el vault: {e}") from e

    def check(self) -> bool:
        """Verifica si el vault existe y es desencriptable.

        Retorna True si es válido, False si no.
        """
        if not self._vault_path.exists():
            return False

        try:
            # Attempt to get the master key and load the content
            master_key = self._get_master_key(
                "Ingrese la clave maestra para verificación", for_write=False
            )
            self._load_and_decrypt_content(master_key)
            return True
        except VaultNotFound:
            return False  # Should not happen if path exists, but just in case
        except VaultCorruptFile:
            return False
        except VaultDecryptionError:
            return False
        except VaultBackendUnavailable:
            return False
        except Exception:  # Catch any other unexpected errors
            return False

    def reveal_entry(self, name: str) -> tuple[str, str]:
        """Revela el username y password de una entrada. Solicita la clave maestra."""
        entry = self.get_entry(name)
        return entry.username, entry.password
