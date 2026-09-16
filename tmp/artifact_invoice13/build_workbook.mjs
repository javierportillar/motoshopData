import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "/Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData";
const outputDir = path.join(root, "outputs/motoshop_factura_13_2024-07-27_20260910");
const dataDir = path.join(outputDir, "analysis_data");
const previewDir = path.join(root, "tmp/artifact_invoice13/previews_20260910");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const loadJson = async (name) => JSON.parse(await fs.readFile(path.join(dataDir, `${name}.json`), "utf8"));
const summaryData = JSON.parse(await fs.readFile(path.join(dataDir, "summary.json"), "utf8"));
const skuAudit = await loadJson("sku_audit");
const monthlySales = await loadJson("monthly_sales");
const allRisk = await loadJson("all_risk");
const topPerformers = await loadJson("top_performers");
const duplicateSkus = await loadJson("duplicate_skus");
const negativeStock = await loadJson("negative_stock");

const inventoryDate = new Date(`${summaryData.source.inventory_snapshot_date}T00:00:00`);
const latestSale = new Date(summaryData.source.latest_sale_timestamp);
const latestPurchase = new Date(`${summaryData.source.latest_purchase_date}T00:00:00`);
const quarterTotals = new Map();
for (const row of monthlySales) {
  const date = new Date(`${String(row.mes).slice(0, 10)}T00:00:00`);
  const quarter = Math.floor(date.getMonth() / 3) + 1;
  const key = `${date.getFullYear()}-T${quarter}`;
  quarterTotals.set(key, (quarterTotals.get(key) ?? 0) + Number(row.ventas));
}
const quarterlySales = [...quarterTotals.entries()].map(([period, sales]) => ({ period, sales }));

const wb = Workbook.create();
const resumen = wb.worksheets.add("Resumen");
const detalle = wb.worksheets.add("Detalle SKU");
const riesgos = wb.worksheets.add("Riesgos");
const topVentas = wb.worksheets.add("Top ventas");
const tendencia = wb.worksheets.add("Tendencia mensual");
const controles = wb.worksheets.add("Controles");
const fuentes = wb.worksheets.add("Fuentes");

const colors = {
  navy: "#0B1F33",
  blue: "#2F6FED",
  teal: "#0F9D8A",
  amber: "#E7A23B",
  red: "#D95C5C",
  paleRed: "#FDECEC",
  paleBlue: "#EAF1FF",
  paleTeal: "#E7F6F3",
  paleAmber: "#FFF4DD",
  text: "#172B4D",
  muted: "#5B6B7A",
  border: "#D9E2EC",
  white: "#FFFFFF",
};

const titleStyle = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 18 },
  verticalAlignment: "center",
};
const subtitleStyle = {
  fill: "#DCE7F3",
  font: { color: colors.navy, size: 10 },
  verticalAlignment: "center",
};
const sectionStyle = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 11 },
  verticalAlignment: "center",
};
const headerStyle = {
  fill: colors.blue,
  font: { bold: true, color: colors.white, size: 9 },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: colors.border },
};
const bodyBorder = { preset: "inside", style: "thin", color: "#E8EDF3" };

function setTitle(sheet, range, title, subtitle, endCol) {
  sheet.showGridLines = false;
  sheet.mergeCells(range);
  sheet.getRange(range.split(":")[0]).values = [[title]];
  sheet.getRange(range).format = titleStyle;
  sheet.getRange(range).format.rowHeight = 32;
  const subtitleRange = `A2:${endCol}2`;
  sheet.mergeCells(subtitleRange);
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(subtitleRange).format = subtitleStyle;
  sheet.getRange(subtitleRange).format.rowHeight = 24;
}

function asDate(value) {
  if (!value) return null;
  return new Date(value.replace(" ", "T"));
}

