from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np
import pandas as pd
from loadcurve_profiles import residential_day, add_block


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

    raw_ht = float(base_energy[ht].sum())
    raw_bt = float(base_energy[~ht].sum())

    if cfg.annual_ht_kwh > 0 and raw_ht <= 0:
        raise ValueError("Aucune plage haut tarif n'est définie.")
    if cfg.annual_bt_kwh > 0 and raw_bt <= 0:
        raise ValueError("Aucune plage bas tarif n'est disponible.")

    def smooth_binary_mask(mask: np.ndarray, radius: int = 6) -> np.ndarray:
        """
        Transforme le masque HT/BT en poids progressifs autour des changements de tarif.
        radius=6 correspond à une transition d'environ 1 h 30.
        """
        weights = mask.astype(float)
        if radius <= 0:
            return weights

        kernel_x = np.arange(-radius, radius + 1, dtype=float)
        sigma = max(radius / 2.2, 1.0)
        kernel = np.exp(-0.5 * (kernel_x / sigma) ** 2)
        kernel /= kernel.sum()

        # Lissage circulaire par journée afin de garder la continuité autour de minuit.
        out = np.zeros_like(weights)
        day_count = len(weights) // 96
        for day_idx in range(day_count):
            start = day_idx * 96
            end = start + 96
            day = weights[start:end]
            padded = np.concatenate([day[-radius:], day, day[:radius]])
            smoothed = np.convolve(padded, kernel, mode="same")[radius:-radius]
            out[start:end] = smoothed
        return np.clip(out, 0.0, 1.0)

    ht_weight = smooth_binary_mask(ht, radius=6)
    bt_weight = 1.0 - ht_weight

    # On cherche deux facteurs globaux a et b tels que :
    # somme(base * correction * HT_mask) = cible HT
    # somme(base * correction * BT_mask) = cible BT
    # avec correction = a*poids_HT + b*poids_BT.
    a11 = float((base_energy * ht_weight * ht).sum())
    a12 = float((base_energy * bt_weight * ht).sum())
    a21 = float((base_energy * ht_weight * (~ht)).sum())
    a22 = float((base_energy * bt_weight * (~ht)).sum())

    matrix = np.array([[a11, a12], [a21, a22]], dtype=float)
    targets = np.array([cfg.annual_ht_kwh, cfg.annual_bt_kwh], dtype=float)

    try:
        factors = np.linalg.solve(matrix, targets)
    except np.linalg.LinAlgError:
        factors = np.array([
            cfg.annual_ht_kwh / raw_ht if raw_ht else 0.0,
            cfg.annual_bt_kwh / raw_bt if raw_bt else 0.0,
        ])

    factor_ht, factor_bt = np.clip(factors, 0.0, None)
    correction = factor_ht * ht_weight + factor_bt * bt_weight
    energy = base_energy * correction

    # Correction finale très légère pour garantir exactement les deux totaux,
    # sans recréer de rupture visible : on répartit l'écart proportionnellement
    # à l'énergie déjà présente dans chaque zone tarifaire.
    current_ht = float(energy[ht].sum())
    current_bt = float(energy[~ht].sum())

    if current_ht > 0:
        energy[ht] *= cfg.annual_ht_kwh / current_ht
    if current_bt > 0:
        energy[~ht] *= cfg.annual_bt_kwh / current_bt

    # Lissage local de la puissance autour des frontières tarifaires.
    power = energy / 0.25
    boundary = np.flatnonzero(np.r_[False, ht[1:] != ht[:-1]])

    for idx_boundary in boundary:
        left = max(0, idx_boundary - 4)
        right = min(len(power), idx_boundary + 5)
        if right - left < 3:
            continue

        start_value = power[left]
        end_value = power[right - 1]
        blend = np.linspace(start_value, end_value, right - left)
        original_sum_ht = float((power[left:right] * 0.25)[ht[left:right]].sum())
        original_sum_bt = float((power[left:right] * 0.25)[~ht[left:right]].sum())

        power[left:right] = 0.65 * power[left:right] + 0.35 * blend

        # Rééquilibrage local pour ne pas modifier la répartition tarifaire.
        local_energy = power[left:right] * 0.25
        local_ht = ht[left:right]

        new_ht = float(local_energy[local_ht].sum())
        new_bt = float(local_energy[~local_ht].sum())

        if new_ht > 0 and original_sum_ht > 0:
            local_energy[local_ht] *= original_sum_ht / new_ht
        if new_bt > 0 and original_sum_bt > 0:
            local_energy[~local_ht] *= original_sum_bt / new_bt

        power[left:right] = local_energy / 0.25

    energy = power * 0.25

    # Garantie finale stricte après lissage.
    final_ht = float(energy[ht].sum())
    final_bt = float(energy[~ht].sum())
    if final_ht > 0:
        energy[ht] *= cfg.annual_ht_kwh / final_ht
    if final_bt > 0:
        energy[~ht] *= cfg.annual_bt_kwh / final_bt
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
