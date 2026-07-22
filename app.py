from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from loadcurve_engine import Config, TariffPeriod, generate, typical_day, monthly
from loadcurve_export import to_csv, to_excel, to_png


st.set_page_config(page_title="Courbe de charge HT/BT", page_icon="⚡", layout="wide")

st.markdown("""
<style>
:root {
    color-scheme: dark;
}

/* Zone principale */
.stApp {
    background-color: #0e1117;
    color: #f3f4f6;
}

.block-container {
    padding-top: 1.1rem;
    padding-bottom: 2rem;
}

h1, h2, h3 {
    letter-spacing: -0.02em;
    color: #f8fafc;
}

/* Sidebar entièrement sombre */
section[data-testid="stSidebar"] {
    background-color: #111827 !important;
    border-right: 1px solid #263244;
}

section[data-testid="stSidebar"] > div {
    background-color: #111827 !important;
}

section[data-testid="stSidebar"] * {
    color: #f3f4f6;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    color: #e5e7eb;
}

/* Champs numériques et texte */
section[data-testid="stSidebar"] div[data-baseweb="input"] > div,
section[data-testid="stSidebar"] div[data-baseweb="base-input"],
section[data-testid="stSidebar"] input {
    background-color: #0b1220 !important;
    color: #ffffff !important;
    border-color: #374151 !important;
}

section[data-testid="stSidebar"] input::placeholder {
    color: #9ca3af !important;
}

/* Selectbox */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background-color: #0b1220 !important;
    color: #ffffff !important;
    border-color: #374151 !important;
}

section[data-testid="stSidebar"] div[data-baseweb="select"] svg {
    fill: #e5e7eb !important;
}

/* Boutons +/- des champs numériques */
section[data-testid="stSidebar"] button {
    color: #f3f4f6;
}

section[data-testid="stSidebar"] button[kind="secondary"] {
    background-color: #182234 !important;
    border-color: #374151 !important;
}

/* Sliders */
section[data-testid="stSidebar"] div[data-baseweb="slider"] div[role="slider"] {
    background-color: #ef4444 !important;
    border-color: #ef4444 !important;
}

section[data-testid="stSidebar"] div[data-baseweb="slider"] > div > div {
    color: #f3f4f6 !important;
}

/* Checkbox */
section[data-testid="stSidebar"] input[type="checkbox"] {
    accent-color: #ef4444;
}

/* Bouton principal */
section[data-testid="stSidebar"] button[kind="primary"] {
    background-color: #ef4444 !important;
    border-color: #ef4444 !important;
    color: #ffffff !important;
}

section[data-testid="stSidebar"] button[kind="primary"]:hover {
    background-color: #dc2626 !important;
    border-color: #dc2626 !important;
}

/* Cartes métriques adaptées au thème sombre */
div[data-testid="stMetric"] {
    border: 1px solid #374151;
    border-radius: 12px;
    padding: 14px;
    background-color: #151b26;
}

div[data-testid="stMetric"] label,
div[data-testid="stMetric"] div {
    color: #f3f4f6;
}

.metric-red div[data-testid="stMetric"] {
    border-color: #7f1d1d;
    background-color: #2a1518;
}

.metric-blue div[data-testid="stMetric"] {
    border-color: #1e3a8a;
    background-color: #111c35;
}

.metric-green div[data-testid="stMetric"] {
    border-color: #166534;
    background-color: #10251a;
}

.metric-purple div[data-testid="stMetric"] {
    border-color: #6b21a8;
    background-color: #24142f;
}

/* Boutons de téléchargement */
div[data-testid="stDownloadButton"] button {
    background-color: #151b26;
    color: #f3f4f6;
    border-color: #374151;
}

div[data-testid="stDownloadButton"] button:hover {
    border-color: #64748b;
    background-color: #1f2937;
}

/* Messages et séparateurs */
div[data-testid="stAlert"] {
    background-color: #151b26;
    color: #f3f4f6;
}

hr {
    border-color: #263244;
}
</style>
""", unsafe_allow_html=True)

st.title("Générateur de courbe de charge")
st.caption("Profil annuel théorique au pas de 15 minutes, calibré exactement sur les consommations haut tarif et bas tarif.")

