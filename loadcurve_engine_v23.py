from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np
import pandas as pd
from loadcurve_profiles import residential_day, add_block

ENGINE_VERSION = "2.3.0-saisie-annuelle-ou-mensuelle"


@dataclass
class TariffPeriod:
    start: float
    end: float


@dataclass
class Config:
    year: int
    annual_ht_kwh: float
    annual_bt_kwh: float
    price_ht: float
    price_bt: float
    resale_price: float
    ht_periods: List[TariffPeriod]
    ht_weekdays_only: bool
    occupants: int
    absent_people: int
    departure: float
    return_home: float
    wake: float
    bedtime: float
    dinner: float
    lunch_at_home: bool
    weekend_factor: float
    base_kw: float
    heat_pump: bool
    direct_heating: bool
    boiler: bool
    boiler_start: float
    boiler_kwh_day: float
    ev: bool
    ev_start: float
    ev_kwh_day: float
    ev_power_kw: float
    ev_weekdays_only: bool
    variability_pct: float
    input_mode: str = "annual"
    monthly_ht_kwh: list[float] | None = None
    monthly_bt_kwh: list[float] | None = None
    random_seed: int = 42


def _in_period(hour: float, start: float, end: float) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def tariff_mask(index: pd.DatetimeIndex, cfg: Config) -> np.ndarray:
    hours = index.hour.to_numpy() + index.minute.to_numpy() / 60
    mask = np.zeros(len(index), dtype=bool)
    for period in cfg.ht_periods:
        mask |= np.array([_in_period(h, period.start, period.end) for h in hours])
    if cfg.ht_weekdays_only:
        mask &= index.weekday.to_numpy() < 5
    return mask


