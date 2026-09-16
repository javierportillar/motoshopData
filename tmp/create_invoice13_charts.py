from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


BASE = Path("outputs/motoshop_factura_13_2024-07-27_20260902/analysis_data")
CHARTS = BASE / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

NAVY = "#0B1F33"
BLUE = "#2F6FED"
TEAL = "#0F9D8A"
AMBER = "#E7A23B"
RED = "#D95C5C"
LIGHT = "#E8EEF6"
GRID = "#D9E2EC"


def money_millions(x, _):
    return f"${x / 1_000_000:.1f}M"


plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }
)

summary = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
band = pd.read_csv(BASE / "sell_through_bands.csv")
monthly = pd.read_csv(BASE / "monthly_sales.csv", parse_dates=["mes"])
sku = pd.read_csv(BASE / "sku_audit.csv")


# 1) Cost absorption versus minimum potential residual.
absorbed = (
    summary["performance"]["cost_weighted_sell_through"]
    * summary["invoice"]["header_total"]
)
residual = summary["inventory"]["minimum_potential_invoice_residual_cost"]
fig, ax = plt.subplots(figsize=(7.2, 4.2))
wedges, _ = ax.pie(
    [absorbed, residual],
    colors=[TEAL, RED],
    startangle=90,
    counterclock=False,
    wedgeprops={"width": 0.35, "edgecolor": "white"},
)
ax.text(0, 0.08, "59,8%", ha="center", va="center", fontsize=24, fontweight="bold", color=NAVY)
ax.text(0, -0.18, "absorción aparente", ha="center", va="center", fontsize=10, color="#52616B")
ax.set_title("Costo de la factura: absorbido vs. potencialmente remanente", color=NAVY, pad=16)
ax.legend(
    wedges,
    [f"Absorbido aparente  ${absorbed/1_000_000:.2f}M", f"Remanente mínimo  ${residual/1_000_000:.2f}M"],
    loc="lower center",
    bbox_to_anchor=(0.5, -0.12),
    frameon=False,
    ncol=1,
)
fig.tight_layout()
fig.savefig(CHARTS / "cost_absorption.png", dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)


# 2) Sell-through bands: invoice cost and SKU count.
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), gridspec_kw={"wspace": 0.32})
colors = [RED, "#F08A5D", AMBER, BLUE, TEAL]
axes[0].bar(band["banda_sell_through"], band["costo_factura"], color=colors)
axes[0].yaxis.set_major_formatter(FuncFormatter(money_millions))
axes[0].set_title("Costo de compra por banda", color=NAVY)
axes[0].set_xlabel("Sell-through aparente")
axes[0].grid(axis="y", color=GRID, linewidth=0.7)
axes[0].set_axisbelow(True)
for i, v in enumerate(band["costo_factura"]):
    axes[0].text(i, v + 90_000, f"${v/1_000_000:.2f}M", ha="center", va="bottom", fontsize=8)

axes[1].bar(band["banda_sell_through"], band["skus"], color=colors)
axes[1].set_title("Cantidad de SKU por banda", color=NAVY)
axes[1].set_xlabel("Sell-through aparente")
axes[1].grid(axis="y", color=GRID, linewidth=0.7)
axes[1].set_axisbelow(True)
for i, v in enumerate(band["skus"]):
    axes[1].text(i, v + 4, f"{int(v)}", ha="center", va="bottom", fontsize=9)
fig.suptitle("La compra quedó polarizada: ganadores claros y cola larga sin salida", fontsize=15, fontweight="bold", color=NAVY, y=1.03)
fig.savefig(CHARTS / "sell_through_bands.png", dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)


# 3) Monthly sales of SKUs included in the invoice.
monthly["label"] = monthly["mes"].dt.strftime("%b\n%Y")
fig, ax = plt.subplots(figsize=(11.2, 4.4))
bar_colors = [BLUE] * len(monthly)
if len(bar_colors):
    bar_colors[-1] = AMBER  # current partial month
ax.bar(monthly["label"], monthly["ventas"], color=bar_colors, width=0.75)
ax.yaxis.set_major_formatter(FuncFormatter(money_millions))
ax.set_title("Ventas mensuales de los SKU de la factura", color=NAVY, pad=12)
ax.set_ylabel("Ventas (COP)")
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.set_axisbelow(True)
ax.tick_params(axis="x", rotation=0)
ax.text(0.995, 0.95, "Septiembre 2026: mes parcial", transform=ax.transAxes, ha="right", va="top", fontsize=9, color="#7A5A00")
fig.tight_layout()
fig.savefig(CHARTS / "monthly_sales.png", dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)


# 4) Highest-cost SKUs with no sales since the invoice.
never = sku[(sku["unidades_vendidas_desde"] <= 0) & (sku["stock_actual"] > 0)].nlargest(12, "costo_factura")
never = never.sort_values("costo_factura")
labels = [f"{code} · {name[:38]}" for code, name in zip(never["cod_producto"], never["producto"])]
fig, ax = plt.subplots(figsize=(10.5, 5.8))
ax.barh(labels, never["costo_factura"], color=RED)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x/1_000:.0f}k"))
ax.set_title("Mayor capital original sin una sola venta posterior", color=NAVY, pad=12)
ax.set_xlabel("Costo en la factura (COP)")
ax.grid(axis="x", color=GRID, linewidth=0.7)
ax.set_axisbelow(True)
for y, v in enumerate(never["costo_factura"]):
    ax.text(v + 4_000, y, f"${v/1_000:.0f}k", va="center", fontsize=8)
fig.tight_layout()
fig.savefig(CHARTS / "never_sold_top.png", dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)

print(f"Charts written to {CHARTS}")
