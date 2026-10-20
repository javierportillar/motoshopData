import pytest
from motoshop_api.llm.qa_chat import compact_assistant_history_content


def test_short_content_is_untouched():
    text = "Hola! Estos son los productos más vendidos de octubre: MAIZ001 y DAF001."
    assert compact_assistant_history_content(text, is_latest=True) == text
    assert compact_assistant_history_content(text, is_latest=False) == text


def test_bulleted_sku_list_compacting_latest():
    # Construct a message with 40 SKU lines, including dotted NITs and S.A.S. suffixes
    lines = [
        "Candidatos a revisar por stock agotado · corte inventario 2026-10-20.",
    ]
    lines.append(
        "- SKU YAM001 · FILTRO ACEITE YAMAHA: stock 0 UNIDADES; ventas 10 UNIDADES; proveedor: IMPORTADORA S.A.S. (NIT: 900.123.456-1)."
    )
    for i in range(2, 41):
        lines.append(
            f"{i}. SKU PROD{i:03d} · PRODUCTO DE PRUEBA {i}: stock 0 GRAMO; ventas {i*100} GRAMO en 180 días; "
            f"referencia {i*25} GRAMO para 45 días; proveedor: DISTRIBUIDOR {i%5} S.A. (NIT: 900.{i%5:03d}.456-1)."
        )
    lines.append("Nota: La cantidad es una referencia.")
    full_content = "\n".join(lines)
    assert len(full_content) > 3000

    compacted = compact_assistant_history_content(full_content, is_latest=True)
    # Must be noticeably shorter
    assert len(compacted) < len(full_content)
    # Must retain every SKU, corporate suffix (S.A.S., S.A.), and full dotted NIT
    assert "- SKU YAM001 · FILTRO ACEITE YAMAHA (proveedor: IMPORTADORA S.A.S. (NIT: 900.123.456-1))" in compacted
    assert "- SKU PROD002 · PRODUCTO DE PRUEBA 2 (proveedor: DISTRIBUIDOR 2 S.A. (NIT: 900.002.456-1))" in compacted
    assert "- SKU PROD040 · PRODUCTO DE PRUEBA 40" in compacted
    # Redundant metric boilerplate must be gone
    assert "stock 0 GRAMO; ventas" not in compacted
    assert "referencia 25 GRAMO" not in compacted
    assert "Nota: La cantidad es una referencia." in compacted


def test_generic_text_no_duplicate_expansion():
    # Text between 1501 and 3300 chars should NOT expand with duplicated content
    narrative = "Analisis del negocio:\n" + ("Palabras de contexto financiero.\n" * 50)
    assert 1500 < len(narrative) <= 3300

    compacted = compact_assistant_history_content(narrative, is_latest=True)
    # Must not exceed original length!
    assert len(compacted) <= len(narrative)
    assert "... [contenido intermedio compactado] ..." not in compacted


def test_bulleted_sku_list_compacting_older_turn():
    lines = ["Lista de compras anteriores:"]
    for i in range(1, 30):
        lines.append(
            f"- SKU PROD{i:03d} · PRODUCTO {i}: stock 0 UNIDADES; ventas {i*10} UNIDADES; proveedor: PROV {i} (NIT: 123)."
        )
    full_content = "\n".join(lines)
    compacted = compact_assistant_history_content(full_content, is_latest=False)

    # Older turn should keep first 10 items and a count summary
    assert "- SKU PROD001 · PRODUCTO 1" in compacted
    assert "- SKU PROD010 · PRODUCTO 10" in compacted
    assert "... y 19 productos más listados en este turno ..." in compacted
    assert "- SKU PROD025" not in compacted


def test_generic_long_text_compacting():
    # Long text with no bulleted SKUs
    long_text = "Analisis del negocio:\n" + ("Palabras de contexto financiero y balance general.\n" * 80)
    assert len(long_text) > 3000

    compacted_latest = compact_assistant_history_content(long_text, is_latest=True)
    assert len(compacted_latest) < len(long_text)
    assert "contenido intermedio compactado" in compacted_latest

    compacted_old = compact_assistant_history_content(long_text, is_latest=False)
    assert len(compacted_old) < len(compacted_latest)
    assert "detalle histórico compactado" in compacted_old
