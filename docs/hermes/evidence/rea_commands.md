# Evidencia — REA (Reverse Engineering Agent) sobre SgHermes.exe

## Instalación

```powershell
npx rea-agents@6.7.0 setup      # MCP + skill, registrado en OpenCode / Codex / VS Code
rea doctor
rea inspect-managed-artifact "C:\Program Files (x86)\Julio Chaves\SgHermes\SgHermes.exe"
rea inspect-managed-members  "C:\Program Files (x86)\Julio Chaves\SgHermes\SgHermes.exe"
```

- Paquete: `rea-agents@6.7.0` (repo `morluto/rea`), bin `rea`.
- Estado tras setup: `state: aligned`, skill v42, **207 tools**.
- Backups de configuración: `*.rea.backup` en cada archivo modificado.

## Resultados

| Comando | Resultado |
|---|---|
| `inspect-managed-artifact` | ✅ Identidad confirmada: PE **managed**, x86, SHA-256 `6fb0c1f08bb7232f59156a46cd140a3b064dc65370c2c50468614bcb470e6ab8` |
| `inspect-managed-members` | ❌ **Falló** |

### Error de `inspect-managed-members`

```json
{
  "coverage": {
    "issues": [
      {
        "code": "resource-limit",
        "detail": "Managed metadata exceeds the 67108864 byte representation budget"
      }
    ]
  },
  "message": "The CLI metadata could not be admitted; managed member inspection is unavailable."
}
```

### Diagnóstico

- El ejecutable tiene **37.760.512 bytes** de metadata gestionada; el límite del representador es **64 MB (67.108.864 bytes)**.
- `rea` no expone flag para elevar ese presupuesto en la versión instalada.
- Providers nativos (`ghidra`, `ida`, `jadx`, `kuna`) **no configurados** y, en cualquier caso, no aplican a IL managed.

### Alternativas evaluadas

| Alternativa | Estado |
|---|---|
| `dotnet` SDK + `ilspycmd` | ❌ No instalado (no hay `dotnet`, ni `ilspycmd`, `ildasm`, `ikdasm`, `monodis`, `dnSpy`) |
| Barrido de strings ASCII | ❌ Casi vacío: los literales .NET viven en el heap `#US` como **UTF-16LE** |
| **Barrido UTF-16LE con regex y agrupación** | ✅ **Aplicado** → 12.538 literales únicos, 147 sentencias SQL, 79 tablas referenciadas |

### Recomendación para la siguiente pasada

```powershell
winget install Microsoft.DotNet.SDK.8
dotnet tool install -g ilspycmd
ilspycmd -p -o .\decompiled "C:\Program Files (x86)\Julio Chaves\SgHermes\SgHermes.exe"
```

Con IL/descompilado se cierran los puntos marcados **[X]** en el blueprint: validaciones de UI, orden exacto de escritura, manejo de errores, impresión y control de cajón.

## Conclusión

REA aportó la **identidad técnica** (managed, x86, .NET 4.5, dependencias). La **lógica de negocio** se reconstruyó por otra vía: los literales SQL del binario, que resultaron ser más reveladores que el árbol de tipos (fórmula de `totdet`, tabla `contadores`, `listapre`, permisos).