function writeTableSheet(sheet, title, subtitle, headers, rows, widths) {
  const endCol = columnName(headers.length);
  setTitle(sheet, `A1:${endCol}1`, title, subtitle, endCol);
  sheet.getRange(`A4:${endCol}4`).values = [headers];
  sheet.getRange(`A4:${endCol}4`).format = headerStyle;
  sheet.getRange(`A4:${endCol}4`).format.rowHeight = 32;
  if (rows.length) {
    sheet.getRangeByIndexes(4, 0, rows.length, headers.length).values = rows;
    sheet.getRangeByIndexes(4, 0, rows.length, headers.length).format = {
      font: { color: colors.text, size: 9 },
      borders: bodyBorder,
      verticalAlignment: "center",
    };
    const table = sheet.tables.add(`A4:${endCol}${4 + rows.length}`, true, `${sheet.name.replace(/[^A-Za-z0-9]/g, "")}Table`);
    table.showBandedRows = true;
  }
  sheet.freezePanes.freezeRows(4);
  for (let i = 0; i < widths.length; i += 1) {
    sheet.getRange(`${columnName(i + 1)}:${columnName(i + 1)}`).format.columnWidth = widths[i];
  }
  return { endCol, lastRow: 4 + rows.length };
}

function columnName(n) {
  let s = "";
  let x = n;
  while (x > 0) {
    x -= 1;
    s = String.fromCharCode(65 + (x % 26)) + s;
    x = Math.floor(x / 26);
  }
  return s;
}

// Detalle SKU: raw inputs plus auditable formula-driven calculations.
const detailHeaders = [
  "SKU", "Producto", "Líneas factura", "Unid. compradas", "Costo unit. factura", "Costo factura",
  "Stock actual", "Valor stock a costo factura", "Unid. vendidas desde", "Ventas desde", "Facturas venta",
  "Primera venta", "Última venta", "Días sin venta", "Unid. 30d", "Unid. 90d", "Unid. 365d",
  "Absorción aparente", "Sell-through", "Remanente mínimo unid.", "Remanente mínimo costo",
  "Compras posteriores unid.", "Docs compra posteriores", "Última compra", "Precio venta actual",
  "Ingreso cohorte estimado", "Utilidad bruta estimada", "Margen estimado", "Banda", "Estado auditoría",
];
const detailRows = skuAudit.map((r) => [
  r.cod_producto, r.producto, r.lineas_factura, r.cantidad_comprada, r.costo_unitario_factura, r.costo_factura,
  r.stock_actual, null, r.unidades_vendidas_desde, r.ventas_desde, r.facturas_venta_desde,
  asDate(r.primera_venta_desde), asDate(r.ultima_venta_desde), null, r.unidades_30d, r.unidades_90d,
  r.unidades_365d, null, null, null, null, r.unidades_compradas_despues, r.documentos_compra_despues,
  asDate(r.ultima_compra_despues), r.precio_venta_actual, null, null, null, null, null,
]);
const detailInfo = writeTableSheet(
  detalle,
  "Auditoría por SKU · Factura 13 / S18",
  "578 SKU únicos · 580 líneas · Fórmulas visibles para sell-through, residual y clasificación",
  detailHeaders,
  detailRows,
  [14, 42, 10, 11, 14, 14, 11, 16, 13, 14, 11, 14, 14, 11, 10, 10, 10, 12, 11, 14, 14, 14, 12, 14, 14, 15, 15, 11, 10, 27],
);
const detailEnd = detailInfo.lastRow;
detalle.getRange("H5").formulas = [["=MAX(G5,0)*E5"]];
detalle.getRange("H5:H" + detailEnd).fillDown();
detalle.getRange("N5").formulas = [["=IF(M5=\"\",\"\",MAX(0,'Resumen'!$B$3-M5))"]];
detalle.getRange("N5:N" + detailEnd).fillDown();
detalle.getRange("R5").formulas = [["=MIN(D5,I5)"]];
detalle.getRange("R5:R" + detailEnd).fillDown();
detalle.getRange("S5").formulas = [["=IFERROR(R5/D5,0)"]];
detalle.getRange("S5:S" + detailEnd).fillDown();
detalle.getRange("T5").formulas = [["=MIN(MAX(G5,0),MAX(D5-I5,0))"]];
detalle.getRange("T5:T" + detailEnd).fillDown();
detalle.getRange("U5").formulas = [["=T5*E5"]];
detalle.getRange("U5:U" + detailEnd).fillDown();
detalle.getRange("Z5").formulas = [["=IF(I5>0,R5*(J5/I5),0)"]];
detalle.getRange("Z5:Z" + detailEnd).fillDown();
detalle.getRange("AA5").formulas = [["=Z5-(R5*E5)"]];
detalle.getRange("AA5:AA" + detailEnd).fillDown();
detalle.getRange("AB5").formulas = [["=IFERROR(AA5/Z5,0)"]];
detalle.getRange("AB5:AB" + detailEnd).fillDown();
detalle.getRange("AC5").formulas = [["=IF(S5=0,\"0%\",IF(S5<0.5,\"1-49%\",IF(S5<0.8,\"50-79%\",IF(S5<1,\"80-99%\",\"100%\"))))"]];
detalle.getRange("AC5:AC" + detailEnd).fillDown();
detalle.getRange("AD5").formulas = [["=IF(G5<0,\"Stock negativo\",IF(G5<=0,\"Sin stock actual\",IF(I5<=0,\"Sin ventas desde compra\",IF(Q5<=0,\"Con stock, sin ventas 365d\",IF(S5<0.5,\"Rotación baja\",IF(S5<1,\"Rotación media\",\"Compra absorbida; stock repuesto\"))))))"]];
detalle.getRange("AD5:AD" + detailEnd).fillDown();
detalle.getRange(`D5:D${detailEnd}`).format.numberFormat = "#,##0";
detalle.getRange(`G5:G${detailEnd}`).format.numberFormat = "#,##0;[Red](#,##0)";
detalle.getRange(`I5:I${detailEnd}`).format.numberFormat = "#,##0";
detalle.getRange(`O5:R${detailEnd}`).format.numberFormat = "#,##0";
detalle.getRange(`T5:T${detailEnd}`).format.numberFormat = "#,##0";
detalle.getRange(`V5:V${detailEnd}`).format.numberFormat = "#,##0";
detalle.getRange(`E5:F${detailEnd}`).format.numberFormat = "$#,##0;[Red]($#,##0)";
detalle.getRange(`H5:H${detailEnd}`).format.numberFormat = "$#,##0;[Red]($#,##0)";
detalle.getRange(`J5:J${detailEnd}`).format.numberFormat = "$#,##0;[Red]($#,##0)";
detalle.getRange(`U5:U${detailEnd}`).format.numberFormat = "$#,##0;[Red]($#,##0)";
detalle.getRange(`Y5:AA${detailEnd}`).format.numberFormat = "$#,##0;[Red]($#,##0)";
detalle.getRange(`S5:S${detailEnd}`).format.numberFormat = "0.0%";
detalle.getRange(`AB5:AB${detailEnd}`).format.numberFormat = "0.0%";
detalle.getRange(`L5:M${detailEnd}`).format.numberFormat = "yyyy-mm-dd";
detalle.getRange(`X5:X${detailEnd}`).format.numberFormat = "yyyy-mm-dd";
detalle.getRange(`B5:B${detailEnd}`).format.wrapText = true;
detalle.getRange(`G5:G${detailEnd}`).conditionalFormats.add("cellIs", { operator: "lessThan", formula: 0, format: { fill: colors.paleRed, font: { color: "#9B1C1C", bold: true } } });
detalle.getRange(`S5:S${detailEnd}`).conditionalFormats.add("colorScale", { colors: ["#F8696B", "#FFEB84", "#63BE7B"] });

