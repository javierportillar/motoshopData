"""Tests del vault de credenciales bancarias (`motoshop_api.erp.bankreconciliation.vault`).

Cobertura de las correcciones de la revisión de seguridad:
- C1: el `salt` pertenece al envelope, no al backend de custodia.
- C2: la frase de contraseña no puede estar vacía ni ser demasiado corta.
- C3: la clave maestra del Keychain NUNCA viaja en `argv`.
- W1/W3/W5/W6/W7/W8/W9/W10/W11/W12/W13/S1: ver los tests correspondientes.
"""

import base64
import datetime
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from motoshop_api.erp.bankreconciliation import cli
from motoshop_api.erp.bankreconciliation.vault import (
    CredentialVault,
    VaultBackendUnavailable,
    VaultCorruptFile,
    VaultDecryptionError,
    VaultError,
    VaultNotFound,
    _DpapiCustody,
    _get_config_dir,
    decrypt_payload,
    derive_key,
)

# --- Helpers ---


class _FakeSecurityProcess:
    """Proceso falso de `security add-generic-password`.

    Reproduce el prompt real ("password data for new item: retype password ...") y
    lee la clave desde la pseudo-terminal, igual que lo haría el binario original.
    """

    def __init__(self, cmd: list[str], stdin: int, on_secret) -> None:
        # Un proceso real hereda un duplicado del fd: el doble debe hacer lo mismo
        # para que la pty no se quede sin extremo esclavo.
        self._stdin = os.dup(stdin)
        self._on_secret = on_secret
        self._already_read = False
        self.returncode: int | None = None
        os.write(self._stdin, b"password data for new item: retype password for new item: ")

    def _read_secret(self) -> str:
        if self._already_read:
            return ""
        self._already_read = True
        try:
            return os.read(self._stdin, 4096).decode("ascii", errors="replace").strip()
        finally:
            os.close(self._stdin)

    def _finish(self) -> None:
        if self.returncode is None:
            self.returncode = 0
            self._on_secret(self._read_secret())

    def poll(self) -> int | None:
        self._finish()
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self._finish()
        return self.returncode  # type: ignore[return-value]

    def kill(self) -> None:
        self.returncode = -9


class _FakeKeychain:
    """Doble del Keychain de macOS, mockeado en la frontera del binario `security`."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.popen_argvs: list[list[str]] = []
        self.run_argvs: list[list[str]] = []
        self.stored_secrets: list[str] = []

    # `security find-generic-password` / `security delete-generic-password`
    def run(self, cmd, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        argv = list(cmd)
        self.run_argvs.append(argv)
        account = argv[argv.index("-a") + 1]
        service = argv[argv.index("-s") + 1]
        if argv[1] == "find-generic-password":
            value = self.items.get((service, account))
            if value is None:
                return subprocess.CompletedProcess(
                    argv,
                    44,
                    "",
                    "security: SecKeychainSearchCopyNext: "
                    "The specified item could not be found in the keychain.",
                )
            return subprocess.CompletedProcess(argv, 0, value + "\n", "")
        if argv[1] == "delete-generic-password":
            if (service, account) in self.items:
                del self.items[(service, account)]
                return subprocess.CompletedProcess(argv, 0, "", "")
            raise subprocess.CalledProcessError(
                44,
                argv,
                output="",
                stderr="security: SecKeychainSearchCopyNext: "
                "The specified item could not be found in the keychain.",
            )
        raise AssertionError(f"Comando `security` inesperado: {argv}")

    # `security add-generic-password` (la clave llega por la pty, nunca por argv)
    def popen(self, cmd, stdin=None, stdout=None, stderr=None, **kwargs):  # noqa: ANN001, ANN002, ANN003
        argv = list(cmd)
        assert argv[1] == "add-generic-password", argv
        self.popen_argvs.append(argv)
        account = argv[argv.index("-a") + 1]
        service = argv[argv.index("-s") + 1]

        def on_secret(secret: str) -> None:
            self.stored_secrets.append(secret)
            self.items[(service, account)] = secret

        return _FakeSecurityProcess(argv, stdin, on_secret)


@pytest.fixture
def fake_keychain(monkeypatch: pytest.MonkeyPatch):
    """Keychain de macOS simulado en la frontera del binario `security`."""
    fake = _FakeKeychain()
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(subprocess, "Popen", fake.popen)
    # El backend `keychain` sólo existe en macOS: se simula la plataforma para que
    # el test sea ejecutable en cualquier sistema.
    with patch("sys.platform", "darwin"):
        yield fake


@pytest.fixture
def temp_vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configura un entorno temporal para el vault (sin tocar el entorno global)."""
    # `monkeypatch.setenv` restaura el valor previo (o lo elimina) al final del test.
    # Se fijan las DOS variables: el código resuelve `XDG_CONFIG_HOME` en POSIX y
    # `APPDATA` en Windows. Sin `APPDATA` el test escribiría en el perfil REAL del
    # operador cuando corre en Windows.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    # La ruta se resuelve con la MISMA función que usa el código, no con una copia
    # de la regla: así el test vale en POSIX (XDG) y en Windows (APPDATA).
    config_dir = _get_config_dir()
    assert str(tmp_path) in str(config_dir), "el fixture tiene que aislar el config dir"
    return config_dir