def generate(cfg: Config) -> pd.DataFrame:
    if cfg.annual_ht_kwh < 0 or cfg.annual_bt_kwh < 0:
        raise ValueError("Les consommations HT et BT doivent être positives.")
    if cfg.annual_ht_kwh + cfg.annual_bt_kwh <= 0:
        raise ValueError("La consommation totale doit être supérieure à zéro.")
    if cfg.return_home <= cfg.departure:
        raise ValueError("L'heure de retour doit être après l'heure de départ.")

    index = pd.date_range(
        f"{cfg.year}-01-01 00:00",
        f"{cfg.year + 1}-01-01 00:00",
        freq="15min",
        inclusive="left",
    )

    weekday = residential_day(
        cfg.occupants, cfg.absent_people, cfg.departure, cfg.return_home,
        cfg.wake, cfg.bedtime, cfg.dinner, cfg.lunch_at_home, False, cfg.base_kw
    )
    weekend = residential_day(
        cfg.occupants, 0, cfg.departure, cfg.return_home,
        min(cfg.wake + 1, 10), min(cfg.bedtime + 0.5, 24),
        cfg.dinner, True, True, cfg.base_kw
    ) * cfg.weekend_factor

    if cfg.boiler:
        weekday = add_block(weekday, cfg.boiler_start, cfg.boiler_kwh_day, 2.0)
        weekend = add_block(weekend, cfg.boiler_start, cfg.boiler_kwh_day, 2.0)

    if cfg.ev:
        weekday = add_block(weekday, cfg.ev_start, cfg.ev_kwh_day, cfg.ev_power_kw)
        if not cfg.ev_weekdays_only:
            weekend = add_block(weekend, cfg.ev_start, cfg.ev_kwh_day, cfg.ev_power_kw)

    rng = np.random.default_rng(cfg.random_seed)
    power = np.zeros(len(index))
    normalized_days = index.normalize()
    for day in pd.DatetimeIndex(normalized_days.unique()):
        mask = normalized_days == day
        template = weekday if day.weekday() < 5 else weekend
        daily = rng.normal(1.0, cfg.variability_pct / 100)
        intra = rng.normal(1.0, cfg.variability_pct / 220, 96)
        power[mask] = np.clip(template * daily * intra, 0.01, None)

    # Saisonnalité mensuelle explicite.
    # Les coefficients suivent une forme en U : consommation élevée en hiver,
    # faible en été, comme sur le profil de référence fourni.
    month_weights_heat_pump = {
        1: 1.42,
        2: 1.28,
        3: 1.12,
        4: 0.92,
        5: 0.82,
        6: 0.68,
        7: 0.60,
        8: 0.68,
        9: 0.82,
        10: 1.02,
        11: 1.26,
        12: 1.50,
    }

    month_weights_direct_heating = {
        1: 1.58,
        2: 1.38,
        3: 1.16,
        4: 0.86,
        5: 0.72,
        6: 0.54,
        7: 0.48,
        8: 0.54,
        9: 0.70,
        10: 1.00,
        11: 1.34,
        12: 1.70,
    }

    if cfg.heat_pump or cfg.direct_heating:
        selected_weights = (
            month_weights_direct_heating
            if cfg.direct_heating
            else month_weights_heat_pump
        )

        monthly_factor = np.array(
            [selected_weights[int(month)] for month in index.month],
            dtype=float,
        )

        # On applique la saisonnalité principalement à la partie variable
        # de la charge, tout en conservant une charge de base stable.
        stable_base = np.minimum(power, max(cfg.base_kw, 0.05))
        variable_load = np.maximum(power - stable_base, 0.0)

        hour = index.hour.to_numpy() + index.minute.to_numpy() / 60.0
        occupied_factor = np.where(
            ((hour >= cfg.wake) & (hour <= cfg.departure))
            | ((hour >= cfg.return_home) & (hour <= cfg.bedtime)),
            1.0,
            0.72,
        )

        heating_share = 0.46 if cfg.direct_heating else 0.34
        seasonal_multiplier = (
            1.0
            + heating_share
            * occupied_factor
            * (monthly_factor - 1.0)
        )

        power = stable_base + variable_load * seasonal_multiplier

        # Ajout d'une charge spécifique au chauffage pour mieux marquer
        # les mois froids, sans créer de pics artificiels.
        heating_base = max(float(np.mean(power)), 0.1)
        heating_extra = (
            heating_base
            * (0.34 if cfg.direct_heating else 0.22)
            * np.maximum(monthly_factor - 0.60, 0.0)
            * occupied_factor
        )
        power += heating_extra

    ht = tariff_mask(index, cfg)
    base_energy = np.clip(power * 0.25, 1e-9, None)

    if cfg.annual_ht_kwh > 0 and not np.any(ht):
        raise ValueError("Aucune plage haut tarif n'est définie.")
    if cfg.annual_bt_kwh > 0 and not np.any(~ht):
        raise ValueError("Aucune plage bas tarif n'est disponible.")

    total_annual_target = cfg.annual_ht_kwh + cfg.annual_bt_kwh

    if cfg.input_mode == "monthly":
        if cfg.monthly_ht_kwh is None or cfg.monthly_bt_kwh is None:
            raise ValueError("Les consommations mensuelles HT et BT sont requises.")
        if len(cfg.monthly_ht_kwh) != 12 or len(cfg.monthly_bt_kwh) != 12:
            raise ValueError("Il faut renseigner exactement 12 mois.")

        monthly_ht_targets = np.array(cfg.monthly_ht_kwh, dtype=float)
        monthly_bt_targets = np.array(cfg.monthly_bt_kwh, dtype=float)
        if np.any(monthly_ht_targets < 0) or np.any(monthly_bt_targets < 0):
            raise ValueError("Les consommations mensuelles ne peuvent pas être négatives.")

        cfg.annual_ht_kwh = float(monthly_ht_targets.sum())
        cfg.annual_bt_kwh = float(monthly_bt_targets.sum())
        total_annual_target = cfg.annual_ht_kwh + cfg.annual_bt_kwh
        monthly_targets = monthly_ht_targets + monthly_bt_targets
        target_matrix = np.column_stack([monthly_bt_targets, monthly_ht_targets])
    else:
        if cfg.direct_heating:
            monthly_weights = np.array([14.2,12.3,10.1,7.8,6.5,5.0,4.3,5.0,6.6,9.1,11.8,15.1], dtype=float)
        elif cfg.heat_pump:
            monthly_weights = np.array([13.2,11.7,9.8,7.8,6.9,5.5,4.8,5.5,6.9,8.9,10.9,14.1], dtype=float)
        else:
            monthly_weights = np.array([12.0,10.8,9.4,8.0,7.3,6.2,5.5,6.1,7.2,8.8,10.3,12.4], dtype=float)
        monthly_weights = monthly_weights / monthly_weights.sum()
        monthly_targets = total_annual_target * monthly_weights

    # Matrice brute 12 mois x 2 tarifs (BT, HT).
    raw_matrix = np.zeros((12, 2), dtype=float)
    months = index.month.to_numpy()

    for month_num in range(1, 13):
        month_mask = months == month_num
        raw_matrix[month_num - 1, 0] = float(
            base_energy[month_mask & (~ht)].sum()
        )
        raw_matrix[month_num - 1, 1] = float(
            base_energy[month_mask & ht].sum()
        )

    # Évite les cellules nulles qui empêcheraient l'équilibrage.
    raw_matrix = np.maximum(raw_matrix, 1e-12)

    if cfg.input_mode != "monthly":
        column_targets = np.array([cfg.annual_bt_kwh, cfg.annual_ht_kwh], dtype=float)
        target_matrix = raw_matrix.copy()
        for _ in range(500):
            row_sums = target_matrix.sum(axis=1)
            target_matrix *= (monthly_targets / np.maximum(row_sums, 1e-12))[:, None]
            col_sums = target_matrix.sum(axis=0)
            target_matrix *= (column_targets / np.maximum(col_sums, 1e-12))[None, :]
            row_error = np.max(np.abs(target_matrix.sum(axis=1) - monthly_targets))
            col_error = np.max(np.abs(target_matrix.sum(axis=0) - column_targets))
            if row_error < 1e-8 and col_error < 1e-8:
                break

    # Application des facteurs à chaque cellule mois/tarif.
    energy = base_energy.copy()

    for month_num in range(1, 13):
        month_mask = months == month_num

        bt_cell = month_mask & (~ht)
        ht_cell = month_mask & ht

        raw_bt_cell = float(base_energy[bt_cell].sum())
        raw_ht_cell = float(base_energy[ht_cell].sum())

        if raw_bt_cell > 0:
            energy[bt_cell] *= (
                target_matrix[month_num - 1, 0] / raw_bt_cell
            )
        if raw_ht_cell > 0:
            energy[ht_cell] *= (
                target_matrix[month_num - 1, 1] / raw_ht_cell
            )

    power = energy / 0.25

    tariff = np.where(ht, "HT", "BT")
    price = np.where(ht, cfg.price_ht, cfg.price_bt)

    df = pd.DataFrame({
        "DateHeure": index,
        "Tarif": tariff,
        "Puissance_kW": power,
        "Consommation_kWh": energy,
        "Prix_CHF_kWh": price,
        "Cout_CHF": energy * price,
    })
    df["Date"] = df["DateHeure"].dt.date
    df["Heure"] = df["DateHeure"].dt.strftime("%H:%M")
    df["Mois"] = df["DateHeure"].dt.month
    df["TypeJour"] = np.where(df["DateHeure"].dt.weekday < 5, "Semaine", "Week-end")
    return df.round({"Puissance_kW": 5, "Consommation_kWh": 5, "Cout_CHF": 5})


def typical_day(df: pd.DataFrame, day_type: str) -> pd.DataFrame:
    part = df[df["TypeJour"] == day_type].copy()
    out = part.groupby(["Heure", "Tarif"], as_index=False).agg(
        Puissance_kW=("Puissance_kW", "mean")
    )
    order = {f"{h:02d}:{m:02d}": h * 4 + m // 15 for h in range(24) for m in (0, 15, 30, 45)}
    out["Ordre"] = out["Heure"].map(order)
    return out.sort_values("Ordre")


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    p = df.pivot_table(index="Mois", columns="Tarif", values="Consommation_kWh", aggfunc="sum", fill_value=0)
    p = p.reset_index()
    if "HT" not in p: p["HT"] = 0.0
    if "BT" not in p: p["BT"] = 0.0
    names = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    p["Mois_nom"] = [names[i-1] for i in p["Mois"]]
    p["Total"] = p["HT"] + p["BT"]
    return p
