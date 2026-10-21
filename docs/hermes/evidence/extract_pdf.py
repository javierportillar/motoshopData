"""Extrae el manual de usuario de SgHermes a texto plano.

Uso:  & "C:\\Python314\\python.exe" docs\\hermes\\evidence\\extract_pdf.py
Salida: evidence/manual_full_text.txt
"""
import os
import re

from pypdf import PdfReader

MANUAL = r"C:\Program Files (x86)\Julio Chaves\SgHermes\Manual de Usuario.pdf"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(OUT_DIR, "manual_full_text.txt")

reader = PdfReader(MANUAL)
print("paginas:", len(reader.pages))

chunks = []
for i, page in enumerate(reader.pages):
    try:
        body = page.extract_text() or ""
    except Exception as exc:  # noqa: BLE001 - queremos seguir con las demas paginas
        body = f"(error: {exc})"
    chunks.append(f"\n===== PAGINA {i + 1} =====\n{body}")

full = "".join(chunks)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(full)

print("chars:", len(full))
print("salida:", OUT)

titles = [
    line.strip()
    for line in full.splitlines()
    if line.strip() and len(line.strip()) < 70 and re.match(r"^(CAP|Cap|[0-9]+[.)])", line.strip())
]
print("--- posibles titulos (primeros 40) ---")
print("\n".join(titles[:40]))
