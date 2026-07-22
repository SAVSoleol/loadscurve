from __future__ import annotations
from io import BytesIO
import pandas as pd
import matplotlib.pyplot as plt


def to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def to_excel(annual, weekday, weekend, monthly) -> bytes:
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        annual.to_excel(writer, sheet_name="Courbe annuelle", index=False)
        weekday.to_excel(writer, sheet_name="Journée semaine", index=False)
        weekend.to_excel(writer, sheet_name="Journée week-end", index=False)
        monthly.to_excel(writer, sheet_name="Résumé mensuel", index=False)
        for ws in writer.sheets.values():
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cells in ws.columns:
                letter = cells[0].column_letter
                width = max((len(str(c.value)) for c in cells[:1000] if c.value is not None), default=10)
                ws.column_dimensions[letter].width = min(max(width + 2, 12), 28)
    return out.getvalue()


def to_png(day_df: pd.DataFrame, title: str) -> bytes:
    out = BytesIO()
    merged = day_df.groupby("Heure", as_index=False).agg(Puissance_kW=("Puissance_kW", "sum"))
    colors = []
    tariffs = day_df.groupby("Heure")["Tarif"].first()
    for h in merged["Heure"]:
        colors.append("#e53935" if tariffs[h] == "HT" else "#1e40af")

    fig, ax = plt.subplots(figsize=(13, 6))
    x = range(len(merged))
    y = merged["Puissance_kW"].to_numpy()
    for i in range(len(merged) - 1):
        ax.plot([i, i + 1], [y[i], y[i + 1]], color=colors[i], linewidth=2.2)
    ax.fill_between(x, 0, y, color="#dbeafe", alpha=0.35)
    ax.set_xlim(0, 95)
    ax.set_title(title)
    ax.set_xlabel("Heure")
    ax.set_ylabel("Puissance (kW)")
    ax.grid(alpha=0.25)
    ticks = list(range(0, 96, 8)) + [95]
    labels = [merged.iloc[i]["Heure"] for i in ticks[:-1]] + ["24:00"]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    fig.tight_layout()
    fig.savefig(out, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()
