"""All fixtures are artificial TEST samples, never production/demo market data."""
import socket

import numpy as np
import pandas as pd
import pytest

from quantmind.market_data import AkShareETFSource


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("离线测试禁止连接真实网络或调用真实行情适配器")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(AkShareETFSource, "fetch", blocked)


@pytest.fixture
def make_bars():
    def make(close=None, count=300, start="2023-01-02", amount=True):
        # Synthetic TEST data: bdate_range here is not a production exchange calendar.
        prices = np.asarray(close if close is not None else np.arange(1, count + 1), dtype=float)
        f = pd.DataFrame({"date": pd.bdate_range(start, periods=len(prices)), "open": prices,
                          "high": prices + .5, "low": prices - .5, "close": prices, "volume": 100.0})
        if amount:
            f["amount"] = prices * 10_000
        return f
    return make


@pytest.fixture
def metadata():
    return {"source": "TEST / 人工构造样本", "adjustment": "none", "adjustment_label": "不复权（测试）",
            "fetched_at": "2026-10-16T08:00:00+08:00", "price_unit": "元（测试）",
            "volume_unit": "手（测试）", "amount_unit": "元（测试）", "status": "TEST", "source_url": "TEST"}
