from __future__ import annotations
import numpy as np


def gaussian(hours: np.ndarray, center: float, width: float, amplitude: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((hours - center) / max(width, 0.1)) ** 2)


def residential_day(
    occupants: int,
    absent_people: int,
    departure: float,
    return_home: float,
    wake: float,
    bedtime: float,
    dinner: float,
    lunch_at_home: bool,
    weekend: bool,
    base_kw: float,
) -> np.ndarray:
    hours = np.arange(96) / 4
    occupants = max(1, int(occupants))
    absent_people = min(max(0, int(absent_people)), occupants)
    present_ratio = (occupants - absent_people) / occupants

    load = np.full(96, max(base_kw, 0.05), dtype=float)

    load += gaussian(hours, wake + 0.45, 0.75, 0.22 + 0.18 * occupants)
    load += gaussian(hours, dinner, 1.15, 0.42 + 0.30 * occupants)
    load += gaussian(hours, dinner + 2.0, 1.40, 0.15 + 0.10 * occupants)

    day_mask = (hours >= 8) & (hours < 17)
    load[day_mask] += 0.05 + 0.10 * occupants

    if not weekend and absent_people:
        mask = (hours >= departure) & (hours < return_home)
        variable = np.maximum(load[mask] - base_kw, 0)
        load[mask] = base_kw + variable * (0.15 + 0.85 * present_ratio)

    if lunch_at_home or weekend:
        load += gaussian(hours, 12.2, 0.65, 0.10 + 0.09 * occupants)

    if weekend:
        load += gaussian(hours, 10.5, 2.0, 0.10 + 0.07 * occupants)
        load += gaussian(hours, 15.0, 2.2, 0.08 + 0.06 * occupants)
        load *= 1.08

    night = (hours >= bedtime) | (hours < max(wake - 1.5, 0))
    load[night] = np.maximum(base_kw, load[night] * 0.55)
    return np.clip(load, 0.02, None)


def add_block(load: np.ndarray, start_hour: float, energy_kwh: float, power_kw: float) -> np.ndarray:
    out = load.copy()
    if energy_kwh <= 0 or power_kw <= 0:
        return out
    steps = max(1, int(round((energy_kwh / power_kw) * 4)))
    start = int(round((start_hour % 24) * 4))
    for i in range(steps):
        out[(start + i) % 96] += power_kw
    return out
