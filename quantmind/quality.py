"""Canonical daily bars: preserve missing data and reject invalid observations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close"]
CALENDAR_LIMITATION = "未接入可靠交易日历；仅按自然日提示范围和新鲜度，周末、节假日不直接认定为缺失，未严格验证交易日完整性。"


@dataclass(frozen=True)
class QualityResult:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Parse, sort, and coerce; never fill, drop duplicates, or repair OHLC."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    aliases = {"日期": "date", "交易日期": "date", "开盘": "open", "最高": "high",
               "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount"}
    renamed = frame.rename(columns=aliases).copy()
    if renamed.columns.duplicated().any():
        raise ValueError("存在重复字段名称，无法确定行情口径。")
    missing = [c for c in REQUIRED_COLUMNS if c not in renamed]
    if missing:
        raise ValueError("缺少行情字段：" + ", ".join(missing))
    cols = REQUIRED_COLUMNS + (["amount"] if "amount" in renamed else [])
    out = renamed[cols].copy()
    # Numeric date values are ambiguous (nanoseconds vs YYYYMMDD): reject explicitly.
    out["date"] = out["date"].map(lambda x: None if isinstance(x, (int, float, np.number)) else x)
    out["date"] = pd.to_datetime(out["date"], errors="coerce", format="mixed")
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out["date"] = out["date"].dt.normalize()
    for col in cols[1:]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values("date", kind="stable").reset_index(drop=True)


def validate_bars(frame: pd.DataFrame, *, today: date | None = None) -> QualityResult:
    errors, warnings = [], []
    reference = today or date.today()
    if frame is None or frame.empty:
        return QualityResult(False, ("没有可用行情数据。",))
    missing = [c for c in REQUIRED_COLUMNS if c not in frame]
    if missing:
        return QualityResult(False, ("缺少必需字段：" + ", ".join(missing),))
    if not pd.api.types.is_datetime64_any_dtype(frame["date"]):
        errors.append("交易日期必须先解析为标准日期。")
    else:
        if frame["date"].isna().any():
            errors.append("存在无法解析或缺失的交易日期。")
        if frame["date"].duplicated().any():
            errors.append("存在重复交易日期；请核查数据源，未自动删除。")
        if not frame["date"].is_monotonic_increasing:
            errors.append("交易日期未按升序排列。")
        if (frame["date"] > pd.Timestamp(reference)).any():
            errors.append("行情日期晚于当前日期。")
    numeric_ok = True
    for col in PRICE_COLUMNS + ["volume"] + (["amount"] if "amount" in frame else []):
        values = pd.to_numeric(frame[col], errors="coerce")
        if not pd.api.types.is_numeric_dtype(frame[col]) or not np.isfinite(values.to_numpy(dtype=float)).all():
            errors.append(f"{col} 存在缺失、非数值或非有限数值。")
            numeric_ok = False
    if numeric_ok:
        if (frame[PRICE_COLUMNS] <= 0).any().any():
            errors.append("OHLC 价格必须为正数。")
        if (frame["volume"] < 0).any() or ("amount" in frame and (frame["amount"] < 0).any()):
            errors.append("成交量、成交额必须非负。")
        if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) |
                (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).any():
            errors.append("OHLC 关系异常：最高价应覆盖开收盘及最低价，最低价应不高于其余价格。")
        if (frame["volume"] == 0).any():
            warnings.append("存在零成交量记录，可能停牌或无成交；未填充或删除。")
    if "amount" not in frame:
        warnings.append("该数据源未提供成交额；显示为未提供，不作估算。")
    for issue in errors:
        logger.error("行情校验失败：%s", issue)
    for issue in warnings:
        logger.warning("行情校验提示：%s", issue)
    return QualityResult(not errors, tuple(errors), tuple(warnings))


def range_warnings(frame: pd.DataFrame, start: str, end: str, *, today: date | None = None) -> list[str]:
    """Heuristics only: no weekday-based invented exchange calendar."""
    if frame.empty:
        return ["查询区间内没有真实行情，可能为休市、上市前或数据源未覆盖。", CALENDAR_LIMITATION]
    first, last = frame["date"].min(), frame["date"].max()
    reference = min(pd.Timestamp(end), pd.Timestamp(today or date.today()))
    warnings = [CALENDAR_LIMITATION]
    warnings.append(f"实际覆盖 {first.date()} 至 {last.date()}，共 {len(frame)} 条日线。")
    if (first - pd.Timestamp(start)).days > 10:
        warnings.append("区间起点超过 10 个自然日没有返回行情；可能为上市前、长假或覆盖不足，不能确认完整。")
    age = (reference - last).days
    if age > 10:
        warnings.append(f"数据可能陈旧或覆盖不足：截至所选结束日期相差 {age} 个自然日。")
    gaps = frame["date"].diff().dt.days
    if (gaps > 10).any():
        warnings.append("存在超过 10 个自然日的行情间隔；可能为长假、停牌或缺口，不能仅据此判定缺失；查询时会尝试整段补取，未插值。")
    return warnings
