"""Generadores deterministas de reportes en Excel, PDF y Word con diseño de marca."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import docx
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


@dataclass
class ReportData:
    title: str
    subtitle: str
    tenant_name: str
    brand_color: str = "#7B1818"
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    summary_metrics: dict[str, str] = field(default_factory=dict)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.lstrip("#")
    if len(clean) != 6:
        clean = "7B1818"
    return tuple(int(clean[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


# ── Excel Generator (.xlsx) ──────────────────────────────────────────────────


def generate_excel(report: ReportData) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report.title[:30]
    ws.views.sheetView[0].showGridLines = True

    brand_hex = report.brand_color.lstrip("#").upper()
    fill_header = PatternFill(start_color=brand_hex, end_color=brand_hex, fill_type="solid")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_title = Font(name="Calibri", size=16, bold=True, color="1E293B")
    font_subtitle = Font(name="Calibri", size=10, italic=True, color="64748B")
    font_company = Font(name="Calibri", size=11, bold=True, color=brand_hex)

    fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_white = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    total_border = Border(
        top=Side(style="thin", color="0F172A"),
        bottom=Side(style="double", color="0F172A"),
    )

    # Header de compañía y título
    ws.cell(row=1, column=1, value=report.tenant_name.upper()).font = font_company
    ws.cell(row=2, column=1, value=report.title).font = font_title
    ws.cell(row=3, column=1, value=report.subtitle).font = font_subtitle

    current_row = 5

    # Métricas clave de resumen (KPIs)
    if report.summary_metrics:
        ws.cell(row=current_row, column=1, value="RESUMEN EJECUTIVO").font = Font(
            name="Calibri", size=11, bold=True, color="334155"
        )
        current_row += 1
        col_idx = 1
        for label, val in report.summary_metrics.items():
            cell_lbl = ws.cell(row=current_row, column=col_idx, value=label)
            cell_lbl.font = Font(name="Calibri", size=9, bold=True, color="64748B")
            cell_lbl.fill = fill_alt
            cell_lbl.border = thin_border

            cell_val = ws.cell(row=current_row + 1, column=col_idx, value=val)
            cell_val.font = Font(name="Calibri", size=12, bold=True, color="0F172A")
            cell_val.fill = fill_white
            cell_val.border = thin_border
            col_idx += 1
        current_row += 3

    # Tabla de datos
    header_row = current_row
    for col_num, col_name in enumerate(report.columns, start=1):
        c = ws.cell(row=header_row, column=col_num, value=col_name)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border

    current_row += 1
    numeric_totals: dict[int, float] = {}

    for r_idx, row_values in enumerate(report.rows):
        row_fill = fill_alt if r_idx % 2 == 1 else fill_white
        for c_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=current_row, column=c_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.fill = row_fill
            cell.border = thin_border

            if isinstance(val, (int, float)):
                numeric_totals[c_idx] = numeric_totals.get(c_idx, 0.0) + float(val)
                if isinstance(val, float) or "valor" in report.columns[c_idx - 1].lower() or "venta" in report.columns[c_idx - 1].lower():
                    cell.number_format = "$#,##0"
                else:
                    cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            else:
                cell.alignment = Alignment(horizontal="left")
        current_row += 1

    # Fila de totales si hay columnas numéricas acumulables
    if numeric_totals:
        c_label = ws.cell(row=current_row, column=1, value="TOTAL")
        c_label.font = Font(name="Calibri", size=11, bold=True, color="0F172A")
        c_label.border = total_border
        for c_idx in range(1, len(report.columns) + 1):
            cell = ws.cell(row=current_row, column=c_idx)
            cell.border = total_border
            if c_idx in numeric_totals:
                cell.value = numeric_totals[c_idx]
                cell.font = Font(name="Calibri", size=11, bold=True, color="0F172A")
                if "valor" in report.columns[c_idx - 1].lower() or "venta" in report.columns[c_idx - 1].lower():
                    cell.number_format = "$#,##0"
                else:
                    cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")

    # Ajuste automático del ancho de columnas
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── PDF Generator (.pdf) ─────────────────────────────────────────────────────


def generate_pdf(report: ReportData) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    r, g, b = _hex_to_rgb(report.brand_color)
    brand_col = colors.Color(r / 255.0, g / 255.0, b / 255.0)

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    company_style = ParagraphStyle(
        "CompanyHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=brand_col,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=14,
    )
    th_style = ParagraphStyle(
        "THStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=1,  # Center
    )
    td_style = ParagraphStyle(
        "TDStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
    )
    td_num_style = ParagraphStyle(
        "TDNumStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
        alignment=2,  # Right
    )

    elements = [
        Paragraph(report.tenant_name.upper(), company_style),
        Paragraph(report.title, title_style),
        Paragraph(report.subtitle, subtitle_style),
    ]

    # KPIs resumen
    if report.summary_metrics:
        kpi_data = [
            [
                Paragraph(f"<b>{k}</b>", ParagraphStyle("KPIKey", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))),
                Paragraph(f"<b>{v}</b>", ParagraphStyle("KPIVal", parent=styles["Normal"], fontSize=10, textColor=brand_col)),
            ]
            for k, v in report.summary_metrics.items()
        ]
        kpi_table = Table(kpi_data, colWidths=[150, 180])
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(kpi_table)
        elements.append(Spacer(1, 14))

    # Construcción de la tabla principal
    table_data = []
    # Encabezados
    table_data.append([Paragraph(c, th_style) for c in report.columns])

    for row in report.rows:
        row_cells = []
        for c_idx, val in enumerate(row):
            if isinstance(val, (int, float)):
                if isinstance(val, float) or "valor" in report.columns[c_idx].lower() or "venta" in report.columns[c_idx].lower():
                    formatted = f"${val:,.0f} COP".replace(",", ".")
                else:
                    formatted = f"{val:,.0f}".replace(",", ".")
                row_cells.append(Paragraph(formatted, td_num_style))
            else:
                row_cells.append(Paragraph(str(val), td_style))
        table_data.append(row_cells)

    # Anchos de columna proporcionales al tamaño de página (540pt disponibles)
    available_width = 540
    num_cols = max(len(report.columns), 1)
    col_width = available_width / num_cols
    # Si primera y segunda columna son texto y las otras números, dar más ancho a producto
    col_widths = [col_width] * num_cols
    if num_cols >= 3:
        col_widths[0] = 70  # Código / SKU
        col_widths[1] = available_width - 70 - (num_cols - 2) * 80  # Nombre producto
        for i in range(2, num_cols):
            col_widths[i] = 80

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), brand_col),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(t)

    # Footer con fecha y paginado
    def add_footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        page_str = f"Página {d.page} · Sistema de Inteligencia de Negocio {report.tenant_name}"
        canvas.drawRightString(doc.pagesize[0] - 36, 20, page_str)
        canvas.drawString(36, 20, "Confidencial · Datos reales respaldados por DuckDB")
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    return buf.getvalue()


# ── Word Generator (.docx) ───────────────────────────────────────────────────


def _set_cell_background(cell, hex_color: str):
    tc_pr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color.lstrip("#"))
    tc_pr.append(shd)


def generate_word(report: ReportData) -> bytes:
    doc = docx.Document()

    # Configurar márgenes a 1 pulgada (72 pt)
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)

    r, g, b = _hex_to_rgb(report.brand_color)
    brand_rgb = RGBColor(r, g, b)

    # Encabezado corporativo
    p_comp = doc.add_paragraph()
    run_comp = p_comp.add_run(report.tenant_name.upper())
    run_comp.font.name = "Calibri"
    run_comp.font.size = Pt(11)
    run_comp.font.bold = True
    run_comp.font.color.rgb = brand_rgb
    p_comp.paragraph_format.space_after = Pt(2)

    # Título principal
    p_title = doc.add_paragraph()
    run_title = p_title.add_run(report.title)
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(15, 23, 42)
    p_title.paragraph_format.space_after = Pt(2)

    # Subtítulo / Metadatos
    p_sub = doc.add_paragraph()
    run_sub = p_sub.add_run(report.subtitle)
    run_sub.font.name = "Calibri"
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)
    p_sub.paragraph_format.space_after = Pt(14)

    # Resumen Ejecutivo (KPIs)
    if report.summary_metrics:
        p_kpi_title = doc.add_paragraph()
        run_kpi_title = p_kpi_title.add_run("Resumen Ejecutivo")
        run_kpi_title.font.name = "Calibri"
        run_kpi_title.font.size = Pt(12)
        run_kpi_title.font.bold = True
        p_kpi_title.paragraph_format.space_after = Pt(4)

        kpi_table = doc.add_table(rows=len(report.summary_metrics), cols=2)
        kpi_table.alignment = WD_TABLE_ALIGNMENT.LEFT
        for idx, (k, v) in enumerate(report.summary_metrics.items()):
            row = kpi_table.rows[idx]
            cell_k, cell_v = row.cells[0], row.cells[1]
            _set_cell_background(cell_k, "F8FAFC")
            _set_cell_background(cell_v, "FFFFFF")

            pk = cell_k.paragraphs[0]
            rk = pk.add_run(k)
            rk.font.name = "Calibri"
            rk.font.size = Pt(9)
            rk.font.bold = True
            rk.font.color.rgb = RGBColor(71, 85, 105)

            pv = cell_v.paragraphs[0]
            rv = pv.add_run(v)
            rv.font.name = "Calibri"
            rv.font.size = Pt(11)
            rv.font.bold = True
            rv.font.color.rgb = brand_rgb

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # Tabla principal de datos
    table = doc.add_table(rows=1 + len(report.rows), cols=len(report.columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Encabezado
    hdr_cells = table.rows[0].cells
    brand_hex = report.brand_color.lstrip("#")
    for i, title in enumerate(report.columns):
        _set_cell_background(hdr_cells[i], brand_hex)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        run.font.name = "Calibri"
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    # Datos
    for r_idx, row_data in enumerate(report.rows):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row_data):
            _set_cell_background(row_cells[c_idx], bg_color)
            p = row_cells[c_idx].paragraphs[0]
            if isinstance(val, (int, float)):
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if isinstance(val, float) or "valor" in report.columns[c_idx].lower() or "venta" in report.columns[c_idx].lower():
                    formatted = f"${val:,.0f} COP".replace(",", ".")
                else:
                    formatted = f"{val:,.0f}".replace(",", ".")
                run = p.add_run(formatted)
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                run = p.add_run(str(val))
            run.font.name = "Calibri"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(30, 41, 59)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Pie de página institucional
    p_footer = doc.add_paragraph()
    r_foot = p_footer.add_run(
        f"Documento confidencial generado por el Asistente IA de {report.tenant_name}. Datos extraídos directamente de DuckDB Gold Marts."
    )
    r_foot.font.name = "Calibri"
    r_foot.font.size = Pt(8)
    r_foot.font.italic = True
    r_foot.font.color.rgb = RGBColor(148, 163, 184)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
