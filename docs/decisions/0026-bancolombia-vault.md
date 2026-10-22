# ADR-0026 · Vault de Credenciales para Bancolombia

- **Estado:** Proposed
- **Fecha:** 2026-10-21
- **Bloquea:** Implementación de la reconciliación bancaria automatizada.
- **Decide:** Equipo de Backend

## Contexto

El proceso de reconciliación bancaria con Bancolombia requiere acceder a un portal web con credenciales. Estas credenciales son secretas y no deben ser almacenadas en texto plano en el código fuente, en variables de entorno, en archivos `.env`, ni en logs, ni pasadas por línea de comandos directamente. Se necesita una solución segura para que el operador pueda almacenar y recuperar estas credenciales en su máquina local de forma encriptada.

## Opciones consideradas

1.  **Archivo de texto plano o `.env`:** PROHIBIDO por motivos de seguridad.
2.  **Vault de HashiCorp o similar:** Complejo y sobredimensionado para una única máquina de operador. Requiere infraestructura adicional y gestión de secretos centralizada, lo cual está fuera del alcance de este requerimiento local.
3.  **Sistema de gestión de secretos del SO (Keychain/DPAPI) directo:** Permite el almacenamiento seguro, pero no es cross-platform directamente para el mismo formato de dato encriptado.
4.  **Vault local encriptado con clave maestra derivada/custodiada:** Un archivo local encriptado con una clave derivada de una frase de contraseña o custodiada por el sistema operativo (Keychain/DPAPI), ofreciendo un balance entre seguridad y facilidad de uso local.

## Decisión

Implementar un vault local encriptado con la opción (4), usando Fernet de la librería `cryptography` para el cifrado simétrico (AES-128-CBC + HMAC-SHA256) y PBKDF2-HMAC-SHA256 para la derivación de la clave maestra a partir de una frase de contraseña.

### Detalles técnicos

*   **Cifrado:** `cryptography.fernet.Fernet` (basado en AES-128-CBC para el cifrado y HMAC-SHA256 para la autenticación).
*   **Derivación de clave (KDF):** `hashlib.pbkdf2_hmac("sha256", passphrase, salt, iterations, dklen=32)`. Las iteraciones se fijan en `600,000` para resistencia a ataques de fuerza bruta. La clave derivada se codifica en base64 urlsafe para usar con Fernet.
*   **Contraseña maestra mínima:** la frase de contraseña del backend `passphrase` **no puede estar vacía** y debe tener **al menos 8 caracteres**. Sin este control, PBKDF2 derivaría una clave a partir de una cadena vacía y el vault quedaría Protected sólo por el formato del archivo. La regla se aplica tanto al crear el vault como al leerlo.
*   **Custodia de la clave maestra:**
    *   **`passphrase` (por defecto):** La clave maestra se deriva en cada uso a partir de una frase de contraseña que el operador introduce. El `salt` para PBKDF2 se almacena en el envelope del vault, en texto plano (no es secreto, solo un modificador de la frase de contraseña). El `salt` **pertenece al envelope, no al backend de custodia**: se lee del archivo en cada operación de escritura, de modo que cualquier backend pueda reescribir el vault sin conocer el KDF del otro.
    *   **`keychain` (macOS):** La clave maestra *raw* (32 bytes aleatorios, base64-urlsafe) se genera una vez y se guarda en el macOS Keychain usando el comando `security`. El envelope del vault registra `key_custody: "keychain"` y `kdf.algo: "random"` con `iterations: 0`, porque **no hay derivación**: la clave es aleatoria y la custodia vive en el Keychain. El envelope debe describir lo que realmente se hizo, nunca un KDF que no se aplicó. El `salt` del envelope se mantiene estable entre escrituras (no participa de la derivación, pero evita ruido innecesario en el sobre).
        *   **La clave maestra nunca viaja en `argv`.** `security add-generic-password` se invoca con `-w` como **última opción y sin valor**, de modo que sea el propio binario el que pregunte la clave por terminal; la respuesta se escribe en el maestro de una pseudo-terminal (`pty.openpty()`) creada por el proceso, con el eco del terminal desactivado y el hijo lanzado en una sesión nueva (`start_new_session=True`) para que no tenga terminal de control. Un secreto en `argv` sería visible para cualquier usuario local mediante `ps`. Si la pseudo-terminal no puede usarse, la operación falla con un `VaultError` explícito: **no** se recurre nunca a pasar el secreto por la línea de comandos.
    *   **`dpapi` (Windows):** **NO IMPLEMENTADO.** La custodia mediante `CryptProtectData`/`CryptUnprotectData` queda fuera de alcance. Mientras tanto, el backend lanza `VaultBackendUnavailable` en cualquier plataforma (incluido Windows) y **no se ofrece en las opciones de la CLI** (`--backend` sólo acepta `passphrase` y `keychain`), de modo que no se pueda seleccionar una vía que no funciona.
