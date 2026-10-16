"""Offline TEST samples: observed records include arbitrary gaps, never an exchange calendar."""
import numpy as np
import pandas as pd
import pytest

from quantmind.analysis import analyze, format_metric
from quantmind.charts import build_charts, date_gaps, record_axis
from quantmind.presentation import QuantityUnit, display_quantity, quantity_unit, quantity_scale, metric_color, UP, DOWN
from quantmind.report import generate_report


def test_record_categories_compress_weekend_long_gap_without_inventing_rows(make_bars, metadata):
    bars = make_bars(close=[10, 11, 10, 12, 13])
    bars["date"] = pd.to_datetime(["2025-09-26", "2025-09-29", "2025-09-30", "2025-10-08", "2025-10-09"])
    original = bars.copy(deep=True)
    result = analyze("510300", bars, "2025-09-26", "2025-10-09", metadata)
    frame_before = result.frame.copy(deep=True)
    figures = build_charts(result)
    expected = ["2025-09-26", "2025-09-29", "2025-09-30", "2025-10-08", "2025-10-09"]
    for fig in figures.values():
        assert fig.layout.xaxis.type == "category"
        assert list(fig.layout.xaxis.categoryarray) == expected
        for trace in fig.data:
            assert list(trace.x) == expected
            assert [row[0] for row in trace.customdata] == expected
            assert "%{customdata[0]}" in trace.hovertemplate
        assert fig.layout.xaxis.range == (-.5, 4.5)
    price = figures["price"]
    assert list(price.layout.xaxis2.categoryarray) == expected
    assert price.layout.xaxis.matches == "x2"  # Plotly shared horizontal coordinate
    assert any(shape.x0 == 2.5 and shape.x1 == 2.5 for shape in price.layout.shapes)
    assert list(price.data[0].close) == [10, 11, 10, 12, 13]
    pd.testing.assert_frame_equal(bars, original)
    pd.testing.assert_frame_equal(result.frame, frame_before)


def test_short_and_long_tick_labels_are_unique_and_auto_thinned():
    month = pd.Series(pd.to_datetime(["2026-09-15", "2026-09-18", "2026-10-08", "2026-10-15"]))
    axis = record_axis(month)
    assert axis["labelalias"]["2026-09-15"] == "09-15"
    assert axis["labelalias"]["2026-10-08"] == "10-08"
    assert axis["tickmode"] == "auto" and axis["nticks"] == 8
    # Auto ticks can be recalculated by Plotly on zoom instead of a static monthly tick array.
    assert "tickvals" not in axis and "dtick" not in axis
    years = record_axis(pd.Series(pd.bdate_range("2025-01-01", "2026-10-15")))
    assert len(set(years["labelalias"].values())) == len(years["categoryarray"])
    assert years["labelalias"]["2025-09-15"] != years["labelalias"]["2026-09-15"]


@pytest.mark.parametrize("dates", [[], ["2026-09-16", "2026-09-15"], ["2026-09-15", "2026-09-15"], ["bad"]])
def test_bad_date_mapping_is_rejected(dates):
    parsed = pd.Series(pd.to_datetime(dates, errors="coerce"))
    with pytest.raises(ValueError, match="绘图日期"):
        record_axis(parsed)


def test_date_gap_table_reports_elapsed_days_without_classifying_holidays():
    dates = pd.Series(pd.to_datetime(["2025-09-26", "2025-09-29", "2025-09-30", "2025-10-08"]))
    gaps = date_gaps(dates)
    assert gaps.to_dict("records") == [
        {"前一记录": "2025-09-26", "后一记录": "2025-09-29", "间隔自然日": 3},
        {"前一记录": "2025-09-30", "后一记录": "2025-10-08", "间隔自然日": 8},
    ]
    assert list(gaps.columns) == ["前一记录", "后一记录", "间隔自然日"]


@pytest.mark.parametrize("old_label", ["份（价量关系推断；官方文档标手存在冲突）", "手（100份；价量关系核验）", "元（人民币）", "份"])
def test_unverified_and_legacy_metadata_never_assumes_a_physical_unit(old_label):
    meta = {"volume_unit": old_label, "amount_unit": old_label, "unit_check_pass_fraction": 1.0}
    unit = quantity_unit(meta, "volume")
    assert not unit.verified and unit.name == "原始单位"
    text = display_quantity(123_456_789, unit)
    assert text == "1.23亿原始单位（未核实）"
    assert "份" not in text and "手" not in text and "元" not in text


def test_confirmed_quantity_scales_require_explicit_evidence():
    unit = quantity_unit({"volume_unit_verified": True, "volume_unit_base": "份", "volume_unit_evidence": "TEST authoritative field definition"}, "volume")
    assert display_quantity(123_450_000, unit) == "1.23亿份"
    assert display_quantity(12_345, unit) == "1.23万份"
    assert display_quantity(0, unit) == "0份"
    money = QuantityUnit("元", True)
    assert display_quantity(12_345, money) == "1.23万元"
    assert display_quantity(123_450_000, money) == "1.23亿元"
    assert not quantity_unit({"volume_unit_verified": True, "volume_unit_base": "份"}, "volume").verified
    assert not quantity_unit({"amount_unit_verified": True, "amount_unit_base": "份", "amount_unit_evidence": "TEST"}, "amount").verified
    assert display_quantity(None, money) == display_quantity(np.nan, money) == "—"


def test_scaled_chart_is_display_only_and_report_numbers_remain_equal(make_bars, metadata):
    bars = make_bars(count=100)
    bars["volume"] = 123_450_000.0
    result = analyze("510300", bars, "2023-03-01", "2023-05-19", metadata)
    before = result.frame.copy(deep=True)
    metrics_before = result.metrics.copy()
    volume = build_charts(result)["price"].data[-1]
    assert list(volume.y) == [1.2345] * len(before)
    assert "原始单位（未核实）" in volume.customdata[0][1]
    assert quantity_scale(before.volume, QuantityUnit("份", True)) == (1e8, "亿份")
    pd.testing.assert_frame_equal(before, result.frame)
    assert result.metrics == metrics_before
    report = generate_report(result)
    assert "成交量单位：原始单位（未核实；保留原始值）" in report
    for key, value in result.metrics.items():
        assert format_metric(key, value) in report


def test_up_down_colors_match_chart_convention():
    assert metric_color("close", 12, 11) == metric_color("return20", .1) == UP
    assert metric_color("close", 10, 11) == metric_color("max_drawdown", -.1) == DOWN
