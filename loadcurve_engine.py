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

    if cfg.heat_pump or cfg.direct_heating:
        doy = index.dayofyear.to_numpy()
        cold = (1 + np.cos(2 * np.pi * (doy - 15) / 365.25)) / 2
        hour = index.hour.to_numpy() + index.minute.to_numpy() / 60
        occupied = np.where(
            ((hour >= cfg.wake) & (hour <= cfg.departure))
            | ((hour >= cfg.return_home) & (hour <= cfg.bedtime)),
            1.0, 0.55
        )
        strength = 0.38 if cfg.direct_heating else 0.22
        power += max(power.mean(), 0.1) * strength * cold * occupied

    ht = tariff_mask(index, cfg)
    energy = power * 0.25
    raw_ht = energy[ht].sum()
    raw_bt = energy[~ht].sum()

    if cfg.annual_ht_kwh > 0 and raw_ht <= 0:
        raise ValueError("Aucune plage haut tarif n'est définie.")
    if cfg.annual_bt_kwh > 0 and raw_bt <= 0:
        raise ValueError("Aucune plage bas tarif n'est disponible.")

    energy[ht] *= cfg.annual_ht_kwh / raw_ht if raw_ht else 0
    energy[~ht] *= cfg.annual_bt_kwh / raw_bt if raw_bt else 0
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
