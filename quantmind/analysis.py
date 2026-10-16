"""Single analysis snapshot consumed by UI, charts, and Markdown reports."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import calculate_indicators
from .instruments import ETF_NAMES
from .quality import validate_bars, range_warnings

METRIC_LABELS = {
    "close": "最新收盘价（元）", "period_return": "区间价格收益率", "return20": "20 日价格收益率",
    "volatility20": "20 日年化历史波动率", "max_drawdown": "区间最大回撤",
    "ma5": "MA5（元）", "ma20": "MA20（元）", "ma60": "MA60（元）", "rsi14": "RSI14",
    "dif": "DIF（元）", "dea": "DEA（元）", "macd": "MACD 柱状值（元）",
}
PERCENT_METRICS = {"period_return", "return20", "volatility20", "max_drawdown"}


def format_metric(key: str, value: float | None) -> str:
    if value is None or pd.isna(value):
        return "样本不足"
    return f"{value:.2%}" if key in PERCENT_METRICS else f"{value:.4f}"


@dataclass
class Analysis:
    symbol: str
    name: str
    start: str
    end: str
    frame: pd.DataFrame
    metrics: dict[str, float | None]
    metadata: dict
    warnings: list[str]
    prehistory_count: int


def analyze(symbol: str, history: pd.DataFrame, start: str, end: str,
            metadata: dict, warnings: list[str] | None = None) -> Analysis:
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("开始日期不能晚于结束日期。")
    quality = validate_bars(history)
    if not quality.valid:
        raise ValueError("行情存在严重异常，已停止分析：" + "；".join(quality.errors))
    # Guard against look-ahead: no observation after selected end enters any indicator.
    history = history.loc[history["date"] <= pd.Timestamp(end)].copy()
    calculated = calculate_indicators(history)
    selected = calculated.loc[calculated["date"].between(pd.Timestamp(start), pd.Timestamp(end))].copy()
    if selected.empty:
        raise ValueError("所选区间没有真实行情。请检查日期、上市时间或数据源覆盖范围。")
    selected["drawdown"] = selected["close"] / selected["close"].cummax() - 1
    latest = selected.iloc[-1]
    metrics = {k: (None if pd.isna(latest[k]) else float(latest[k]))
               for k in METRIC_LABELS if k not in {"period_return", "max_drawdown"}}
    metrics["period_return"] = float(selected["close"].iloc[-1] / selected["close"].iloc[0] - 1) if len(selected) >= 2 else None
    metrics["max_drawdown"] = float(selected["drawdown"].min()) if len(selected) >= 2 else None
    issues = list(warnings or []) + list(quality.warnings) + range_warnings(selected, start, end)
    count = int((history["date"] < pd.Timestamp(start)).sum())
    if count < 250:
        issues.append(f"前置历史仅 {count} 条（目标至少 250 条）；EMA/RSI 受初始化影响，完整窗口不足处标为样本不足。")
    unavailable = [METRIC_LABELS[k] for k, v in metrics.items() if v is None]
    if unavailable:
        issues.append("样本不足：" + "、".join(unavailable) + "。")
    issues.append("采用不复权价格；现金分红、拆分等事件可能产生价格缺口并影响指标，收益不含现金分红，不是总收益率。")
    return Analysis(symbol, ETF_NAMES[symbol], start, end, selected.reset_index(drop=True), metrics,
                    metadata.copy(), list(dict.fromkeys(issues)), count)