// Executive summary.
setTitle(
  resumen,
  "A1:L1",
  "MotoShop · Evaluación de compra · Factura 13 / S18",
  `Proveedor: KAROL NATALIA BURGOS BUSTOS · Compra: 2024-07-27 15:40 · Datos actualizados al ${summaryData.source.inventory_snapshot_date}`,
  "L",
);
resumen.getRange("A3").values = [["Corte de datos"]];
resumen.getRange("B3").values = [[inventoryDate]];
resumen.getRange("B3").format.numberFormat = "yyyy-mm-dd";
resumen.getRange("D3").values = [["Última venta"]];
resumen.getRange("E3:F3").merge();
resumen.getRange("E3").values = [[latestSale]];
resumen.getRange("E3").format.numberFormat = "yyyy-mm-dd hh:mm";
resumen.getRange("H3").values = [["Última compra"]];
resumen.getRange("I3:J3").merge();
resumen.getRange("I3").values = [[latestPurchase]];
resumen.getRange("I3").format.numberFormat = "yyyy-mm-dd";
resumen.getRange("A3:L3").format = { font: { color: colors.muted, size: 9 }, verticalAlignment: "center" };

resumen.mergeCells("A5:L7");
resumen.getRange("A5").values = [["VEREDICTO: SÍ HUBO SOBRECOMPRA. Solo 52,2% de las unidades muestra salida atribuible; quedan al menos 1.861 unidades por $4,51 millones y 150 SKU nunca se vendieron."]];
resumen.getRange("A5:L7").format = { fill: colors.paleRed, font: { bold: true, color: "#8A1C1C", size: 13 }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "center", borders: { preset: "outside", style: "medium", color: colors.red } };

