import math

import numpy as np
import pandas as pd
import pytest

from quantmind.analysis import analyze, format_metric, METRIC_LABELS
from quantmind.charts import build_charts
from quantmind.indicators import calculate_indicators, rsi_wilder
from quantmind.report import generate_report


def test_ma_and_return_windows(make_bars):
    f = calculate_indicators(make_bars(count=60))
    assert f.ma5.iloc[:4].isna().all() and f.ma5.iloc[4] == 3
    assert f.ma20.iloc[19] == 10.5
    assert f.ma60.iloc[59] == 30.5
    assert f.return20.iloc[:20].isna().all()
    assert f.return20.iloc[20] == 20  # 21 / 1 - 1


@pytest.mark.parametrize("close,expected", [(list(range(1, 17)), 100), (list(range(20, 4, -1)), 0), ([5] * 16, 50)])
def test_rsi_edges(close, expected):
    rsi = rsi_wilder(pd.Series(close))
    assert rsi.iloc[:14].isna().all()
    assert rsi.iloc[14] == rsi.iloc[15] == expected


def test_wilder_seed_and_recursion_hand_example():
    close = [100]
    for change in [2, -1] * 7 + [-2]:
        close.append(close[-1] + change)
    rsi = rsi_wilder(pd.Series(close))
    assert rsi.iloc[14] == pytest.approx(200 / 3)  # 7 gains of 2, 7 losses of 1
    assert rsi.iloc[15] == pytest.approx(2600 / 43)  # G=13/14, L=8.5/14


def test_macd_closed_form_for_linear_prices(make_bars):
    f = calculate_indicators(make_bars(count=60))
    # Closed-form response of first-price seeded EMA to ramp p[t]=t+1.
    def closed_dif(t):
        return 7 - 12.5 * (25 / 27) ** t + 5.5 * (11 / 13) ** t
    assert f.dif.iloc[:25].isna().all()
    assert f.dif.iloc[25] == pytest.approx(closed_dif(25))
    assert f.dea.iloc[:33].isna().all()
    expected_dea33 = .8**8 * closed_dif(25) + .2 * sum(.8 ** (33 - t) * closed_dif(t) for t in range(26, 34))
    assert f.dea.iloc[33] == pytest.approx(expected_dea33)
    assert f.macd.iloc[33] == pytest.approx(2 * (closed_dif(33) - expected_dea33))


def test_volatility_sample_std_independent_formula(make_bars):
    # Ten returns +10%, ten returns -10%: mean zero; sum squares=.2.
    closes = 10 * np.cumprod(np.r_[1, [1.1, .9] * 10])
    f = calculate_indicators(make_bars(close=closes))
    expected = math.sqrt(.2 / 19) * math.sqrt(252)
    assert f.volatility20.iloc[20] == pytest.approx(expected)
    assert f.volatility20.iloc[:20].isna().all()


def test_drawdown_only_selected_range_and_report_consistency(make_bars, metadata):
    bars = make_bars(close=[100, 200, 100, 120, 90, 110])
    result = analyze("510300", bars, "2023-01-04", "2023-01-09", metadata)
    assert result.metrics["max_drawdown"] == pytest.approx(-.25)  # 90/120-1, not 90/200-1
    assert result.metrics["period_return"] == pytest.approx(.1)
    report = generate_report(result)
    for key, label in METRIC_LABELS.items():
        assert f"| {label} | {format_metric(key, result.metrics[key])} |" in report
    assert "-25.00%" in report and "10.00%" in report
    assert "样本不足" in report and "不含现金分红" in report and "非包含现金分红的总收益率" in report


def test_warmup_slice_no_future_leak(make_bars, metadata):
    bars = make_bars(count=300)
    begin, end = str(bars.date.iloc[270].date()), str(bars.date.iloc[280].date())
    r = analyze("510300", bars, begin, end, metadata)
    assert r.prehistory_count == 270
    assert r.frame.ma60.iloc[0] == 241.5  # mean 212..271
    assert r.metrics["close"] == 281
    assert r.metrics["return20"] == pytest.approx(281 / 261 - 1)
    assert r.metrics["max_drawdown"] == 0  # valid increasing interval
    assert r.frame.date.max() == pd.Timestamp(end)


def test_one_bar_is_insufficient_not_fake_zero(make_bars, metadata):
    r = analyze("510300", make_bars(count=1), "2023-01-02", "2023-01-02", metadata)
    for key in ["ma5", "return20", "volatility20", "max_drawdown", "rsi14", "macd", "period_return"]:
        assert r.metrics[key] is None
        assert format_metric(key, r.metrics[key]) == "样本不足"
    assert "样本不足" in generate_report(r)


def test_empty_and_bad_input_block_analysis(make_bars, metadata):
    f = make_bars(count=10)
    with pytest.raises(ValueError, match="没有真实行情"):
        analyze("510300", f, "2025-01-01", "2025-02-01", metadata)
    f.loc[0, "high"] = .01
    with pytest.raises(ValueError, match="严重异常"):
        analyze("510300", f, "2023-01-01", "2023-02-01", metadata)


def test_plotly_figures_serialize_and_share_result(make_bars, metadata):
    r = analyze("510300", make_bars(count=100), "2023-03-01", "2023-05-19", metadata)
    charts = build_charts(r)
    assert set(charts) == {"price", "rsi", "macd"}
    assert [len(f.data) for f in charts.values()] == [5, 1, 3]
    assert list(charts["price"].data[0].close) == r.frame.close.tolist()
    assert list(charts["rsi"].data[0].y) == r.frame.rsi14.tolist()
    assert all(len(f.to_json()) > 1000 for f in charts.values())
