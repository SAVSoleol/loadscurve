from __future__ import annotations

import plotly.graph_objects as go


def full_day_chart(df, title, compact=False):
    """
    Affiche une courbe continue de 00h00 à 24h00.
    Les segments HT et BT partagent les points de transition afin
    d'éviter tout espace vide entre les couleurs.
    """
    all_times = [
        f"{h:02d}:{m:02d}"
        for h in range(24)
        for m in (0, 15, 30, 45)
    ]

    lookup = (
        df.groupby("Heure")
        .agg(
            Puissance_kW=("Puissance_kW", "sum"),
            Tarif=("Tarif", "first"),
        )
        .reindex(all_times)
    )

    lookup["Puissance_kW"] = (
        lookup["Puissance_kW"]
        .interpolate(limit_direction="both")
        .fillna(0.0)
    )
    lookup["Tarif"] = lookup["Tarif"].ffill().bfill().fillna("BT")

    # Point final 24h00 identique à 00h00.
    x_values = list(range(97))
    y_values = lookup["Puissance_kW"].tolist() + [
        float(lookup.iloc[0]["Puissance_kW"])
    ]
    tariff_values = lookup["Tarif"].tolist() + [
        str(lookup.iloc[0]["Tarif"])
    ]

    fig = go.Figure()

    styles = {
        "HT": {
            "line": "#ef2b2d",
            "fill": "rgba(239,43,45,0.15)",
            "zone": "rgba(239,43,45,0.075)",
            "label": "Haut tarif (HT)",
        },
        "BT": {
            "line": "#3157ff",
            "fill": "rgba(49,87,255,0.11)",
            "zone": "rgba(49,87,255,0.045)",
            "label": "Bas tarif (BT)",
        },
    }

    # Blocs tarifaires continus.
    blocks = []
    block_start = 0
    for i in range(1, len(tariff_values)):
        if tariff_values[i] != tariff_values[i - 1]:
            blocks.append((block_start, i - 1, tariff_values[i - 1]))
            block_start = i
    blocks.append((block_start, len(tariff_values) - 1, tariff_values[-1]))

    legend_seen = set()

    for block_index, (block_start, block_end, tariff) in enumerate(blocks):
        style = styles[tariff]

        # Inclusion du point voisin aux frontières : le segment bleu et
        # le segment rouge se rejoignent exactement au même endroit.
        draw_start = block_start - 1 if block_index > 0 else block_start
        draw_end = block_end + 1 if block_index < len(blocks) - 1 else block_end
        draw_start = max(0, draw_start)
        draw_end = min(96, draw_end)

        fig.add_trace(
            go.Scatter(
                x=x_values[draw_start:draw_end + 1],
                y=y_values[draw_start:draw_end + 1],
                mode="lines",
                name=style["label"],
                legendgroup=tariff,
                showlegend=tariff not in legend_seen,
                line=dict(color=style["line"], width=2.4),
                fill="tozeroy",
                fillcolor=style["fill"],
                connectgaps=True,
                hovertemplate="%{y:.2f} kW<extra>"
                + style["label"]
                + "</extra>",
            )
        )
        legend_seen.add(tariff)

    # Fonds tarifaires.
    for block_start, block_end, tariff in blocks:
        if block_start >= 96:
            continue
        fig.add_vrect(
            x0=block_start,
            x1=min(block_end + 1, 96),
            fillcolor=styles[tariff]["zone"],
            line_width=0,
            layer="below",
        )

    ticks = list(range(0, 97, 8))
    labels = [
        f"{hour:02d}:00"
        for hour in range(0, 24, 2)
    ] + ["24:00"]

    fig.update_layout(
        title=title,
        height=340 if compact else 520,
        xaxis=dict(
            title="Heure",
            range=[0, 96],
            tickmode="array",
            tickvals=ticks,
            ticktext=labels,
        ),
        yaxis=dict(
            title="Puissance (kW)",
            rangemode="tozero",
        ),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            y=1.12,
            x=0.68,
        ),
        margin=dict(l=45, r=20, t=70, b=45),
    )
    return fig