const cardRanges = [["A9:B9", "A10:B11"], ["C9:D9", "C10:D11"], ["E9:F9", "E10:F11"], ["G9:H9", "G10:H11"], ["I9:J9", "I10:J11"], ["K9:L9", "K10:L11"]];
const cardLabels = ["VALOR FACTURA", "ABSORCIÓN UNIDADES", "SIN SALIDA EST.", "REMANENTE MÍNIMO", "SKU SIN VENTAS", "SKU ABSORBIDOS 100%"];
const cardFormulas = [
  `=SUM('Detalle SKU'!$F$5:$F$${detailEnd})`,
  `=SUM('Detalle SKU'!$R$5:$R$${detailEnd})/SUM('Detalle SKU'!$D$5:$D$${detailEnd})`,
  `=SUM('Detalle SKU'!$D$5:$D$${detailEnd})-SUM('Detalle SKU'!$R$5:$R$${detailEnd})`,
  `=SUM('Detalle SKU'!$U$5:$U$${detailEnd})`,
  `=COUNTIF('Detalle SKU'!$I$5:$I$${detailEnd},0)`,
  `=COUNTIF('Detalle SKU'!$S$5:$S$${detailEnd},1)`,
];
for (let i = 0; i < cardRanges.length; i += 1) {
  const [labelRange, valueRange] = cardRanges[i];
  resumen.mergeCells(labelRange);
  resumen.mergeCells(valueRange);
  resumen.getRange(labelRange.split(":")[0]).values = [[cardLabels[i]]];
  resumen.getRange(valueRange.split(":")[0]).formulas = [[cardFormulas[i]]];
  resumen.getRange(labelRange).format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 9 }, horizontalAlignment: "center", verticalAlignment: "center" };
  resumen.getRange(valueRange).format = { fill: i === 3 ? colors.paleAmber : (i === 4 || i === 5 ? colors.paleRed : colors.paleBlue), font: { bold: true, color: colors.navy, size: 17 }, horizontalAlignment: "center", verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: colors.border } };
}
resumen.getRange("A10").format.numberFormat = "$#,##0";
resumen.getRange("C10").format.numberFormat = "0.0%";
resumen.getRange("E10").format.numberFormat = "#,##0";
resumen.getRange("G10").format.numberFormat = "$#,##0";
resumen.getRange("I10").format.numberFormat = "#,##0";
resumen.getRange("K10").format.numberFormat = "#,##0";

resumen.mergeCells("A13:L15");
resumen.getRange("A13").values = [["Lectura ejecutiva: la compra no fue buena como conjunto. De 3.897 unidades, 1.862 siguen sin absorción aparente (47,8%). Además, 239 SKU quedaron por debajo de 50% de absorción. Sí hubo 258 SKU totalmente absorbidos: la corrección es reducir amplitud y cantidades, no abandonar todos los productos."]];
resumen.getRange("A13:L15").format = { fill: colors.paleBlue, font: { color: colors.text, size: 11 }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: colors.border } };

// Formula-backed chart helper: SKU by sell-through band.
resumen.getRange("A37:B37").values = [["Banda", "SKU"]];
resumen.getRange("A38:A42").values = [["0%"], ["1-49%"], ["50-79%"], ["80-99%"], ["100%"]];
resumen.getRange("B38").formulas = [[`=COUNTIF('Detalle SKU'!$AC$5:$AC$${detailEnd},A38)`]];
resumen.getRange("B38:B42").fillDown();
resumen.getRange("A37:B37").format = headerStyle;
resumen.getRange("B38:B42").format.numberFormat = "#,##0";

// Compact quarterly sales helper.
resumen.getRange("E37:F37").values = [["Trimestre", "Ventas"]];
for (let i = 0; i < quarterlySales.length; i += 1) {
  const row = 38 + i;
  resumen.getRange(`E${row}`).values = [[quarterlySales[i].period]];
  resumen.getRange(`F${row}`).values = [[quarterlySales[i].sales]];
}
resumen.getRange("E37:F37").format = headerStyle;
resumen.getRange(`F38:F${37 + quarterlySales.length}`).format.numberFormat = "$#,##0";

