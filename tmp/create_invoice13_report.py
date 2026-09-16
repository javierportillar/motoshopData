from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path("/Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData")
OUTPUT_DIR = ROOT / "outputs/motoshop_factura_13_2024-07-27_20260910"
DATA_DIR = OUTPUT_DIR / "analysis_data"
CHART_DIR = DATA_DIR / "charts_concise"
OUTPUT_PDF = OUTPUT_DIR / "informe_factura_13_motoshop.pdf"
CHART_DIR.mkdir(parents=True, exist_ok=True)

NAVY = "#0B1F33"
BLUE = "#2F6FED"
TEAL = "#0F9D8A"
AMBER = "#E7A23B"
RED = "#D95C5C"
PALE_RED = "#FDECEC"
PALE_BLUE = "#EAF1FF"
PALE_TEAL = "#E7F6F3"
PALE_AMBER = "#FFF4DD"
TEXT = "#172B4D"
MUTED = "#5B6B7A"
BORDER = "#D9E2EC"

pdfmetrics.registerFont(TTFont("ArialEmbedded", "/System/Library/Fonts/Supplemental/Arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialEmbedded-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))

summary = json.loads((DATA_DIR / "summary.json").read_text(encoding="utf-8"))
sku = pd.read_csv(DATA_DIR / "sku_audit.csv")
bands = pd.read_csv(DATA_DIR / "sell_through_bands.csv")
monthly = pd.read_csv(DATA_DIR / "monthly_sales.csv")
negative = pd.read_csv(DATA_DIR / "negative_stock.csv")


def money(value: float) -> str:
    return f"${value:,.0f}".replace(",", ".")


def money_m(value: float) -> str:
    return f"${value / 1_000_000:.2f} M".replace(".", ",")


def integer(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def pct(value: float) -> str:
    return f"{value * 100:.1f}%".replace(".", ",")


def create_charts() -> None:
    plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.titleweight": "bold"})

    purchased = float(summary["invoice"]["units"])
    absorbed = float(summary["performance"]["units_sold_apparent_cap"])
    pending = purchased - absorbed
    fig, ax = plt.subplots(figsize=(10.4, 1.8))
    ax.barh([0], [absorbed], color=TEAL, height=0.46)
    ax.barh([0], [pending], left=[absorbed], color=AMBER, height=0.46)
    ax.text(absorbed / 2, 0, f"Absorbidas\n{integer(absorbed)} · {absorbed/purchased:.1%}", ha="center", va="center", color="white", weight="bold", fontsize=10)
    ax.text(absorbed + pending / 2, 0, f"No absorbidas\n{integer(pending)} · {pending/purchased:.1%}", ha="center", va="center", color=NAVY, weight="bold", fontsize=10)
    ax.set_xlim(0, purchased)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("De cada 100 unidades compradas, 48 todavía no muestran salida atribuible", loc="left", color=NAVY, pad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "salida_unidades.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    band_colors = [RED, AMBER, "#E8C467", "#7FB7BE", TEAL]
    fig, ax = plt.subplots(figsize=(5.0, 3.25))
    ax.barh(bands["banda_sell_through"], bands["skus"], color=band_colors)
    for y, value in enumerate(bands["skus"]):
        ax.text(value + 4, y, integer(value), va="center", color=TEXT, fontsize=9, weight="bold")
    ax.set_xlim(0, max(bands["skus"]) * 1.18)
    ax.invert_yaxis()
    ax.set_title("SKU por nivel de absorción", loc="left", color=NAVY, pad=8)
    ax.set_xlabel("Cantidad de SKU", color=MUTED)
    ax.grid(axis="x", color="#E9EEF3", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BORDER)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "bandas_sku.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    monthly["mes"] = pd.to_datetime(monthly["mes"])
    monthly["trimestre"] = monthly["mes"].dt.to_period("Q")
    quarter = monthly.groupby("trimestre", as_index=False)["ventas"].sum()
    labels = [f"T{p.quarter} {str(p.year)[2:]}" for p in quarter["trimestre"]]
    values = quarter["ventas"] / 1_000_000
    colors_list = [BLUE] * len(quarter)
    colors_list[-1] = "#D8DEE8"
    fig, ax = plt.subplots(figsize=(5.0, 3.25))
    bars = ax.bar(labels, values, color=colors_list, width=0.68)
    for i, bar in enumerate(bars):
        if i in (0, 1, len(bars) - 3, len(bars) - 2, len(bars) - 1):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.14, f"${bar.get_height():.1f}M", ha="center", va="bottom", fontsize=7.5, color=TEXT)
    ax.set_title("Ventas trimestrales de los mismos SKU", loc="left", color=NAVY, pad=8)
    ax.set_ylabel("COP millones", color=MUTED)
    ax.tick_params(axis="x", labelrotation=38, labelsize=8)
    ax.grid(axis="y", color="#E9EEF3", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BORDER)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "ventas_trimestrales.png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


create_charts()

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="ArialEmbedded-Bold", fontSize=21, leading=24, textColor=colors.HexColor(NAVY), alignment=TA_LEFT, spaceAfter=6))
styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["Normal"], fontName="ArialEmbedded", fontSize=9.2, leading=12, textColor=colors.HexColor(MUTED), spaceAfter=11))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="ArialEmbedded-Bold", fontSize=15, leading=18, textColor=colors.HexColor(NAVY), spaceBefore=2, spaceAfter=7))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="ArialEmbedded-Bold", fontSize=11, leading=14, textColor=colors.HexColor(NAVY), spaceBefore=7, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyX", parent=styles["BodyText"], fontName="ArialEmbedded", fontSize=9.1, leading=12.5, textColor=colors.HexColor(TEXT), spaceAfter=5))
styles.add(ParagraphStyle(name="SmallX", parent=styles["BodyText"], fontName="ArialEmbedded", fontSize=7.5, leading=9.5, textColor=colors.HexColor(MUTED)))
styles.add(ParagraphStyle(name="Verdict", parent=styles["BodyText"], fontName="ArialEmbedded-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#8A1C1C"), alignment=TA_CENTER))
styles.add(ParagraphStyle(name="KpiLabel", parent=styles["BodyText"], fontName="ArialEmbedded-Bold", fontSize=7, leading=8.5, textColor=colors.white, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="KpiValue", parent=styles["BodyText"], fontName="ArialEmbedded-Bold", fontSize=13.5, leading=16, textColor=colors.HexColor(NAVY), alignment=TA_CENTER))
styles.add(ParagraphStyle(name="TableHead", parent=styles["BodyText"], fontName="ArialEmbedded-Bold", fontSize=7.2, leading=8.5, textColor=colors.white, alignment=TA_LEFT))
styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontName="ArialEmbedded", fontSize=7.1, leading=8.8, textColor=colors.HexColor(TEXT)))
styles.add(ParagraphStyle(name="TableCellSmall", parent=styles["BodyText"], fontName="ArialEmbedded", fontSize=6.5, leading=7.8, textColor=colors.HexColor(TEXT)))