@pytest.fixture
def mock_getpass():
    """Mock getpass.getpass para pruebas interactivas."""
    with patch("getpass.getpass") as mock:
        yield mock


@pytest.fixture
def vault_path(temp_vault_env: Path) -> Path:
    return temp_vault_env / "credentials.enc"


@pytest.fixture
def dummy_passphrase() -> str:
    return "una-clave-maestra-muy-segura"


@pytest.fixture
def dummy_master_key(dummy_passphrase: str) -> bytes:
    salt = b"\x9d\x1a>\xae\x0c\xec{\xda\xf9\xad\xfa\xfc\x92\x9d\x1a"  # Example salt
    return derive_key(dummy_passphrase, salt)


# --- Round-trip ---


def test_round_trip_set_get_entry(temp_vault_env: Path, mock_getpass, dummy_passphrase: str):
    """Verifica que set_entry y get_entry funcionan correctamente para ida y vuelta."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_bancolombia", "clave_secreta_123")

    entry = vault.get_entry("bancolombia")
    assert entry.username == "usuario_bancolombia"
    assert entry.password == "clave_secreta_123"
    assert isinstance(entry.updated_at, datetime.datetime)


def test_save_without_fchmod(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str, monkeypatch
):
    """Windows no tiene `os.fchmod`: guardar el vault no puede depender de él."""
    mock_getpass.return_value = dummy_passphrase
    monkeypatch.delattr(os, "fchmod", raising=False)

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia-masvital", "usuario_bancolombia", "clave_secreta_123")

    entry = vault.get_entry("bancolombia-masvital")
    assert entry.username == "usuario_bancolombia"
    assert entry.password == "clave_secreta_123"


def test_vault_readable_from_another_process(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """El vault debe poder leerse desde otro proceso (sin la clave en memoria).

    Regresión: el salt del envelope debe ser EXACTAMENTE el con el que se derivó
    la clave; si difieren, el vault queda ilegible para cualquier proceso nuevo.
    """
    mock_getpass.return_value = dummy_passphrase

    vault_escritor = CredentialVault(custody_backend="passphrase")
    vault_escritor.set_entry("bancolombia", "usuario_x", "clave_x")

    # Proceso nuevo: sin clave maestra cacheada, deriva desde el salt del envelope.
    vault_lector = CredentialVault(custody_backend="passphrase")
    entry = vault_lector.get_entry("bancolombia")

    assert entry.username == "usuario_x"
    assert entry.password == "clave_x"


# --- Confidencialidad del contenido en disco ---


def test_ciphertext_does_not_contain_plaintext(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Verifica que el archivo cifrado no expone usuario ni contraseña en texto plano."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_secreto", "clave_extremadamente_secreta_456")

    # Leer el archivo como bytes
    assert vault_path.exists()
    content_bytes = vault_path.read_bytes()

    assert b"usuario_secreto" not in content_bytes
    assert b"clave_extremadamente_secreta_456" not in content_bytes
    # El nombre de la entrada tampoco queda en claro: vive dentro del payload cifrado.
    assert b"bancolombia" not in content_bytes
    # El sobre sí contiene metadata no sensible (kdf, versión, ciphertext).
    assert b"pbkdf2_hmac_sha256" in content_bytes


def test_entry_name_lives_inside_the_encrypted_payload(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """El nombre de la entrada debe estar DENTRO del payload cifrado, no en el sobre."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_secreto", "clave_secreta")

    envelope = json.loads(vault_path.read_text())
    salt = base64.b64decode(envelope["kdf"]["salt"])
    master_key = derive_key(dummy_passphrase, salt)
    plaintext = decrypt_payload(base64.b64decode(envelope["ciphertext"]), master_key)

    # El nombre SÍ está en el payload cifrado...
    assert b"bancolombia" in plaintext
    # ...y NO en los bytes crudos del archivo.
    assert b"bancolombia" not in vault_path.read_bytes()