*   **Ubicación del archivo:**
    *   POSIX (`macOS`, `Linux`): `$XDG_CONFIG_HOME/motoshop/credentials.enc` o `~/.config/motoshop/credentials.enc`.
    *   Windows: `%APPDATA%\motoshop\credentials.enc`.
    *   La ruta se resuelve **en cada llamada** (sin caché): depende de `XDG_CONFIG_HOME`/`APPDATA` y un valor cacheado ignoraría los cambios de configuración del proceso.
*   **Permisos del archivo:**
    *   Directorio (`motoshop`): `0o700` (solo lectura/escritura/ejecución para el propietario).
    *   Archivo (`credentials.enc`): `0o600` (solo lectura/escritura para el propietario).
    *   El archivo se escribe de forma **atómica**: se crea el temporal con `os.open(..., O_CREAT | O_EXCL, 0o600)` —con el modo final desde el primer instante, nunca `0644`— y luego se renombra con `os.replace`, que conserva el modo `0600`.
*   **Formato del envelope:** Un archivo JSON que contiene metadatos no sensibles (`version`, `kdf` params, `key_custody`, `created_at`) y un `ciphertext` que es el payload completo de las entradas encriptado.
*   **Seguridad del contenido:** El **nombre** de la entrada y sus campos `username` y `password` se almacenan *dentro* del payload encriptado, nunca en el envelope en texto plano.
*   **No logging de secretos:** El vault y la CLI tienen prohibido registrar secretos, frases de contraseña o claves maestras en logs o stdout (excepto el comando `reveal` con confirmación explícita). Los errores que incluyan datos del prompt de Keychain sustituyen el secreto por `<redacted>` antes de mostrarse.
*   **Errores tipados:** todo fallo del vault se expresa con la jerarquía `VaultError` → `VaultNotFound` | `VaultDecryptionError` | `VaultCorruptFile` | `VaultBackendUnavailable`. Un base64 inválido o una clave maestra malformada producen `VaultCorruptFile`/`VaultError`, nunca un `ValueError`/`binascii.Error` crudo.

### Restricciones aplicadas

*   **Prohibido Keyfile Backend:** No se permite un backend que guarde la clave maestra en un archivo junto al ciphertext. Esto anularía la seguridad del cifrado.
*   **No environment variables:** La solución debe funcionar sin depender de variables de entorno para los secretos del vault (sí usa `XDG_CONFIG_HOME` o `APPDATA` para la ubicación).
*   **Prohibido el secreto en `argv`:** la clave maestra no puede aparecer en los argumentos de ningún proceso (visible con `ps`).

## Consecuencias

*   **Runtime Dependency:** La librería `cryptography` se convierte en una dependencia de runtime para `motoshop-app/api`.
*   **Seguridad mejorada:** Reduce drásticamente el riesgo de exposición accidental de credenciales en repositorios, logs o configuraciones de entorno.
*   **UX del backend `keychain`:** el prompt de `security` pide la clave **dos veces** (`password data for new item:` y `retype password for new item:`); la implementación responde automáticamente a ambos. El operador no ve la clave en pantalla (eco desactivado).
*   **Experiencia del operador:** Requiere interacción manual para la clave maestra (frase de contraseña o aprobación de Keychain), pero es un trade-off aceptable para la seguridad.
*   **OPEN LEGAL POINT:** La automatización del login bancario (incluso para fines de reconciliación interna autorizada por la empresa) puede estar sujeta a los términos de servicio del portal de Bancolombia. Este punto requiere revisión legal y aprobación antes de la puesta en producción.
