from datetime import date
import sqlite3

import numpy as np
import pandas as pd
import pytest

from quantmind.quality import normalize_bars, validate_bars, range_warnings
from quantmind.storage import SQLiteBarStore


def test_parse_and_sort_without_filling(make_bars):
    f = make_bars(count=3).iloc[::-1].astype({"close": str})
    clean = normalize_bars(f.rename(columns={"date": "日期", "close": "收盘"}))
    assert clean.date.is_monotonic_increasing
    assert clean.close.tolist() == [1, 2, 3]
    assert validate_bars(clean).valid


@pytest.mark.parametrize("column,value,fragment", [
    ("date", "bad-date", "交易日期"), ("close", None, "缺失"), ("open", "bad-number", "非数值"),
    ("close", np.inf, "非有限"), ("open", 0, "正数"), ("volume", -1, "非负"),
    ("amount", -1, "非负"), ("high", .1, "OHLC"), ("low", 10, "OHLC"),
])
def test_reject_bad_rows(make_bars, column, value, fragment):
    f = make_bars(count=3).astype(object)
    f.loc[0, column] = value
    result = validate_bars(normalize_bars(f))
    assert not result.valid
    assert fragment in " ".join(result.errors)


def test_missing_column_duplicates_and_future(make_bars):
    f = make_bars(count=3)
    with pytest.raises(ValueError, match="缺少"):
        normalize_bars(f.drop(columns="open"))
    assert not validate_bars(pd.concat([f, f.iloc[[0]]])).valid
    assert not validate_bars(f, today=date(2022, 1, 1)).valid


def test_optional_amount_zero_volume_and_weekend(make_bars):
    f = make_bars(count=2, start="2023-01-06", amount=False)  # Friday + Monday
    f.loc[0, "volume"] = 0
    result = validate_bars(f)
    assert result.valid
    assert "未提供" in " ".join(result.warnings)
    warnings = range_warnings(f, "2023-01-06", "2023-01-09")
    assert not any("覆盖不足" in w for w in warnings)
    assert any("未严格验证" in w for w in warnings)
    assert any("可能陈旧" in w for w in range_warnings(f, "2023-01-06", "2023-02-01"))


def test_sqlite_update_and_source_adjustment_isolation(tmp_path, make_bars, metadata):
    store = SQLiteBarStore(tmp_path / "test.sqlite3")
    f = make_bars(count=3)
    store.save_batch("000001", f, metadata, "2023-01-01", "2023-01-06")
    changed = f.copy()
    changed.loc[0, ["open", "high", "low", "close"]] = [9, 10, 8, 9]
    store.save_batch("000001", changed, metadata | {"fetched_at": "2026-10-16T09:00:00+08:00"}, "2023-01-01", "2023-01-06")
    store.save_batch("000001", f, metadata | {"source": "TEST / 第二来源"}, "2023-01-01", "2023-01-06")
    store.save_batch("000001", f, metadata | {"adjustment": "qfq", "full_snapshot": True}, "2023-01-01", "2023-01-06")
    got, meta = store.read("000001", "2023-01-01", "2023-01-06", metadata["source"])
    assert len(got) == 3 and got.close.iloc[0] == 9
    assert meta["fetched_at_min"].endswith("09:00:00+08:00")
    qfq, _ = store.read("000001", "2023-01-01", "2023-01-06", metadata["source"], "qfq")
    other, _ = store.read("000001", "2023-01-01", "2023-01-06", "TEST / 第二来源")
    assert qfq.close.iloc[0] == other.close.iloc[0] == 1
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 9
        assert conn.execute("SELECT DISTINCT symbol FROM daily_bars").fetchone()[0] == "000001"


def test_reject_invalid_batch_and_adjusted_partial_snapshot(tmp_path, make_bars, metadata):
    store = SQLiteBarStore(tmp_path / "test.sqlite3")
    f = make_bars(count=3)
    with pytest.raises(ValueError, match="整段"):
        store.save_batch("510300", f, metadata | {"adjustment": "qfq"}, "2023-01-01", "2023-01-06")
    with pytest.raises(ValueError, match="重复"):
        store.save_batch("510300", pd.concat([f, f.iloc[[0]]]), metadata, "2023-01-01", "2023-01-06")
    with pytest.raises(ValueError, match="字符串"):
        store.save_batch(510300, f, metadata, "2023-01-01", "2023-01-06")


def test_range_replacement_removes_deleted_upstream_rows(tmp_path, make_bars, metadata):
    store = SQLiteBarStore(tmp_path / "test.sqlite3")
    f = make_bars(count=3)
    store.save_batch("510300", f, metadata, "2023-01-01", "2023-01-06")
    store.save_batch("510300", f.iloc[:2], metadata, "2023-01-01", "2023-01-06")
    got, _ = store.read("510300", "2023-01-01", "2023-01-06", metadata["source"])
    assert len(got) == 2


def test_actual_coverage_and_deleted_cache_gap(tmp_path, make_bars, metadata):
    store = SQLiteBarStore(tmp_path / "test.sqlite3")
    f = make_bars(count=20)
    store.save_batch("510300", f, metadata, "2023-01-01", "2023-01-31")
    assert store.covered("510300", "2023-01-01", "2023-01-31", metadata["source"])
    assert not store.covered("510300", "2023-01-01", "2023-03-31", metadata["source"])
    with sqlite3.connect(store.path) as conn:
        conn.execute("DELETE FROM daily_bars WHERE date='2023-01-10'")
    assert not store.covered("510300", "2023-01-01", "2023-01-31", metadata["source"])


def test_adjusted_refresh_replaces_all_previous_batches(tmp_path, make_bars, metadata):
    store = SQLiteBarStore(tmp_path / "adjusted.sqlite3")
    full = make_bars(count=5)
    qmeta = metadata | {"adjustment": "qfq", "full_snapshot": True}
    store.save_batch("510300", full, qmeta, "2023-01-01", "2023-01-09")
    # New complete provider snapshot is shorter; old adjusted dates must disappear.
    newer = full.iloc[2:].copy()
    store.save_batch("510300", newer, qmeta | {"fetched_at": "2026-10-16T10:00:00+08:00"}, "2023-01-04", "2023-01-09")
    got, _ = store.read("510300", "2023-01-01", "2023-01-09", metadata["source"], "qfq")
    assert got.date.tolist() == newer.date.tolist()