# --- Clave maestra incorrecta / archivo alterado ---


def test_wrong_master_passphrase_raises_decryption_error(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Intentar desencriptar con una clave maestra incorrecta debe lanzar VaultDecryptionError."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")

    # Intentar obtener con una clave maestra incorrecta, desde una instancia nueva
    # (como lo haría un proceso nuevo que no tiene la clave en memoria).
    mock_getpass.return_value = "clave-maestra-incorrecta"
    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(
        VaultDecryptionError, match="Clave maestra incorrecta o archivo del vault alterado"
    ):
        vault_otro_proceso.get_entry("bancolombia")


def test_wrong_passphrase_never_overwrites_the_vault(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Un `set` con frase de contraseña incorrecta NO puede sobrescribir el vault.

    Es el test anti-overwrite real: se capturan los bytes del archivo, se intenta
    escribir con una clave maestra equivocada y se comprueba que el archivo queda
    byte a byte idéntico.
    """
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")
    original_bytes = vault_path.read_bytes()

    # Proceso nuevo (sin clave en memoria) con una frase de contraseña incorrecta.
    mock_getpass.return_value = "clave-maestra-incorrecta"
    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultDecryptionError):
        vault_otro_proceso.set_entry("bancolombia", "atacante", "clave_del_atacante")

    # El archivo NO se modificó ni un byte.
    assert vault_path.read_bytes() == original_bytes
    # Y el contenido legítimo sigue siendo el original.
    mock_getpass.return_value = dummy_passphrase
    vault_lector = CredentialVault(custody_backend="passphrase")
    entry = vault_lector.get_entry("bancolombia")
    assert entry.username == "usuario_test"
    assert entry.password == "clave_test"


def test_tampered_ciphertext_raises_decryption_error(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Un archivo alterado debe lanzar VaultDecryptionError."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")

    # Cargar el contenido, modificar el ciphertext y reescribir
    assert vault_path.exists()
    with vault_path.open("r+") as f:
        envelope_data = json.load(f)
        tampered_ciphertext = envelope_data["ciphertext"]
        # Alterar un byte aleatorio para simular manipulación
        tampered_bytes = base64.b64decode(tampered_ciphertext)
        tampered_list = list(tampered_bytes)
        tampered_list[10] = (tampered_list[10] + 1) % 256  # Flip a byte
        envelope_data["ciphertext"] = base64.b64encode(bytes(tampered_list)).decode()

        f.seek(0)
        json.dump(envelope_data, f, indent=2)
        f.truncate()

    # Intentar obtener con la frase de contraseña correcta desde una instancia nueva
    mock_getpass.return_value = dummy_passphrase
    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(
        VaultDecryptionError, match="Clave maestra incorrecta o archivo del vault alterado"
    ):
        vault_otro_proceso.get_entry("bancolombia")


# --- W1: excepciones tipadas ante archivos corruptos ---


def test_corrupted_ciphertext_raises_vault_corrupt_file(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Un ciphertext con base64 inválido debe lanzar VaultCorruptFile (no ValueError)."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")

    envelope = json.loads(vault_path.read_text())
    envelope["ciphertext"] = "no-es-base64-valido!!!"
    vault_path.write_text(json.dumps(envelope, indent=2))

    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultCorruptFile):
        vault_otro_proceso.get_entry("bancolombia")


def test_corrupted_salt_raises_vault_corrupt_file(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Un salt corrupto debe lanzar VaultCorruptFile (no binascii.Error)."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")

    envelope = json.loads(vault_path.read_text())
    envelope["kdf"]["salt"] = "!!! no base64 !!!"
    vault_path.write_text(json.dumps(envelope, indent=2))

    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultCorruptFile):
        vault_otro_proceso.get_entry("bancolombia")


def test_malformed_envelope_raises_vault_corrupt_file(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Un envelope sin la estructura esperada debe lanzar VaultCorruptFile."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")

    vault_path.write_text(json.dumps({"version": 1}, indent=2))

    vault_otro_proceso = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultCorruptFile):
        vault_otro_proceso.get_entry("bancolombia")


# --- Consultas ---


def test_missing_entry_raises_vault_not_found(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """Intentar obtener una entrada inexistente debe lanzar VaultNotFound."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario", "clave")

    with pytest.raises(VaultNotFound, match="Entrada 'otra_credencial' no encontrada"):
        vault.get_entry("otra_credencial")