def p(text: str, style: str = "BodyX") -> Paragraph:
    return Paragraph(text, styles[style])


def kpi_cards(cards: list[tuple[str, str, str]]) -> Table:
    labels = [p(label, "KpiLabel") for label, _, _ in cards]
    values = [p(value, "KpiValue") for _, value, _ in cards]
    table = Table([labels, values], colWidths=[(17.8 * cm) / len(cards)] * len(cards), rowHeights=[0.58 * cm, 0.92 * cm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor(BORDER)),
    ]
    for idx, (_, _, fill) in enumerate(cards):
        style.append(("BACKGROUND", (idx, 1), (idx, 1), colors.HexColor(fill)))
    table.setStyle(TableStyle(style))
    return table


def styled_table(headers, rows, widths, numeric_cols=(), small=False) -> Table:
    cell_style = "TableCellSmall" if small else "TableCell"
    data = [[p(h, "TableHead") for h in headers]] + [[p(str(cell), cell_style) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    directives = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(NAVY)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FC")]),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor(BORDER)),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for col in numeric_cols:
        directives.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(directives))
    return table


def report_image(path: Path, width_cm: float) -> Image:
    img = Image(str(path))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * ratio * cm
    return img


def on_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(colors.HexColor(NAVY))
    canvas.rect(0, height - 0.42 * cm, width, 0.42 * cm, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor(BORDER))
    canvas.line(1.4 * cm, 1.0 * cm, width - 1.4 * cm, 1.0 * cm)
    canvas.setFont("ArialEmbedded", 7.3)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(1.4 * cm, 0.64 * cm, "MotoShop · Factura 13/S18 · Informe ejecutivo")
    canvas.drawRightString(width - 1.4 * cm, 0.64 * cm, f"Página {doc.page}")
    canvas.restoreState()


invoice = summary["invoice"]
perf = summary["performance"]
inv = summary["inventory"]
source = summary["source"]
absorbed = perf["units_sold_apparent_cap"]
not_absorbed = perf["unabsorbed_units"]
low_count = perf["skus_below_50pct_absorption"]
low_cost = perf["cost_in_skus_below_50pct_absorption"]
full_count = perf["skus_100pct_apparent_absorption"]
zero_count = perf["skus_never_sold_since"]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
doc = BaseDocTemplate(
    str(OUTPUT_PDF), pagesize=A4,
    leftMargin=1.4 * cm, rightMargin=1.4 * cm, topMargin=1.15 * cm, bottomMargin=1.3 * cm,
    title="Informe ejecutivo Factura 13/S18 MotoShop", author="MotoShop",
)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

story = [
    Spacer(1, 0.12 * cm),
    p("¿Fue una buena compra?", "ReportTitle"),
    p(
        f"Factura 13 · S18 · {invoice['supplier']} · 27 de julio de 2024 · "
        f"Datos actualizados al {source['inventory_snapshot_date']}",
        "ReportSubtitle",
    ),
]
verdict = Table([[p("SÍ HUBO SOBRECOMPRA", "Verdict")]], colWidths=[17.8 * cm], rowHeights=[1.15 * cm])
verdict.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PALE_RED)), ("BOX", (0, 0), (-1, -1), 1.1, colors.HexColor(RED)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
story += [verdict, Spacer(1, 0.3 * cm)]
story += [
    kpi_cards([
        ("VALOR COMPRA", money(invoice["header_total"]), PALE_BLUE),
        ("ABSORCIÓN UNIDADES", pct(perf["unit_weighted_sell_through"]), PALE_AMBER),
        ("SIN SALIDA EST.", integer(not_absorbed), PALE_RED),
        ("COSTO NO ABSORBIDO", money_m(perf["unabsorbed_cost"]), PALE_RED),
        ("SKU SIN VENTAS", integer(zero_count), PALE_RED),
    ]),
    Spacer(1, 0.3 * cm),
    p("Respuesta directa", "H1x"),
    p(
        f"<b>No fue una buena compra como conjunto.</b> Después de más de dos años, solo "
        f"<b>{pct(perf['unit_weighted_sell_through'])}</b> de las {integer(invoice['units'])} unidades muestra salida atribuible. "
        f"Quedan <b>{integer(not_absorbed)} unidades ({pct(not_absorbed/invoice['units'])})</b> sin absorber, por "
        f"<b>{money_m(perf['unabsorbed_cost'])}</b> de costo original.",
    ),
    p("Por qué", "H2x"),
]
reason_rows = [
    ["Sin ventas", f"{integer(zero_count)} SKU nunca se vendieron desde la compra; representan {money_m(bands.loc[bands.banda_sell_through == '0%', 'costo_factura'].iloc[0])}."],
    ["Rotación insuficiente", f"{integer(low_count)} SKU quedaron por debajo de 50% de absorción; concentran {money_m(low_cost)} del costo."],
    ["Inventario expuesto", f"El remanente mínimo potencial es {integer(inv['minimum_potential_invoice_residual_units'])} unidades por {money_m(inv['minimum_potential_invoice_residual_cost'])}."],
    ["Parte acertada", f"{integer(full_count)} SKU sí absorbieron el 100% de lo comprado; el error fue el tamaño y la amplitud de la canasta, no todos los productos."],
]
story += [styled_table(["Señal", "Dato verificable"], reason_rows, [4.0 * cm, 13.8 * cm]), Spacer(1, 0.24 * cm)]
story += [
    p("Decisión recomendada", "H2x"),
    p(f"<b>Detener recompras</b> de los {integer(zero_count)} SKU sin ventas y revisar los {integer(low_count)} SKU por debajo de 50% antes de emitir nuevas órdenes."),
    p("<b>Recuperar caja</b> con devolución, traslado, paquetes o descuento selectivo. La prioridad debe ser el valor inmovilizado, no solo la cantidad de referencias."),
    p(f"<b>Recomprar únicamente</b> los SKU ya absorbidos y con demanda reciente; {integer(perf['skus_replenished_after_invoice'])} SKU tuvieron compras posteriores y deben revisarse contra ventas de 90 días."),
]

story += [PageBreak(), p("Qué pasó con los productos", "H1x")]
story += [p("La salida fue parcial y quedó concentrada: pocos grupos explican la mayor parte de la venta, mientras una cola larga sigue sin rotar.")]
story += [report_image(CHART_DIR / "salida_unidades.png", 17.4), Spacer(1, 0.1 * cm)]
chart_pair = Table(
    [[report_image(CHART_DIR / "bandas_sku.png", 8.55), report_image(CHART_DIR / "ventas_trimestrales.png", 8.55)]],
    colWidths=[8.9 * cm, 8.9 * cm],
)
chart_pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
story += [chart_pair, Spacer(1, 0.12 * cm)]
q = monthly.assign(mes=pd.to_datetime(monthly["mes"]))
q["trimestre"] = q["mes"].dt.to_period("Q")
q = q.groupby("trimestre")["ventas"].sum()
q4_2024 = float(q.loc[pd.Period("2024Q4")])
q2_2026 = float(q.loc[pd.Period("2026Q2")])
decline = 1 - q2_2026 / q4_2024
movement_rows = [
    ["Salida de unidades", f"{integer(absorbed)} absorbidas frente a {integer(not_absorbed)} no absorbidas."],
    ["Distribución", f"{integer(zero_count)} SKU quedaron en 0%; {integer(full_count)} llegaron a 100%. El resultado está polarizado."],
    ["Demanda", f"Las ventas trimestrales de estos SKU bajaron de {money_m(q4_2024)} en T4 2024 a {money_m(q2_2026)} en T2 2026 ({pct(-decline)})."],
]
story += [styled_table(["Lectura", "Qué significa"], movement_rows, [4.0 * cm, 13.8 * cm])]
story += [Spacer(1, 0.16 * cm), p("La serie trimestral incluye ventas de reposiciones posteriores. Sirve para medir la demanda de los mismos SKU, no para calcular el retorno exacto de esta factura. T3 2026 es parcial al 10 de septiembre.", "SmallX")]

story += [PageBreak(), p("Qué quedó y qué hacer", "H1x")]
story += [p(f"Hay {integer(inv['skus_with_positive_stock'])} SKU de esta canasta con stock positivo. Los siguientes diez nunca registraron una venta posterior y concentran el mayor costo original.")]
never = sku[(sku["unidades_vendidas_desde"] <= 0) & (sku["stock_actual"] > 0)].nlargest(10, "costo_factura")
never_rows = []
for _, row in never.iterrows():
    never_rows.append([
        row["cod_producto"], str(row["producto"])[:48], integer(row["cantidad_comprada"]), integer(row["stock_actual"]), money(row["costo_factura"]), money(row["remanente_minimo_costo"]),
    ])
story += [styled_table(["SKU", "Producto", "Compra", "Stock", "Costo compra", "Remanente mín."], never_rows, [2.4 * cm, 6.7 * cm, 1.5 * cm, 1.4 * cm, 2.8 * cm, 3.0 * cm], numeric_cols=(2, 3, 4, 5), small=True)]
story += [Spacer(1, 0.2 * cm), p("Plan puntual", "H2x")]
actions = [
    ["1", "Bloquear recompra", f"Aplicar a {integer(zero_count)} SKU sin ventas y revisar manualmente cualquier excepción."],
    ["2", "Validar existencia", f"Contar los diez SKU anteriores y corregir los {integer(inv['skus_negative_stock'])} SKU con stock negativo."],
    ["3", "Liquidar", "Priorizar devolución, traslado o descuento según costo inmovilizado y margen posible."],
    ["4", "Cambiar la regla", "Comprar con demanda de 90 días, cobertura máxima y punto de reorden por SKU; no repetir una canasta tan amplia."],
]
story += [styled_table(["", "Acción", "Resultado esperado"], actions, [0.8 * cm, 4.0 * cm, 13.0 * cm])]
story += [Spacer(1, 0.22 * cm), p("Límite del análisis", "H2x")]
story += [p("El sistema no vincula cada unidad actual con el lote comprado en 2024. Por eso, el informe usa dos estimaciones conservadoras: absorción aparente = mínimo entre unidades compradas y vendidas después; remanente mínimo = mínimo entre stock positivo actual y unidades aún no absorbidas. Debe confirmarse con conteo físico.")]
story += [p(f"Fuente: motoshop_gold.duckdb de Cloudflare R2, descargada el 10 de septiembre de 2026. Última venta: {source['latest_sale_timestamp']}; inventario: {source['inventory_snapshot_date']}. Encabezado y detalle concilian en {money(invoice['header_total'])}.", "SmallX")]


doc.build(story)
print(OUTPUT_PDF)