const bandChart = resumen.charts.add("bar", resumen.getRange("A37:B42"));
bandChart.title = "SKU por nivel de absorción";
bandChart.hasLegend = false;
bandChart.setPosition("A17", "F34");

const trendChart = resumen.charts.add("column", resumen.getRange(`E37:F${37 + quarterlySales.length}`));
trendChart.title = "Ventas trimestrales de los mismos SKU";
trendChart.hasLegend = false;
trendChart.xAxis = { axisType: "textAxis" };
trendChart.yAxis = { numberFormatCode: "$#,##0,,\"M\"" };
trendChart.setPosition("G17", "L34");

resumen.getRange("A:L").format.columnWidth = 13;
resumen.getRange("A:A").format.columnWidth = 18;
resumen.getRange("E:E").format.columnWidth = 15;
resumen.freezePanes.freezeRows(3);

// Monthly trend source.
const trendHeaders = ["Mes", "Ventas", "Unidades", "Utilidad bruta", "Facturas"];
const trendRows = monthlySales.map((r) => [
  new Date(`${String(r.mes).slice(0, 10)}T00:00:00`), r.ventas, r.unidades, r.utilidad_bruta, r.facturas,
]);
const trendInfo = writeTableSheet(
  tendencia,
  "Tendencia mensual de los SKU de la factura",
  "Ventas válidas posteriores a 2024-07-27 15:40 · Septiembre 2026 es un mes parcial",
  trendHeaders,
  trendRows,
  [14, 16, 12, 16, 10],
);
tendencia.getRange(`A5:A${trendInfo.lastRow}`).format.numberFormat = "mmm yyyy";
tendencia.getRange(`B5:B${trendInfo.lastRow}`).format.numberFormat = "$#,##0";
tendencia.getRange(`C5:C${trendInfo.lastRow}`).format.numberFormat = "#,##0";
tendencia.getRange(`D5:D${trendInfo.lastRow}`).format.numberFormat = "$#,##0";

// Risk and winners views.
const riskHeaders = ["SKU", "Producto", "Compra unid.", "Costo factura", "Stock", "Valor stock costo original", "Vendidas desde", "Unid. 365d", "Días sin venta", "Sell-through", "Remanente mín. costo", "Estado"];
const riskRows = allRisk.map((r) => [r.cod_producto, r.producto, r.cantidad_comprada, r.costo_factura, r.stock_actual, r.valor_stock_a_costo_factura, r.unidades_vendidas_desde, r.unidades_365d, r.dias_sin_venta, r.sell_through_aparente, r.remanente_minimo_costo, r.estado_auditoria]);
const riskInfo = writeTableSheet(
  riesgos,
  "Riesgos y capital inmovilizado",
  "SKU con stock y sin ventas 365d, o con sell-through inferior a 50% · Ordenados por exposición",
  riskHeaders,
  riskRows,
  [14, 43, 11, 14, 10, 16, 12, 10, 11, 11, 15, 27],
);
riesgos.getRange(`C5:C${riskInfo.lastRow}`).format.numberFormat = "#,##0";
riesgos.getRange(`E5:I${riskInfo.lastRow}`).format.numberFormat = "#,##0";
riesgos.getRange(`D5:D${riskInfo.lastRow}`).format.numberFormat = "$#,##0";
riesgos.getRange(`F5:F${riskInfo.lastRow}`).format.numberFormat = "$#,##0";
riesgos.getRange(`J5:J${riskInfo.lastRow}`).format.numberFormat = "0.0%";
riesgos.getRange(`K5:K${riskInfo.lastRow}`).format.numberFormat = "$#,##0";
riesgos.getRange(`B5:B${riskInfo.lastRow}`).format.wrapText = true;

