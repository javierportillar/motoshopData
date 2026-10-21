# SgHermes v10.0.0.3 — delta sobre el análisis de 9.1.0

> Fecha: 2026-10-21
> **Este documento NO reemplaza** `hermes_reverse_engineering_blueprint.md`, `code_analysis.md` ni `modules.md`.
> El corpus existente documenta **SgHermes 9.1.0** (MotoShop, 37.760.512 bytes, SHA-256 `6fb0c1f0…`).
> Acá se documenta **SgHermes 10.0.0.3**, el binario que corre en MasVital, y lo que cambia respecto de esa base.

## 1. Por qué existe este delta

La instalación de MasVital **no es la versión documentada**. Es un build posterior, con otro hash y otro tamaño:

| | Documentado (MotoShop) | En producción (MasVital) |
|---|---|---|
| Versión | 9.1.0 | **10.0.0.3** |
| SHA-256 | `6fb0c1f08bb7232f59156a46cd140a3b064dc65370c2c50468614bcb470e6ab8` | `39d4f2d4083ba0432fa224836500f7cfc32a0f4bb473473122b59d4d25073113` |
| Tamaño | 37.760.512 bytes | **39.016.448 bytes** |
| Ruta | `C:\Program Files (x86)\Julio Chaves\SgHermes\` | idéntica |
| Estado | — | **en ejecución** (PID 2792) |

Diferencia: **+1,26 MB** de binario. Toda regla de negocio citada en `code_analysis.md` debe revalidarse contra este build antes de tomarla como contrato.

## 2. Histórico de builds encontrado en la máquina

| Archivo | Versión | SHA-256 (prefijo) | Fecha |
|---|---|---|---|
| `SgHermes.exe` (activo) | **10.0.0.3** | `39D4F2D4083BA043` | 2026-05-29 |
| `ant10_1.exe` | 10.0.0.2 | `3F29113A0CD04742` | 2026-05-21 |
| `ant2.exe` | 9.5.1.6 | `9C061D1320250579` | 2025-09-25 |
| `ante1.exe` | 9.2.1.1 | `35286F8A510C5AEB` | 2024-07-30 |

Hay **tres generaciones** de binario conviviendo en la carpeta de instalación. `ante1.exe` (9.2.1.1) es el más cercano al 9.1.0 documentado.

## 3. Ficha técnica (v10.0.0.3)

| Campo | Valor |
|---|---|
| Formato | PE32, x86, IL-only, `32-bit-required`, `32-bit-preferred` |
| Runtime | .NET Framework 4.5 (`SgHermes.exe.config`) |
| Metadatos CLI | 6.581.228 bytes |
| Recursos | 18.205.184 bytes |
| Secciones PE | 3 |
| Entry point | metadata-token `0x0600000b` |
| Strong name | ausente |
| ReadyToRun | no |

## 4. REA: misma limitación, ahora cuantificada

Se reprodujo el comportamiento ya descrito en el blueprint:

```
provider: rea-dotnet-static
resource-limit / metadata.representation:
"Managed metadata exceeds the 67108864 byte representation budget"
```

| Operación | Resultado |
|---|---|
| `rea inspect-managed-artifact` | OK — identifica PE/x86/IL y contabiliza metadatos y recursos |
| `rea inspect-managed-members` | **Vacío**: `types: []`, `methods: []`, `coverage: unavailable` |
| `rea decompile` | No aplica — es para binario nativo, no IL |
| `rea doctor` | `config_drift` (registrations `codex`/`opencode`/`vscode`), skill `missing`, installations `multiple` |

**Conclusión:** REA sirve para identidad y clasificación; para ingeniería inversa de este binario hay que decompilar. `rea setup` **no** es necesario para las operaciones de inspección (funcionan sin él).

## 5. Receta de decompilación (esta máquina no tenía .NET)

El blueprint marcaba `[X]` la lectura de IL porque no había SDK. Acá sí se resolvió:

```powershell
winget install --id Microsoft.DotNet.SDK.8 -e --accept-source-agreements --accept-package-agreements --silent
$dotnet = "C:\Program Files\dotnet\dotnet.exe"
& $dotnet tool install -g ilspycmd --version 8.2.0.7535
$env:DOTNET_ROOT = "C:\Program Files\dotnet"
$env:DOTNET_ROLL_FORWARD = "LatestMajor"
& "$env:USERPROFILE\.dotnet\tools\ilspycmd.exe" -p -o <salida> "C:\Program Files (x86)\Julio Chaves\SgHermes\SgHermes.exe"
```

Tres trampas concretas:

1. `ilspycmd` actual exige .NET 9 → hay que fijar `--version 8.2.0.7535`.
2. Esa versión apunta a .NET 6 → se ejecuta con `DOTNET_ROLL_FORWARD=LatestMajor`.
3. El apphost no encuentra el runtime si `dotnet` no está en el `PATH` del proceso → exportar `DOTNET_ROOT`.

Resultado:

| | 9.1.0 (documentado) | 10.0.0.3 (este build) |
|---|---|---|
| Archivos `.cs` | 797 | **804** |
| Volumen | ~1,3 M líneas | **45,59 MB** |

El árbol decompilado no se versiona (45 MB); es reproducible con la receta.

## 6. Qué se confirmó igual en v10

Verificado leyendo el código decompilado de **este** binario:

| Hallazgo del blueprint | Estado en v10 |
|---|---|
| Cadena ODBC armada por concatenación (`PROVIDER=MSDASQL;DRIVER={…}`) | **Confirmado** — `Hermes\Bconexion.cs:47` |
| `servidor.txt` de 6 campos separados por `;` | **Confirmado** — parser manual en `Hermes\FrmInicio.cs:900-949` |
| Drivers ofrecidos: MySQL ODBC 5.1 / 5.3 Unicode / 8.0 Unicode | **Confirmado** — `FrmInicio.cs:1005-1007` |
| Stock como contador en `productos.exiprod` | **Confirmado** — `Vardos.cs:491` hace `exiprod = exiprod + '…'` |
| SQL sin parámetros | **Confirmado** — `Inicio.SQL` + `Inicio.CnBd.Execute` |
| Integración DIAN con Dataico y SofPropLat | **Confirmado** — namespaces `Hermes.WADataico.*` y `Hermes.WASofPropLat.*` |
| Persistencia FE en `respdocfele` / `comevenrecep` | **Confirmado** |

## 7. Qué cambia o se agrega

1. **Base viva distinta.** El esquema documentado (`evidence/schema_2024.sql`, 175 tablas) corresponde a MotoShop. En MasVital hay **179 tablas**, todas MyISAM, y `resdian` **vacía**. Ver `evidence/masvital_live_schema_2026-10.md`.
2. **Facturación electrónica presente pero apagada.** Los 57 contadores tienen `esfelec='N'` y `resdian='NO'`; las 3.547 facturas emitidas tienen `estfele='N'`. La capacidad está comprada, la configuración no.
3. **Operación a granel real.** 17 de 7.818 líneas de venta tienen cantidad fraccionaria (3 decimales), con precio por gramo. `productos.exiprod` mezcla gramos y unidades según `codmed`. Esto no aparece cuantificado en el corpus de 9.1.0.
4. **Un solo contador activo:** `S15 FACTURA DE VENTA POS`, prefijo `FVP`, consecutivo **3.548**.
5. **La configuración efectiva vive en VirtualStore (UAC), no en Program Files.** El `servidor.txt` de `C:\Program Files (x86)\Julio Chaves\SgHermes\` (65 bytes, 2024-07-31) apunta a `bdempresa`, base que **no existe**. La app corre sin elevación, así que Windows redirige sus lecturas y escrituras a `%LOCALAPPDATA%\VirtualStore\Program Files (x86)\Julio Chaves\SgHermes\servidor.txt` (64 bytes, 2026-10-21 09:49), que sí dice **`masvital`**. Verificado contra la conexión viva: PID 2792 → `SHOW FULL PROCESSLIST` → `db = masvital`.

## 8. Impacto en el plan de migración

- El **modelo de datos y las reglas** del blueprint siguen siendo válidos como marco, pero los números concretos (tablas, contadores, volúmenes) deben tomarse de este delta para MasVital.
- El **mapeo de unidades** (gramo vs unidad) es un requisito nuevo y bloqueante para el ETL de inventario.
- La **FE DIAN** no es desarrollo nuevo: es activación + resolución + credenciales.
- **Cuidado al tocar la configuración:** editar `servidor.txt` en Program Files **no tiene efecto**. El archivo que manda es el de VirtualStore; hay que editar ese o relanzar la app elevada.
- El **delta de código 9.1.0 → 10.0.0.3** (804 vs 797 archivos) queda sin diff semántico: requeriría decompilar también el 9.1.0 en una máquina que lo tenga.

## 9. Evidencia asociada

- `docs/hermes/evidence/masvital_live_schema_2026-10.md` — introspección en vivo de `masvital`.
- `docs/hermes/evidence/binary_strings_digest_v10.md` — literales del binario 10.0.0.3.
- Corpus base: `README.md`, `hermes_reverse_engineering_blueprint.md`, `code_analysis.md`, `modules.md`, `form_catalog.csv`.
