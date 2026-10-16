"""Display-only formatting. Original observations and indicator values stay untouched."""
from dataclasses import dataclass
import math

import pandas as pd

UP = "#B55245"
DOWN = "#447D70"
TEXT = "#293C35"
MUTED = "#727A6F"
ACCENT = "#607F9B"
PAPER = "#FDFCF8"
GRID = "#E7E8DF"
GOLD = "#AC8648"
PLUM = "#9582A0"


@dataclass(frozen=True)
class QuantityUnit:
    name: str
    verified: bool


def quantity_unit(metadata: dict, field: str) -> QuantityUnit:
    """Only explicit, evidenced unit metadata permits physical-unit conversion.

    Older cache labels include inferences and conflicts; never promote them to verified units.
    An adapter can supply `<field>_unit_verified`, `<field>_unit_base`, and
    `<field>_unit_evidence` after checking an authoritative upstream definition.
    """
    base = metadata.get(f"{field}_unit_base")
    valid = base in ({"份", "股", "手"} if field == "volume" else {"元"})
    if metadata.get(f"{field}_unit_verified") is True and metadata.get(f"{field}_unit_evidence") and valid:
        return QuantityUnit(base, True)
    return QuantityUnit("原始单位", False)


def display_quantity(value: float | None, unit: QuantityUnit) -> str:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return "—"
    magnitude, suffix = (1e8, "亿") if abs(value) >= 1e8 else (1e4, "万") if abs(value) >= 1e4 else (1, "")
    number = f"{value / magnitude:,.2f}" if magnitude != 1 else f"{value:,.0f}"
    return f"{number}{suffix}{unit.name}" + ("（未核实）" if not unit.verified else "")


def quantity_scale(values: pd.Series, unit: QuantityUnit) -> tuple[float, str]:
    maximum = values.max() if not values.empty else 0
    scale, prefix = (1e8, "亿") if maximum >= 1e8 else (1e4, "万") if maximum >= 1e4 else (1, "")
    return scale, prefix + (unit.name if unit.verified else "原值")


def metric_color(key: str, value: float | None, previous_close: float | None = None) -> str:
    if value is None or pd.isna(value):
        return MUTED
    if key == "close" and previous_close is not None:
        return UP if value > previous_close else DOWN if value < previous_close else TEXT
    if key in {"return20", "period_return", "max_drawdown"}:
        return UP if value > 0 else DOWN if value < 0 else TEXT
    if key == "rsi14":
        return UP if value >= 70 else DOWN if value <= 30 else TEXT
    return TEXT