const winnerHeaders = ["SKU", "Producto", "Compra unid.", "Costo factura", "Vendidas desde", "Ventas desde", "Sell-through", "Ingreso cohorte est.", "Utilidad bruta est.", "Margen est.", "Stock", "Unid. 365d"];
const winnerRows = topPerformers.map((r) => [r.cod_producto, r.producto, r.cantidad_comprada, r.costo_factura, r.unidades_vendidas_desde, r.ventas_desde, r.sell_through_aparente, r.ingreso_cohorte_estimado, r.utilidad_bruta_cohorte_estimada, r.margen_cohorte_estimado, r.stock_actual, r.unidades_365d]);
const winnerInfo = writeTableSheet(
  topVentas,
  "Top 25 · Mayor utilidad bruta estimada",
  "Estimación de cohorte: unidades absorbidas × precio promedio de venta observado",
  winnerHeaders,
  winnerRows,
  [14, 43, 11, 14, 12, 14, 11, 15, 15, 11, 10, 10],
);
topVentas.getRange(`C5:C${winnerInfo.lastRow}`).format.numberFormat = "#,##0";
topVentas.getRange(`E5:E${winnerInfo.lastRow}`).format.numberFormat = "#,##0";
topVentas.getRange(`K5:L${winnerInfo.lastRow}`).format.numberFormat = "#,##0";
topVentas.getRange(`D5:D${winnerInfo.lastRow}`).format.numberFormat = "$#,##0";
topVentas.getRange(`F5:F${winnerInfo.lastRow}`).format.numberFormat = "$#,##0";
topVentas.getRange(`H5:I${winnerInfo.lastRow}`).format.numberFormat = "$#,##0";
topVentas.getRange(`G5:G${winnerInfo.lastRow}`).format.numberFormat = "0.0%";
topVentas.getRange(`J5:J${winnerInfo.lastRow}`).format.numberFormat = "0.0%";
topVentas.getRange(`B5:B${winnerInfo.lastRow}`).format.wrapText = true;

// Controls and caveats.
setTitle(controles, "A1:F1", "Controles de auditoría y límites", "Conciliaciones, calidad y metodología de atribución", "F");
controles.getRange("A4:F4").values = [["Control", "Resultado", "Estado", "Esperado", "Dónde revisar", "Nota"]];
controles.getRange("A4:F4").format = headerStyle;
const controlRows = [
  ["Factura encabezado vs detalle", null, null, 0, "Resumen / Detalle SKU", "Debe conciliar exactamente"],
  ["Líneas vs SKU únicos", null, null, 2, "Detalle SKU", "Hay dos SKU repetidos en líneas separadas"],
  ["SKU con stock negativo", null, null, 0, "Detalle SKU", "Requiere ajuste físico/contable"],
  ["SKU sin precio actual", null, null, 0, "Detalle SKU", "Afecta valoración comercial"],
  ["Cobertura de trazabilidad por lote", "No disponible", "ADVERTENCIA", "Lote/serial", "Kardex/POS", "No existe vínculo lote-compra-stock; el residual es una cota, no un conteo exacto"],
];
controles.getRange("A5:F9").values = controlRows;
controles.getRange("B5").formulas = [[`=11267897-SUM('Detalle SKU'!$F$5:$F$${detailEnd})`]];
controles.getRange("C5").formulas = [["=IF(B5=0,\"PASS\",\"FAIL\")"]];
controles.getRange("B6").formulas = [[`=580-COUNTA('Detalle SKU'!$A$5:$A$${detailEnd})`]];
controles.getRange("C6").formulas = [["=IF(B6=D6,\"PASS\",\"REVISAR\")"]];
controles.getRange("B7").formulas = [[`=COUNTIF('Detalle SKU'!$G$5:$G$${detailEnd},\"<0\")`]];
controles.getRange("C7").formulas = [["=IF(B7=D7,\"PASS\",\"FAIL\")"]];
controles.getRange("B8").formulas = [[`=COUNTBLANK('Detalle SKU'!$Y$5:$Y$${detailEnd})`]];
controles.getRange("C8").formulas = [["=IF(B8=D8,\"PASS\",\"FAIL\")"]];
controles.getRange("A11:F11").merge();
controles.getRange("A11").values = [["Definiciones metodológicas"]];
controles.getRange("A11:F11").format = sectionStyle;
const defs = [
  ["Absorción aparente", "MIN(unidades compradas, unidades vendidas después de la compra). Es una señal comercial, no una identificación física del lote."],
  ["Remanente mínimo", "MIN(stock actual positivo, MAX(unidades compradas - ventas posteriores, 0)). Es la cantidad mínima potencialmente atribuible a la factura bajo la información disponible."],
  ["Ingreso de cohorte estimado", "Unidades absorbidas × precio promedio de venta observado para el SKU después de la compra."],
  ["Buena compra", "Juicio integral: velocidad, amplitud de salida, capital todavía inmovilizado y recuperación. No usa un estándar externo ni reemplaza el conteo físico."],
];
controles.getRange("A12:B15").values = defs;
controles.getRange("A12:A15").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy }, wrapText: true };
controles.getRange("B12:B15").format = { font: { color: colors.text }, wrapText: true };
controles.getRange("A:F").format.columnWidth = 18;
controles.getRange("A:A").format.columnWidth = 28;
controles.getRange("B:B").format.columnWidth = 48;
controles.getRange("E:E").format.columnWidth = 24;
controles.getRange("F:F").format.columnWidth = 52;
controles.getRange("A4:F9").format.borders = bodyBorder;
controles.getRange("C5:C9").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: colors.paleRed, font: { color: "#9B1C1C", bold: true } } });
controles.getRange("C5:C9").conditionalFormats.add("containsText", { text: "PASS", format: { fill: colors.paleTeal, font: { color: "#087F5B", bold: true } } });