def test_list_entries_exposes_no_secret_material(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """list_entries no debe exponer nombres de usuario o contraseñas."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("entry1", "user1", "pass1")
    vault.set_entry("entry2", "user2", "pass2")

    entries_meta = vault.list_entries()
    assert len(entries_meta) == 2
    assert all(isinstance(em.name, str) for em in entries_meta)
    assert all(isinstance(em.updated_at, datetime.datetime) for em in entries_meta)

    # Verificar que no hay datos sensibles
    for em in entries_meta:
        assert "user" not in em.name.lower()
        assert "pass" not in em.name.lower()

    # Re-verify by inspecting actual content from list_entries
    names = {em.name for em in entries_meta}
    assert "entry1" in names
    assert "entry2" in names

    # Check that EntryMeta doesn't have username/password attributes
    with pytest.raises(AttributeError):
        _ = entries_meta[0].username  # type: ignore
    with pytest.raises(AttributeError):
        _ = entries_meta[0].password  # type: ignore


# --- W13: fallar rápido si el vault no existe (sin pedir la clave maestra) ---


def test_list_does_not_prompt_when_vault_is_missing(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """`list` sobre un vault inexistente falla antes de pedir la clave maestra."""
    mock_getpass.return_value = dummy_passphrase
    mock_getpass.reset_mock()

    vault = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultNotFound, match="no existe"):
        vault.list_entries()

    mock_getpass.assert_not_called()


def test_get_entry_does_not_prompt_when_vault_is_missing(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """`reveal` sobre un vault inexistente falla antes de pedir la clave maestra."""
    mock_getpass.return_value = dummy_passphrase
    mock_getpass.reset_mock()

    vault = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultNotFound, match="no existe"):
        vault.get_entry("bancolombia")

    mock_getpass.assert_not_called()


# --- Permisos ---


@pytest.mark.skipif(
    sys.platform == "win32", reason="File permissions behave differently on Windows"
)
def test_file_and_directory_permissions(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Verifica que los permisos del archivo y el directorio son 0o600 y 0o700 respectivamente."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_permisos", "clave_permisos")

    assert vault_path.exists()
    assert vault_path.parent.exists()

    # Verificar permisos del archivo (0o600)
    file_mode = stat.S_IMODE(vault_path.stat().st_mode)
    assert (file_mode & 0o777) == 0o600

    # Verificar permisos del directorio (0o700)
    dir_mode = stat.S_IMODE(vault_path.parent.stat().st_mode)
    assert (dir_mode & 0o777) == 0o700


@pytest.mark.skipif(
    sys.platform == "win32", reason="File permissions behave differently on Windows"
)
def test_no_temporary_file_is_left_behind(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """La escritura atómica no debe dejar archivos temporales en el directorio."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")
    vault.rotate_entry("bancolombia", "usuario_test2", "clave_test2")
    vault.delete_entry("bancolombia")

    leftovers = [p.name for p in vault_path.parent.iterdir() if p.name != vault_path.name]
    assert leftovers == []


def test_failed_write_keeps_the_previous_vault_intact(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Si la escritura falla a mitad, el vault anterior queda intacto y sin temporales."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario_test", "clave_test")
    original_bytes = vault_path.read_bytes()

    with (
        patch(
            "motoshop_api.erp.bankreconciliation.vault.json.dump",
            side_effect=OSError("disco lleno"),
        ),
        pytest.raises(VaultError),
    ):
        vault.set_entry("otra", "usuario_nuevo", "clave_nueva")

    # El vault anterior no se tocó y no quedó ningún temporal.
    assert vault_path.read_bytes() == original_bytes
    leftovers = [p.name for p in vault_path.parent.iterdir() if p.name != vault_path.name]
    assert leftovers == []


# --- Operaciones de escritura ---


def test_delete_entry_removes_it(temp_vault_env: Path, mock_getpass, dummy_passphrase: str):
    """Verifica que delete_entry elimina correctamente una entrada."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("para_borrar", "usuario_del", "clave_del")

    entries_before_delete = vault.list_entries()
    assert len(entries_before_delete) == 1

    vault.delete_entry("para_borrar")

    entries_after_delete = vault.list_entries()
    assert len(entries_after_delete) == 0

    with pytest.raises(VaultNotFound):
        vault.get_entry("para_borrar")


def test_rotate_entry_updates_credentials(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """Verifica que rotate_entry actualiza el usuario y la clave de una entrada existente."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "old_user", "old_pass")

    entry_before_rotate = vault.get_entry("bancolombia")
    assert entry_before_rotate.username == "old_user"
    assert entry_before_rotate.password == "old_pass"

    vault.rotate_entry("bancolombia", "new_user", "new_pass")

    entry_after_rotate = vault.get_entry("bancolombia")
    assert entry_after_rotate.username == "new_user"
    assert entry_after_rotate.password == "new_pass"
    assert entry_after_rotate.updated_at > entry_before_rotate.updated_at