with st.sidebar:
    st.header("1. Données tarifaires & consommation")
    annual_ht = st.number_input("Consommation annuelle haut tarif (kWh)", 0.0, value=16996.0, step=100.0)
    annual_bt = st.number_input("Consommation annuelle bas tarif (kWh)", 0.0, value=7871.0, step=100.0)
    price_ht = st.number_input("Prix du kWh haut tarif (CHF)", 0.0, value=0.31, step=0.01, format="%.3f")
    price_bt = st.number_input("Prix du kWh bas tarif (CHF)", 0.0, value=0.21, step=0.01, format="%.3f")
    resale = st.number_input("Prix de revente (CHF/kWh) — optionnel", 0.0, value=0.08, step=0.01, format="%.3f")

    st.subheader("Plages tarifaires")
    h1s = st.slider("Début HT 1", 0.0, 23.75, 7.0, 0.25)
    h1e = st.slider("Fin HT 1", 0.25, 24.0, 12.0, 0.25)
    second = st.checkbox("Ajouter une deuxième plage HT", True)
    h2s, h2e = 17.0, 23.0
    if second:
        h2s = st.slider("Début HT 2", 0.0, 23.75, 17.0, 0.25)
        h2e = st.slider("Fin HT 2", 0.25, 24.0, 23.0, 0.25)
    weekdays_only = st.selectbox(
        "Jours concernés par le haut tarif",
        ["Lundi à vendredi", "Tous les jours"],
        index=0,
    ) == "Lundi à vendredi"

    st.header("2. Occupation du bâtiment")
    occupants = st.number_input("Combien de personnes vivent dans le bâtiment ?", 1, 20, 4)
    absent = st.number_input("Combien sont absentes durant la journée ?", 0, int(occupants), min(3, int(occupants)))
    departure = st.slider("Heure habituelle de départ", 0.0, 23.75, 7.5, 0.25)
    return_home = st.slider("Heure habituelle de retour", 0.25, 24.0, 17.5, 0.25)

    st.header("3. Habitudes quotidiennes")
    wake = st.slider("Heure de lever", 0.0, 12.0, 6.5, 0.25)
    bedtime = st.slider("Heure de coucher", 18.0, 24.0, 22.5, 0.25)
    dinner = st.slider("Heure du repas du soir", 16.0, 22.0, 19.0, 0.25)
    lunch = st.checkbox("Repas de midi régulièrement à domicile", False)
    weekend_factor = st.slider("Activité le week-end (%)", 50, 160, 115, 5) / 100
    base_kw = st.number_input("Puissance de base estimée (kW)", 0.05, 5.0, 0.25, 0.05)

    st.header("4. Équipements électriques")
    heat_pump = st.checkbox("Pompe à chaleur")
    direct_heating = st.checkbox("Chauffage électrique direct")
    boiler = st.checkbox("Boiler électrique")
    boiler_start, boiler_kwh = 1.0, 4.0
    if boiler:
        boiler_start = st.slider("Début de chauffe du boiler", 0.0, 23.75, 1.0, 0.25)
        boiler_kwh = st.number_input("Consommation journalière du boiler (kWh)", 0.5, 30.0, 4.0, 0.5)

    ev = st.checkbox("Véhicule électrique")
    ev_start, ev_kwh, ev_power, ev_weekdays = 22.0, 8.0, 11.0, True
    if ev:
        ev_start = st.slider("Début de recharge", 0.0, 23.75, 22.0, 0.25)
        ev_kwh = st.number_input("Énergie moyenne rechargée par jour (kWh)", 1.0, 100.0, 8.0, 1.0)
        ev_power = st.selectbox("Puissance de recharge (kW)", [2.3, 3.7, 7.4, 11.0, 22.0], index=3)
        ev_weekdays = st.checkbox("Recharge principalement en semaine", True)

    st.header("5. Résumé & génération")
    variability = st.slider("Variabilité des journées (%)", 0, 25, 8)
    year = st.number_input("Année", 2020, 2050, 2026)
    generate_btn = st.button("Générer la courbe", type="primary", use_container_width=True)

if "generated" not in st.session_state:
    st.session_state.generated = False

