"""Deterministic indicators; compute on warm history before slicing display dates."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Seed with the first `period` changes' arithmetic mean, then Wilder recursion.

    All gains -> 100; all losses -> 0; both zero -> 50. First value at index period.
    """
    result = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return result
    delta = close.astype(float).diff().to_numpy()
    gains, losses = np.maximum(delta, 0), np.maximum(-delta, 0)
    avg_gain, avg_loss = gains[1:period + 1].mean(), losses[1:period + 1].mean()
    for i in range(period, len(close)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_gain == 0 and avg_loss == 0:
            value = 50.0
        elif avg_loss == 0:
            value = 100.0
        else:
            value = 100 - 100 / (1 + avg_gain / avg_loss)
        result.iloc[i] = value
    return result


def calculate_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    close = out["close"].astype(float)
    for window in (5, 20, 60):
        out[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    out["rsi14"] = rsi_wilder(close)
    # EMA seed is first close; adjust=False gives recursive alpha=2/(span+1).
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    # Signal starts with the first valid DIF (the 26th close), then 9 observations.
    out["dif"] = dif.where(np.arange(len(close)) >= 25)
    out["dea"] = out["dif"].ewm(span=9, adjust=False, min_periods=9).mean()
    out["macd"] = 2 * (out["dif"] - out["dea"])
    returns = close.pct_change(fill_method=None)
    out["return20"] = close / close.shift(20) - 1
    out["volatility20"] = returns.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(252)
    return out