def test_initial_vault_creation_writes_correct_envelope(
    temp_vault_env: Path, mock_getpass, vault_path: Path, dummy_passphrase: str
):
    """Verifica que la creación inicial del vault escribe un envelope bien formado."""
    mock_getpass.return_value = dummy_passphrase

    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "user_initial", "pass_initial")

    assert vault_path.exists()
    envelope_data = json.loads(vault_path.read_text())

    assert envelope_data["version"] == 1
    assert envelope_data["key_custody"] == "passphrase"
    assert "ciphertext" in envelope_data
    assert "created_at" in envelope_data
    assert "kdf" in envelope_data
    assert envelope_data["kdf"]["algo"] == "pbkdf2_hmac_sha256"
    assert envelope_data["kdf"]["iterations"] == 600000
    assert "salt" in envelope_data["kdf"]
    assert base64.b64decode(envelope_data["kdf"]["salt"])


# --- C2: la frase de contraseña no puede estar vacía ni ser corta ---


def test_empty_passphrase_is_rejected(
    temp_vault_env: Path, mock_getpass, vault_path: Path
):
    """Una frase de contraseña vacía debe fallar y NO debe crear el archivo del vault."""
    mock_getpass.return_value = ""

    vault = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultError, match="no puede estar vacía"):
        vault.set_entry("bancolombia", "usuario", "clave")

    assert not vault_path.exists()


def test_short_passphrase_is_rejected(
    temp_vault_env: Path, mock_getpass, vault_path: Path
):
    """Una frase de contraseña de menos de 8 caracteres debe fallar sin crear el vault."""
    mock_getpass.return_value = "1234567"  # 7 caracteres

    vault = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultError, match="demasiado corta"):
        vault.set_entry("bancolombia", "usuario", "clave")

    assert not vault_path.exists()


def test_empty_passphrase_is_rejected_on_read(
    temp_vault_env: Path, mock_getpass, dummy_passphrase: str
):
    """Leer el vault con una frase vacía debe fallar con un error claro."""
    mock_getpass.return_value = dummy_passphrase
    vault = CredentialVault(custody_backend="passphrase")
    vault.set_entry("bancolombia", "usuario", "clave")

    mock_getpass.return_value = ""
    vault_lector = CredentialVault(custody_backend="passphrase")
    with pytest.raises(VaultError, match="no puede estar vacía"):
        vault_lector.get_entry("bancolombia")


# --- W9: el backend `dpapi` no está implementado ---


def test_dpapi_backend_raises_unavailable(temp_vault_env: Path):
    """El backend DPAPI no está implementado: debe fallar con VaultBackendUnavailable."""
    if sys.platform != "win32":
        with pytest.raises(VaultBackendUnavailable, match="dpapi"):
            CredentialVault(custody_backend="dpapi")
    else:
        vault = CredentialVault(custody_backend="dpapi")
        assert vault._custody_backend == "dpapi"
        with pytest.raises(VaultBackendUnavailable, match="no está implementado"):
            vault.check()


def test_dpapi_is_not_a_cli_choice(
    temp_vault_env: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """El backend `dpapi` no debe ofrecerse en la CLI hasta que exista."""
    monkeypatch.setattr(sys, "argv", ["motoshop-vault", "--backend", "dpapi", "list"])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "dpapi" in captured.err


# --- W7: el directorio de configuración NO se cachea ---


@pytest.mark.skipif(sys.platform == "win32", reason="Usa XDG_CONFIG_HOME (POSIX)")
def test_config_dir_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cambiar `XDG_CONFIG_HOME` debe cambiar el directorio resuelto (sin cache_clear)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "uno"))
    first = _get_config_dir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "dos"))
    second = _get_config_dir()

    assert first == tmp_path / "uno" / "motoshop"
    assert second == tmp_path / "dos" / "motoshop"
    assert first != second


# --- C1 / W5 / W10 / W11: backend `keychain` ---


def test_keychain_backend_skipped_on_non_macos(temp_vault_env: Path):
    """Verifica que el backend de keychain lanza un error en plataformas que no son macOS."""
    if sys.platform != "darwin":
        with pytest.raises(VaultBackendUnavailable, match="keychain"):
            CredentialVault(custody_backend="keychain")
    else:
        vault = CredentialVault(custody_backend="keychain")
        assert vault._custody_backend == "keychain"