if generate_btn:
    periods = [TariffPeriod(h1s, h1e)]
    if second:
        periods.append(TariffPeriod(h2s, h2e))
    cfg = Config(
        int(year), annual_ht, annual_bt, price_ht, price_bt, resale,
        periods, weekdays_only, int(occupants), int(absent), departure,
        return_home, wake, bedtime, dinner, lunch, weekend_factor, base_kw,
        heat_pump, direct_heating, boiler, boiler_start, boiler_kwh,
        ev, ev_start, ev_kwh, ev_power, ev_weekdays, variability
    )
    try:
        with st.spinner("Génération du profil annuel..."):
            annual = generate(cfg)
            week = typical_day(annual, "Semaine")
            weekend = typical_day(annual, "Week-end")
            month = monthly(annual)
        st.session_state.update({
            "generated": True, "annual": annual, "week": week,
            "weekend": weekend, "month": month, "year": int(year),
            "cfg": cfg
        })
    except Exception as exc:
        st.error(str(exc))

if not st.session_state.generated:
    st.info("Renseigne les paramètres dans la colonne de gauche, puis clique sur « Générer la courbe ».")
    st.stop()

annual = st.session_state.annual
week = st.session_state.week
weekend = st.session_state.weekend
month = st.session_state.month
cfg = st.session_state.cfg

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

st.plotly_chart(
    full_day_chart(week, "Journée type (semaine) — profil de consommation"),
    use_container_width=True
)

total_ht = annual.loc[annual.Tarif=="HT","Consommation_kWh"].sum()
total_bt = annual.loc[annual.Tarif=="BT","Consommation_kWh"].sum()
cost_ht = total_ht * cfg.price_ht
cost_bt = total_bt * cfg.price_bt
total = total_ht + total_bt
cost = cost_ht + cost_bt
peak = annual["Puissance_kW"].max()
mean = annual["Puissance_kW"].mean()
base = annual["Puissance_kW"].quantile(0.05)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="metric-red">', unsafe_allow_html=True)
    st.metric("Consommation haut tarif", f"{total_ht:,.0f} kWh/an".replace(","," "), f"{cost_ht:,.2f} CHF/an".replace(","," "))
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="metric-blue">', unsafe_allow_html=True)
    st.metric("Consommation bas tarif", f"{total_bt:,.0f} kWh/an".replace(","," "), f"{cost_bt:,.2f} CHF/an".replace(","," "))
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="metric-green">', unsafe_allow_html=True)
    st.metric("Consommation totale", f"{total:,.0f} kWh/an".replace(","," "), f"{cost:,.2f} CHF/an".replace(","," "))
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    st.markdown('<div class="metric-purple">', unsafe_allow_html=True)
    st.metric("Puissance maximale", f"{peak:.2f} kW", f"Moyenne {mean:.2f} kW — Base {base:.2f} kW")
    st.markdown('</div>', unsafe_allow_html=True)

a, b, c = st.columns([1,1,1])
with a:
    st.plotly_chart(full_day_chart(week, "Journée type — semaine", compact=True), use_container_width=True)
with b:
    st.plotly_chart(full_day_chart(weekend, "Journée type — week-end", compact=True), use_container_width=True)
with c:
    figm = go.Figure(go.Bar(x=month["Mois_nom"], y=month["Total"], marker_color="#2e9d47"))
    figm.update_layout(title="Répartition mensuelle (total)", height=340, yaxis_title="kWh", margin=dict(l=45,r=20,t=55,b=45))
    st.plotly_chart(figm, use_container_width=True)

st.subheader("Exporter les données")
x1, x2, x3 = st.columns(3)
x1.download_button("Télécharger Excel (.xlsx)", to_excel(annual, week, weekend, month),
                   f"courbe_charge_{st.session_state.year}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   use_container_width=True)
x2.download_button("Télécharger CSV (.csv)", to_csv(annual),
                   f"courbe_charge_{st.session_state.year}.csv",
                   "text/csv", use_container_width=True)
x3.download_button("Télécharger graphe (PNG)", to_png(week, "Journée type — semaine"),
                   "journee_type_semaine.png", "image/png", use_container_width=True)

st.caption("Pas de temps : 15 minutes — 35 040 points pour une année normale. Les valeurs HT et BT générées correspondent exactement aux consommations saisies.")
