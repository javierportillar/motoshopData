import re, os, sys, collections

EXE = r"C:\Program Files (x86)\Julio Chaves\SgHermes\SgHermes.exe"
OUT = r"C:\Users\MotoShop\Documents\javidevmoto\motoshopData\docs\hermes\evidence"
TMP = r"C:\Users\MotoShop\AppData\Local\Temp\opencode\hermes"

os.makedirs(OUT, exist_ok=True)

data = open(EXE, "rb").read()
print("exe bytes:", len(data))

# .NET user strings live in the #US heap as UTF-16LE
txt16 = data.decode("utf-16-le", errors="ignore")
# ASCII literals (SQL/ODBC/config) 
txt8 = data.decode("latin-1", errors="ignore")

RUN = re.compile(r"[\x20-\x7E]{4,}")
s16 = RUN.findall(txt16)
s8 = RUN.findall(txt8)

# dedupe preserving order
def uniq(seq):
    seen = set(); out = []
    for x in seq:
        k = x.strip()
        if len(k) < 4 or k in seen:
            continue
        seen.add(k); out.append(k)
    return out

u16 = uniq(s16)
u8 = uniq(s8)

CATS = collections.OrderedDict([
    ("SQL (sentencias embebidas)", r"\b(SELECT|INSERT|UPDATE|DELETE|REPLACE)\b.*\b(FROM|INTO|SET|VALUES)\b"),
    ("Consecutivos / numeracion", r"(?i)consecutiv|numfven|numcom|prefven|precom|resoluc"),
    ("Pagos / caja", r"(?i)^(efectivo|tarjeta|cheque|transferencia|consignaci|cuentas? por|cambio|vuelto|recib|comprobante de (ingreso|egreso)|arqueo|base inicial)"),
    ("Impuestos / retenciones", r"(?i)iva|impuesto|impoconsumo|retenci|retefuente|reteica|reteiva"),
    ("Inventario / stock", r"(?i)inventario|existencia|kardex|bodega|stock|entrada|salida|ajuste"),
    ("Impresion / perifericos", r"(?i)imprim|printer|escpos|esc/pos|print|tiquete|tirilla|paper|ancho|58|80 ?mm|cajon|gaveta|drawer|barcode|barras|qr"),
    ("Seguridad / login", r"(?i)usuario|clave|password|contras|login|ingresar|permiso|nivel|acceso|sesion"),
    ("Conexion / configuracion", r"(?i)odbc|driver|server=|uid=|pwd=|database|conexion|servidor\.txt|mysqldump|backup|copia de seguridad"),
    ("Actualizacion / red", r"(?i)actualiz|update|http|https|ftp|sftp|ssh|descarg|version|licencia"),
    ("Informes", r"(?i)^informe|reporte"),
    ("Contabilidad PUC", r"\b(11|13|22|41|51|52)\d{6,10}\b"),
])

report = []
report.append("# Evidencia — literales del binario\n")
report.append(f"Fuente: `SgHermes.exe` ({len(data):,} bytes) — lectura estática, sin ejecución.\n")
report.append(f"Extraccion: {len(u16):,} literales UTF-16LE unicos y {len(u8):,} cadenas ASCII/latin1 >= 4 chars.\n")
report.append("> El heap `#US` de .NET almacena los literales como UTF-16LE; un barrido ASCII reproduce solo una fraccion.\n")

report.append("\n## Conteo de categorias\n")
counts = []
for name, pat in CATS.items():
    rx = re.compile(pat, re.IGNORECASE | re.MULTILINE)
    hits = [x for x in u16 if rx.search(x)]
    counts.append((name, len(hits)))
    resp = []
    for h in hits[:40]:
        h = h.strip()
        if 4 <= len(h) <= 300:
            resp.append(h)
    seen = set(); clean = []
    for h in resp:
        if h not in seen:
            seen.add(h); clean.append(h)
    report.append(f"\n### {name}  ({len(hits)} coincidencias)\n")
    if clean:
        report.append("```")
        report.extend(clean[:25])
        report.append("```")
    else:
        report.append("_(sin coincidencias)_")

# SQL exacto (los mas valiosos para reconstruir el acceso a datos)
rx_sql = re.compile(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b[\x20-\x7E]{5,400}", re.IGNORECASE)
sql16 = sorted({m.group(0).strip() for m in rx_sql.finditer(txt16)})
sql8 = sorted({m.group(0).strip() for m in rx_sql.finditer(txt8)})
allsql = []
seen = set()
for s in sql16 + sql8:
    s = re.sub(r"\s+", " ", s).strip()
    if s.lower() in seen:
        continue
    seen.add(s.lower()); allsql.append(s)

report.append(f"\n## Sentencias SQL embebidas ({len(allsql)})\n")
report.append("> Extraidas de ambos barridos. Confirman que el acceso a datos es ODBC con SQL concatenado.\n")
report.append("```sql")
report.extend(allsql[:150])
report.append("```")

# Tablas referenciadas por los SQL
tabs = collections.Counter()
rx_from = re.compile(r"(?:FROM|INTO|UPDATE|JOIN)\s+`?([A-Za-z0-9_]+)`?", re.IGNORECASE)
for s in allsql:
    for t in rx_from.findall(s):
        tabs[t.lower()] += 1
report.append(f"\n## Tablas mencionadas en los SQL ({len(tabs)})\n")
report.append("| Tabla | Menciones |")
report.append("|---|---|")
for t, c in tabs.most_common(80):
    report.append(f"| `{t}` | {c} |")

# Marcadores de parametros: ? vs concatenacion
qmarks = sum(1 for s in allsql if "?" in s)
report.append(f"\n## Estilo de acceso a datos\n")
report.append(f"- Sentencias con marcador de parametro `?`: **{qmarks}** de {len(allsql)}")
report.append("- El resto no muestra parametros -> SQL armado por concatenacion [I]")
report.append(f"- Cadenas con `DRIVER={{` (ODBC DSN inline): **{sum(1 for x in u8 if 'DRIVER={' in x)}**")
report.append(f"- Cadenas con `OdbcConnection`/`MySqlConnection`: **{sum(1 for x in u16 if re.search(r'Odbc|MySql', x, re.I))}**")

open(os.path.join(OUT, "binary_strings_digest.md"), "w", encoding="utf-8").write("\n".join(report) + "\n")
print("strings digest:", len(report), "lineas")
print("sql encontradas:", len(allsql))
print("tablas:", len(tabs))