def test_keychain_set_rotate_delete(
    temp_vault_env: Path, mock_getpass, fake_keychain: _FakeKeychain, vault_path: Path
):
    """El backend `keychain` debe soportar set → rotate → delete.

    Regresión de C1: `delete_entry` y `rotate_entry` NO pueden depender de un
    método que sólo existe en el backend `passphrase`.
    """
    vault = CredentialVault(custody_backend="keychain")
    vault.set_entry("bancolombia", "usuario_kc", "clave_kc")

    assert vault_path.exists()
    assert fake_keychain.items, "la clave maestra debió guardarse en el Keychain"

    vault.rotate_entry("bancolombia", "usuario_kc2", "clave_kc2")
    vault.delete_entry("bancolombia")

    vault_lector = CredentialVault(custody_backend="keychain")
    assert vault_lector.list_entries() == []


def test_keychain_secret_never_appears_in_argv(
    temp_vault_env: Path, fake_keychain: _FakeKeychain, vault_path: Path
):
    """C3: la clave maestra NUNCA debe ir en `argv` (quedaría visible en `ps`)."""
    vault = CredentialVault(custody_backend="keychain")
    vault.set_entry("bancolombia", "usuario_kc", "clave_kc")

    assert fake_keychain.popen_argvs, "se esperaba una llamada a `security add-generic-password`"
    for argv in fake_keychain.popen_argvs:
        # `-w` debe ser la ÚLTIMA opción y sin valor: el propio `security` pregunta.
        assert argv[-1] == "-w"
        assert "-w" not in argv[:-1]
        # Ningún argumento puede contener el secreto (ni una clave de 44 chars).
        for arg in argv:
            assert "clave_kc" not in arg
        assert fake_keychain.stored_secrets
        for secret in fake_keychain.stored_secrets:
            assert secret not in " ".join(argv)
            assert not any(secret in arg for arg in argv)


def test_keychain_envelope_declares_the_real_kdf(
    temp_vault_env: Path, fake_keychain: _FakeKeychain, vault_path: Path
):
    """W10: el envelope debe describir lo que realmente se hizo (clave aleatoria)."""
    vault = CredentialVault(custody_backend="keychain")
    vault.set_entry("bancolombia", "usuario_kc", "clave_kc")

    envelope = json.loads(vault_path.read_text())
    assert envelope["key_custody"] == "keychain"
    assert envelope["kdf"]["algo"] == "random"
    assert envelope["kdf"]["iterations"] == 0

    # El salt debe permanecer estable entre escrituras.
    first_salt = envelope["kdf"]["salt"]
    vault.rotate_entry("bancolombia", "usuario_kc2", "clave_kc2")
    second_envelope = json.loads(vault_path.read_text())
    assert second_envelope["kdf"]["salt"] == first_salt


def test_keychain_vault_stays_readable_across_writes(
    temp_vault_env: Path, fake_keychain: _FakeKeychain, vault_path: Path
):
    """Un vault de `keychain` debe seguir siendo legible tras varias escrituras."""
    vault = CredentialVault(custody_backend="keychain")
    vault.set_entry("bancolombia", "usuario_kc", "clave_kc")

    vault_lector = CredentialVault(custody_backend="keychain")
    entry = vault_lector.get_entry("bancolombia")
    assert entry.username == "usuario_kc"
    assert entry.password == "clave_kc"

    vault.rotate_entry("bancolombia", "usuario_kc2", "clave_kc2")
    vault_lector_2 = CredentialVault(custody_backend="keychain")
    entry = vault_lector_2.get_entry("bancolombia")
    assert entry.username == "usuario_kc2"


def test_keychain_missing_item_raises_vault_not_found(
    temp_vault_env: Path, fake_keychain: _FakeKeychain
):
    """W11: un ítem ausente en el Keychain debe conservar el tipo VaultNotFound."""
    vault = CredentialVault(custody_backend="keychain")
    with pytest.raises(VaultNotFound) as exc_info:
        vault.list_entries()
    # No debe re-envolverse en un VaultError genérico.
    assert exc_info.value.__class__ is VaultNotFound


def test_keychain_malformed_key_raises_vault_error(
    temp_vault_env: Path, fake_keychain: _FakeKeychain, vault_path: Path
):
    """Una clave maestra corrupta en el Keychain debe producir un error tipado."""
    vault = CredentialVault(custody_backend="keychain")
    vault.set_entry("bancolombia", "usuario_kc", "clave_kc")

    # Se corrompe la clave custodiada: ya no es una clave Fernet válida.
    fake_keychain.items[("motoshop-bank-vault", "master-key")] = "no-es-una-clave-fernet"

    vault_lector = CredentialVault(custody_backend="keychain")
    with pytest.raises(VaultError) as exc_info:
        vault_lector.list_entries()
    assert not isinstance(exc_info.value, VaultNotFound)


