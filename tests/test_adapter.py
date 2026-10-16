"""Adapter contract tests simulate the worker transport; always OFFLINE TEST samples."""
from types import SimpleNamespace
import subprocess

import pytest

from quantmind.market_data import AkShareETFSource, MarketDataError

# Keep the implementation before autouse fixture replaces public network entrypoint.
FETCH_IMPLEMENTATION = AkShareETFSource.fetch


def test_adapter_bounded_worker_roundtrip(monkeypatch, make_bars):
    bars = make_bars(count=3)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        bars.to_json(args[-1], orient="records", date_format="iso")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    result = FETCH_IMPLEMENTATION(AkShareETFSource(), "510300", "2023-01-01", "2023-01-06")
    assert result.close.tolist() == [1, 2, 3]
    args, kwargs = calls[0]
    assert args[1:6] == ["-m", "quantmind.market_data", "eastmoney", "510300", "2023-01-01"]
    assert kwargs["timeout"] == 50 and kwargs["capture_output"]


def test_adapter_timeout_and_failure_are_explicit(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("TEST", 50)
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(MarketDataError, match="超过 50 秒"):
        FETCH_IMPLEMENTATION(AkShareETFSource(), "510300", "2023-01-01", "2023-01-06")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr="TEST ConnectionError", stdout=""))
    with pytest.raises(MarketDataError, match="TEST ConnectionError"):
        FETCH_IMPLEMENTATION(AkShareETFSource(), "510300", "2023-01-01", "2023-01-06")


def test_adapter_rejects_out_of_bounds_data(monkeypatch, make_bars):
    def run(args, **kwargs):
        make_bars(count=3).to_json(args[-1], orient="records", date_format="iso")
        return SimpleNamespace(returncode=0, stderr="", stdout="")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(MarketDataError, match="超出请求范围"):
        FETCH_IMPLEMENTATION(AkShareETFSource(), "510300", "2023-01-03", "2023-01-06")