// Sources.
setTitle(fuentes, "A1:H1", "Fuentes y trazabilidad", "Extracción de producción y tablas utilizadas", "H");
fuentes.getRange("A4:H4").values = [["Item", "Valor", "Unidad", "Corte", "Tipo", "Fuente", "Referencia", "Notas"]];
fuentes.getRange("A4:H4").format = headerStyle;
const sourceRows = [
  ["Compra analizada", "Factura 13 / S18", "Documento", "2024-07-27 15:40", "POS", "MotoShop", "https://app.fragloesja.uk/dashboards/compras/dia/2024-07-27?from=mensual", "Proveedor NIT 1116274616"],
  ["Base analítica", "motoshop_gold.duckdb", "Archivo", "Descarga 2026-09-02 15:09 -05", "Cloudflare R2", "Bucket motoshop-gold", "https://4bd1502b7fa3f33d1d3c45ae2d252cfd.r2.cloudflarestorage.com", "Objeto productivo descargado en modo lectura"],
  ["Compra", "11.267.897", "COP", "2024-07-27", "Tabla", "silver_fact_compras + detalle", "num_documento=13; cod_clase=S18", "Encabezado y detalle concilian"],
  ["Ventas", "Hasta 2026-09-02 12:06", "Fecha/hora", "2026-09-02", "Tabla", "silver_fact_ventas + detalle", "estado_documento=B", "Solo ventas vigentes"],
  ["Inventario", "Snapshot 2026-09-02", "Fecha", "2026-09-02", "Tabla", "gold_mart_inventario_actual", "cantidad_actual", "Stock actual por SKU"],
  ["Maestro producto", "6.356 SKU", "Registros", "2026-09-02", "Tabla", "silver_dim_producto", "precio/costo/existencia", "Usado para precio actual"],
];
fuentes.getRange("A5:H10").values = sourceRows;
fuentes.getRange("A5:H10").format = { font: { color: colors.text, size: 9 }, wrapText: true, borders: bodyBorder, verticalAlignment: "top" };
const sourceWidths = [22, 28, 13, 20, 14, 28, 52, 40];
for (let i = 0; i < sourceWidths.length; i += 1) fuentes.getRange(`${columnName(i + 1)}:${columnName(i + 1)}`).format.columnWidth = sourceWidths[i];
fuentes.freezePanes.freezeRows(4);

// Compact checks and export.
const inspectSummary = await wb.inspect({ kind: "table", range: "Resumen!A1:L20", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 12, maxChars: 12000 });
console.log(inspectSummary.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan", maxChars: 8000 });
console.log(errors.ndjson);

const renderSpecs = [
  ["Resumen", "A1:L45"],
  ["Detalle SKU", "A1:AD24"],
  ["Riesgos", "A1:L24"],
  ["Top ventas", "A1:L24"],
  ["Tendencia mensual", `A1:E${Math.min(trendInfo.lastRow, 34)}`],
  ["Controles", "A1:F16"],
  ["Fuentes", "A1:H11"],
];
for (const [sheetName, range] of renderSpecs) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const out = await SpreadsheetFile.exportXlsx(wb);
const outputPath = path.join(outputDir, "auditoria_factura_13_motoshop.xlsx");
await out.save(outputPath);
console.log(JSON.stringify({ outputPath, detailRows: skuAudit.length, riskRows: allRisk.length }));