# --- CLI ---


def _cli_run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["motoshop-vault", *argv])
    cli.main()


def _cli_create_vault(
    monkeypatch: pytest.MonkeyPatch,
    mock_getpass,
    name: str = "bancolombia",
    username: str = "usuario_secreto",
    password: str = "clave_secreta_456",
    passphrase: str = "una-clave-maestra-muy-segura",
) -> None:
    mock_getpass.side_effect = [username, password, passphrase, passphrase]
    _cli_run(monkeypatch, "set", name)


def test_cli_set_then_list_emits_no_secret_material(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """`list` no debe emitir ningún material secreto (usuario ni contraseña)."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    mock_getpass.side_effect = ["una-clave-maestra-muy-segura"]
    _cli_run(monkeypatch, "list")
    captured = capsys.readouterr()

    assert "usuario_secreto" not in captured.out
    assert "clave_secreta_456" not in captured.out
    assert "una-clave-maestra-muy-segura" not in captured.out
    assert "bancolombia" in captured.out  # el nombre sí es metadata


def test_cli_check_exits_zero_when_readable(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """`check` sobre un vault legible termina con código 0."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    mock_getpass.side_effect = ["una-clave-maestra-muy-segura"]
    _cli_run(monkeypatch, "check")
    captured = capsys.readouterr()

    assert "Vault: OK" in captured.out


def test_cli_check_exits_one_when_vault_is_missing(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """`check` sobre un vault inexistente termina con código 1."""
    with pytest.raises(SystemExit) as exc_info:
        _cli_run(monkeypatch, "check")
    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert "NO ACCESIBLE" in captured.out


def test_cli_reveal_without_flag_exits_two(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """`reveal` sin `--yes-i-understand` debe terminar con código 2 y un mensaje claro."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc_info:
        _cli_run(monkeypatch, "reveal", "bancolombia")
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert "--yes-i-understand" in captured.err
    assert "usuario_secreto" not in captured.out


def test_cli_wrong_passphrase_exits_one_with_message(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """Una frase de contraseña incorrecta debe terminar con código 1 y un mensaje no vacío."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    mock_getpass.side_effect = ["frase-maestra-equivocada"]
    with pytest.raises(SystemExit) as exc_info:
        _cli_run(monkeypatch, "list")
    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert captured.err.strip() != ""
    assert "ERROR" in captured.err


def test_cli_non_interactive_stdin_exits_one_with_actionable_message(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """W12: una entrada estándar no interactiva debe dar un mensaje accionable."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    mock_getpass.side_effect = EOFError
    with pytest.raises(SystemExit) as exc_info:
        _cli_run(monkeypatch, "list")
    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert captured.err.strip() != ""
    assert "no es interactiva" in captured.err


def test_cli_reveal_with_flag_prints_credentials(
    temp_vault_env: Path,
    mock_getpass,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
):
    """`reveal --yes-i-understand` sigue funcionando (comportamiento documentado)."""
    _cli_create_vault(monkeypatch, mock_getpass)
    capsys.readouterr()

    mock_getpass.side_effect = ["una-clave-maestra-muy-segura"]
    _cli_run(monkeypatch, "reveal", "bancolombia", "--yes-i-understand")
    captured = capsys.readouterr()

    assert "usuario_secreto" in captured.out
    assert "clave_secreta_456" in captured.out


# --- DPAPI (Windows) ---


class _FakeDpapi:
    """Custodia DPAPI simulada: guarda la clave en memoria.

    Se inyecta en `CredentialVault(custody=...)` para probar el flujo completo en
    cualquier plataforma: lo que se ejercita es el vault, no la API de Windows.
    """

    def __init__(self, clave: bytes | None = None) -> None:
        self.clave = clave
        self.llamadas: list[str] = []

    def get_master_key(self, prompt: str) -> bytes:
        self.llamadas.append("get")
        if self.clave is None:
            raise VaultNotFound("sin clave maestra")
        return base64.urlsafe_b64encode(self.clave)

    def store_master_key(self, master_key: bytes) -> None:
        self.llamadas.append("store")
        self.clave = master_key

    def delete_master_key(self) -> None:
        self.llamadas.append("delete")
        self.clave = None


def test_dpapi_guarda_y_lee_sin_pedir_frase(temp_vault_env: Path, mock_getpass):
    """Con DPAPI no hay frase maestra: el operador no escribe nada."""
    custody = _FakeDpapi()
    vault = CredentialVault(custody_backend="dpapi", custody=custody)

    vault.set_entry("bancolombia-motoshop", "usuario_dpapi", "clave_dpapi_123")
    entry = vault.get_entry("bancolombia-motoshop")

    assert entry.username == "usuario_dpapi"
    assert entry.password == "clave_dpapi_123"
    mock_getpass.assert_not_called()
    # La clave queda cacheada en la instancia: leer con el mismo vault no vuelve
    # a tocar la custodia. Un vault nuevo sí tiene que recuperarla del blob.
    assert custody.llamadas == ["store"]

    otro = CredentialVault(custody_backend="dpapi", custody=custody)
    assert otro.get_entry("bancolombia-motoshop").password == "clave_dpapi_123"
    assert custody.llamadas == ["store", "get"]


def test_dpapi_declara_kdf_random_y_custodia_dpapi(temp_vault_env: Path, vault_path: Path):
    """El sobre tiene que describir lo que se hizo: clave aleatoria, custodia DPAPI."""
    CredentialVault(custody_backend="dpapi", custody=_FakeDpapi()).set_entry(
        "bancolombia-motoshop", "usuario_dpapi", "clave_dpapi_123"
    )

    sobre = json.loads(vault_path.read_text(encoding="utf-8"))

    assert sobre["key_custody"] == "dpapi"
    assert sobre["kdf"]["algo"] == "random"


def test_dpapi_rechaza_una_clave_maestra_ajena(temp_vault_env: Path):
    """Si el blob DPAPI no es el que protegió el vault, no se puede leer."""
    CredentialVault(custody_backend="dpapi", custody=_FakeDpapi(b"\x01" * 32)).set_entry(
        "bancolombia-motoshop", "usuario_dpapi", "clave_dpapi_123"
    )

    ajeno = CredentialVault(custody_backend="dpapi", custody=_FakeDpapi(b"\x02" * 32))
    with pytest.raises(VaultDecryptionError):
        ajeno.get_entry("bancolombia-motoshop")


def test_dpapi_sin_clave_maestra_reporta_vault_not_found(temp_vault_env: Path):
    """Vault presente pero sin blob DPAPI: falta la clave, no es un archivo corrupto."""
    CredentialVault(custody_backend="dpapi", custody=_FakeDpapi()).set_entry(
        "bancolombia-motoshop", "usuario_dpapi", "clave_dpapi_123"
    )

    sin_clave = CredentialVault(custody_backend="dpapi", custody=_FakeDpapi(clave=None))
    with pytest.raises(VaultNotFound):
        sin_clave.get_entry("bancolombia-motoshop")


def test_dpapi_guarda_el_blob_con_permisos_restringidos(
    temp_vault_env: Path, monkeypatch: pytest.MonkeyPatch
):
    """El archivo de la clave se crea 0600 y nunca guarda la clave en claro."""
    from motoshop_api.erp.bankreconciliation import vault as vault_module

    # DPAPI no existe fuera de Windows: se reemplaza sólo la transformación
    # criptográfica (invertir bytes es simétrico), no el manejo del archivo.
    monkeypatch.setattr(
        vault_module,
        "_dpapi_transform",
        lambda data, *, desproteger: bytes(reversed(data)),
    )
    ruta = temp_vault_env / "master.key.dpapi"
    custody = _DpapiCustody(ruta)
    # Clave no palindrómica: si la transformación no se aplicara, el archivo
    # guardaría la clave en claro y el test lo detectaría.
    clave = bytes(range(32))

    custody.store_master_key(clave)

    assert ruta.exists()
    assert ruta.read_bytes() == bytes(reversed(clave))
    assert clave not in ruta.read_bytes()
    if os.name == "posix":
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert custody.get_master_key("") == base64.urlsafe_b64encode(clave)


@pytest.mark.skipif(sys.platform == "win32", reason="DPAPI sólo existe en Windows")
def test_dpapi_no_esta_disponible_fuera_de_windows():
    """En macOS/Linux el backend tiene que fallar rápido y explícito."""
    with pytest.raises(VaultBackendUnavailable):
        CredentialVault(custody_backend="dpapi")


@pytest.mark.skipif(sys.platform != "win32", reason="Requiere DPAPI real de Windows")
def test_dpapi_round_trip_real_en_windows(temp_vault_env: Path):
    """En el nodo Windows: proteger y desproteger una clave real, sin diálogos."""
    from motoshop_api.erp.bankreconciliation.vault import _dpapi_transform

    clave = b"\x2a" * 32
    protegida = _dpapi_transform(clave, desproteger=False)

    assert protegida != clave
    assert _dpapi_transform(protegida, desproteger=True) == clave
