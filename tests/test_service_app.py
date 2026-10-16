from datetime import date, timedelta
from pathlib import Path
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from quantmind.market_data import MarketDataError, MarketDataService
from quantmind.storage import SQLiteBarStore


class TestSource:
    """Artificial TEST adapter; never makes network calls."""
    __test__ = False
    name = "TEST / 人工构造样本"
    kind = "test"

    def __init__(self, bars, metadata):
        self.bars, self.meta, self.calls, self.error = bars, metadata, [], None

    def metadata(self):
        return self.meta.copy()

    def fetch(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.error:
            raise MarketDataError(self.error)
        return self.bars.loc[self.bars.date.between(pd.Timestamp(start), pd.Timestamp(end))].copy()


@pytest.fixture
def service_fixture(tmp_path, make_bars, metadata):
    bars = make_bars(count=530, start="2022-01-03")
    source = TestSource(bars, metadata)
    store = SQLiteBarStore(tmp_path / "test.sqlite3")
    return MarketDataService(store, [source]), source, store


def test_cache_hit_no_network_and_manual_refresh(service_fixture):
    service, source, store = service_fixture
    r = service.history("510300", "2024-01-01", "2024-01-15")
    assert "接口获取成功" in r.metadata["status"]
    cached = service.history("510300", "2024-01-01", "2024-01-15")
    assert len(source.calls) == 1
    assert "使用缓存" in cached.metadata["status"]
    source.bars.loc[source.bars.index[-1], "close"] -= .1
    refreshed = service.history("510300", "2024-01-01", "2024-01-15", refresh=True)
    assert len(source.calls) == 2
    assert refreshed.bars.close.iloc[-1] == pytest.approx(r.bars.close.iloc[-1] - .1)


def test_requested_gap_and_actual_truncation_retry(service_fixture):
    service, source, store = service_fixture
    service.history("510300", "2024-01-01", "2024-01-15")
    # Cache has no real data through March; retry rather than treating request as coverage.
    r = service.history("510300", "2024-01-01", "2024-03-15")
    assert len(source.calls) == 2
    assert r.bars.date.max() < pd.Timestamp("2024-03-01")
    assert any("可能陈旧" in w for w in r.warnings)
    service.history("510300", "2024-01-01", "2024-03-15")
    assert len(source.calls) == 3


def test_deleted_interior_row_retriggers_fetch(service_fixture):
    service, source, store = service_fixture
    r = service.history("510300", "2024-01-01", "2024-01-15")
    target = r.bars.date.iloc[100].strftime("%Y-%m-%d")
    with sqlite3.connect(store.path) as conn:
        conn.execute("DELETE FROM daily_bars WHERE date=?", (target,))
    updated = service.history("510300", "2024-01-01", "2024-01-15")
    assert len(source.calls) == 2
    assert len(updated.bars) == len(r.bars)


def test_network_failure_uses_valid_cache_with_reason(service_fixture):
    service, source, store = service_fixture
    service.history("510300", "2024-01-01", "2024-01-15")
    source.error = "TEST 人工断网"
    r = service.history("510300", "2024-01-01", "2024-01-15", refresh=True)
    assert r.metadata["status"] == "使用缓存（接口失败）"
    assert "TEST 人工断网" in r.metadata["failure_reason"]
    assert r.metadata["fetched_at_max"]
    assert any("使用缓存" in w for w in r.warnings)


def test_no_cache_failure_is_explicit_and_no_fake_data(service_fixture):
    service, source, store = service_fixture
    source.error = "TEST 接口失败"
    with pytest.raises(MarketDataError, match="无可用真实缓存"):
        service.history("510300", "2024-01-01", "2024-01-15")
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 0


def test_invalid_upstream_does_not_poison_cache(service_fixture):
    service, source, store = service_fixture
    original = service.history("510300", "2024-01-01", "2024-01-15")
    source.bars.loc[0, "high"] = .1
    result = service.history("510300", "2024-01-01", "2024-01-15", refresh=True)
    assert "使用缓存" in result.metadata["status"]
    assert "OHLC" in result.metadata["failure_reason"]
    pd.testing.assert_frame_equal(result.bars, original.bars, check_dtype=False)


def test_no_returned_rows_in_selected_interval_fails(service_fixture):
    service, source, store = service_fixture
    with pytest.raises(MarketDataError, match="未覆盖所选区间"):
        service.history("510300", "2024-06-01", "2024-06-03")


def test_secondary_source_cache_avoids_retrying_primary(service_fixture, metadata):
    service, secondary, store = service_fixture
    primary = TestSource(secondary.bars, metadata | {"source": "TEST / 不可用来源"})
    primary.name = "TEST / 不可用来源"
    primary.error = "TEST 主源不可用"
    service.sources = [primary, secondary]
    service.history("510300", "2024-01-01", "2024-01-15")
    r = service.history("510300", "2024-01-01", "2024-01-15")
    assert len(primary.calls) == 1 and len(secondary.calls) == 1
    assert r.metadata["source"] == secondary.name and "使用缓存" in r.metadata["status"]


def test_app_offline_query_and_report_no_runtime_errors(tmp_path, make_bars, metadata, monkeypatch):
    # Streamlit AppTest uses clearly labeled TEST source; browser validation uses real source separately.
    today = date.today()
    source = TestSource(make_bars(count=800, start=str(today - timedelta(days=1100))), metadata)
    original_init = MarketDataService.__init__
    def test_init(self, store, sources=None):
        original_init(self, store, [source])
    monkeypatch.setattr(MarketDataService, "__init__", test_init)
    monkeypatch.setenv("QUANTMIND_DB_PATH", str(tmp_path / "ui-test.sqlite3"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert not source.calls
    app.sidebar.button[0].click().run()
    assert not app.exception and not app.error
    assert len(app.metric) == 5
    assert len(app.get("component_instance")) == 1
    assert "TEST / 人工构造样本" in app.session_state["report"]
    assert "# QuantMind ETF 研究报告" in app.session_state["report"]
    app.sidebar.selectbox[0].select("510500").run()
    assert len(source.calls) == 1  # form change does not fetch
    report = app.session_state["report"]
    app.selectbox(key="chart_panel").select("RSI").run()
    app.toggle(key="chart_ma").set_value(False).run()
    assert not app.exception and not app.error
    assert len(source.calls) == 1  # chart controls never fetch or change the report snapshot
    assert app.session_state["report"] == report
    assert app.session_state["analysis"].symbol == "510300"


def test_app_failure_state_does_not_show_old_results(tmp_path, make_bars, metadata, monkeypatch):
    source = TestSource(make_bars(count=800, start=str(date.today() - timedelta(days=1100))), metadata)
    original_init = MarketDataService.__init__
    monkeypatch.setattr(MarketDataService, "__init__", lambda self, store, sources=None: original_init(self, store, [source]))
    monkeypatch.setenv("QUANTMIND_DB_PATH", str(tmp_path / "ui-failure.sqlite3"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.sidebar.button[0].click().run()
    assert not app.exception and len(app.metric) == 5
    source.error = "TEST 不可用"
    # Batch form input and submit in one AppTest run, matching browser form semantics.
    app.sidebar.selectbox[0].select("510500")
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert any("无可用真实缓存" in e.value for e in app.error)
    assert len(app.metric) == 0


@pytest.mark.parametrize("case,expected", [("verified", "价量关系"), ("bad-ratio", "未通过"), ("no-amount", "无法核验")])
def test_unit_checks_keep_raw_values_and_report_limitations(tmp_path, make_bars, metadata, case, expected):
    bars = make_bars(count=530, start="2022-01-03", amount=case != "no-amount")
    if case == "bad-ratio":
        bars["amount"] = 1
    source = TestSource(bars, metadata | {"volume_unit": "手（价量关系核验）"})
    source.kind = "eastmoney"
    service = MarketDataService(SQLiteBarStore(tmp_path / "unit-test.sqlite3"), [source])
    result = service.history("510300", "2024-01-01", "2024-01-15")
    assert expected in result.metadata["volume_unit"]
    assert result.bars.volume.iloc[-1] == 100  # raw units retained, never silently rescaled
    if case == "verified":
        assert result.metadata["unit_check_pass_fraction"] == 1
    else:
        assert any("核验" in w for w in result.warnings)


def test_ui_source_choice_is_submitted_with_form(tmp_path, make_bars, metadata, monkeypatch):
    source = TestSource(make_bars(count=800, start=str(date.today() - timedelta(days=1100))), metadata)
    selected_sources = []
    original_init = MarketDataService.__init__
    def test_init(self, store, sources=None):
        selected_sources.append(None if sources is None else [s.kind for s in sources])
        original_init(self, store, [source])
    monkeypatch.setattr(MarketDataService, "__init__", test_init)
    monkeypatch.setenv("QUANTMIND_DB_PATH", str(tmp_path / "source-select.sqlite3"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.sidebar.selectbox[1].select("sina")
    assert not selected_sources and not source.calls
    app.sidebar.button[0].click().run()
    assert not app.exception and not app.error
    assert selected_sources == [["sina"]]
    app.sidebar.selectbox[1].select("eastmoney").run()
    assert selected_sources == [["sina"]]  # editing the next query does not construct/fetch a source


def test_ui_insufficient_values_show_dash_and_explanation(tmp_path, make_bars, metadata, monkeypatch):
    yesterday = date.today() - timedelta(days=1)
    source = TestSource(make_bars(count=1, start=str(yesterday)), metadata)
    original_init = MarketDataService.__init__
    monkeypatch.setattr(MarketDataService, "__init__", lambda self, store, sources=None: original_init(self, store, [source]))
    monkeypatch.setenv("QUANTMIND_DB_PATH", str(tmp_path / "insufficient-ui.sqlite3"))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    app.sidebar.date_input[0].set_value(yesterday)
    app.sidebar.button[0].click().run()
    assert not app.exception and not app.error
    assert [m.value for m in app.metric] == ["1.0000", "—", "—", "—", "—"]
    assert any("— 表示样本不足" in c.value and "21" in c.value for c in app.caption)
    assert "样本不足" in app.session_state["report"]
