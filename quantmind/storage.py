"""Transactional SQLite cache; source and adjustment are part of every key."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from .quality import normalize_bars, validate_bars


class SQLiteBarStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            # v2 deliberately leaves any old prototype table untouched.
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS daily_bars (
                    symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL,
                    adjustment TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
                    low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL, amount REAL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(symbol,date,source,adjustment));
                CREATE TABLE IF NOT EXISTS fetch_batches (
                    id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, source TEXT NOT NULL,
                    adjustment TEXT NOT NULL, requested_start TEXT NOT NULL, requested_end TEXT NOT NULL,
                    actual_start TEXT NOT NULL, actual_end TEXT NOT NULL, row_count INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL, metadata TEXT NOT NULL);
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save_batch(self, symbol: str, bars: pd.DataFrame, metadata: dict,
                   start: str, end: str) -> None:
        """Replace the requested range atomically, including removed upstream rows.

        Adjusted series, if added later, replace the entire source/adjustment partition.
        A caller must supply its complete adjusted history, never a partial append.
        """
        bars = normalize_bars(bars)
        quality = validate_bars(bars)
        if not quality.valid:
            raise ValueError("拒绝写入无效行情：" + "；".join(quality.errors))
        if not isinstance(symbol, str) or not symbol.isdigit() or len(symbol) != 6:
            raise ValueError("ETF 代码必须为保留前导零的六位字符串。")
        source, adjustment, fetched_at = (metadata[k] for k in ("source", "adjustment", "fetched_at"))
        if adjustment not in {"none", "qfq", "hfq"}:
            raise ValueError("未知复权方式。")
        if adjustment != "none" and not metadata.get("full_snapshot"):
            raise ValueError("复权数据必须整段快照替换，禁止混合抓取批次。")
        if bars["date"].min() < pd.Timestamp(start) or bars["date"].max() > pd.Timestamp(end):
            raise ValueError("写入行情超出请求范围。")
        rows = [(symbol, r.date.strftime("%Y-%m-%d"), source, adjustment,
                 float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume),
                 None if not hasattr(r, "amount") or pd.isna(r.amount) else float(r.amount), fetched_at)
                for r in bars.itertuples(index=False)]
        with self._connect() as conn:
            if adjustment == "none":
                conn.execute("DELETE FROM daily_bars WHERE symbol=? AND source=? AND adjustment=? AND date BETWEEN ? AND ?",
                             (symbol, source, adjustment, start, end))
            else:
                conn.execute("DELETE FROM daily_bars WHERE symbol=? AND source=? AND adjustment=?", (symbol, source, adjustment))
                conn.execute("DELETE FROM fetch_batches WHERE symbol=? AND source=? AND adjustment=?", (symbol, source, adjustment))
            conn.executemany("INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            conn.execute("""INSERT INTO fetch_batches
                (symbol,source,adjustment,requested_start,requested_end,actual_start,actual_end,row_count,fetched_at,metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (symbol, source, adjustment, start, end, bars["date"].min().strftime("%Y-%m-%d"),
                 bars["date"].max().strftime("%Y-%m-%d"), len(bars), fetched_at, json.dumps(metadata, ensure_ascii=False)))

    def read(self, symbol: str, start: str, end: str, source: str,
             adjustment: str = "none") -> tuple[pd.DataFrame, dict]:
        with self._connect() as conn:
            frame = pd.read_sql_query("""SELECT date,open,high,low,close,volume,amount,fetched_at
                FROM daily_bars WHERE symbol=? AND source=? AND adjustment=? AND date BETWEEN ? AND ? ORDER BY date""",
                conn, params=(symbol, source, adjustment, start, end), parse_dates=["date"])
            batch = conn.execute("""SELECT metadata FROM fetch_batches WHERE symbol=? AND source=? AND adjustment=?
                ORDER BY id DESC LIMIT 1""", (symbol, source, adjustment)).fetchone()
        meta = json.loads(batch[0]) if batch else {}
        if frame.empty:
            return frame.drop(columns=["fetched_at"]), meta
        meta.update(fetched_at_min=frame["fetched_at"].min(), fetched_at_max=frame["fetched_at"].max())
        frame = frame.drop(columns=["fetched_at"])
        if frame["amount"].isna().all():
            frame = frame.drop(columns=["amount"])
        return frame, meta

    def covered(self, symbol: str, start: str, end: str, source: str,
                adjustment: str = "none") -> bool:
        """Use observed response bounds, not merely requested bounds, to detect holes.

        Ten calendar days is a boundary heuristic, never a claim of exchange completeness.
        Store no empty coverage. Interior long gaps are retried on the next query.
        """
        with self._connect() as conn:
            batches = conn.execute("""SELECT requested_start,requested_end,actual_start,actual_end,row_count
                FROM fetch_batches WHERE symbol=? AND source=? AND adjustment=? ORDER BY id DESC""",
                (symbol, source, adjustment)).fetchall()
        bars, _ = self.read(symbol, start, end, source, adjustment)
        if bars.empty or (bars["date"].diff().dt.days > 10).any():
            return False
        for req_start, req_end, actual_start, actual_end, count in batches:
            if req_start <= start and req_end >= end:
                if (pd.Timestamp(actual_start) - pd.Timestamp(start)).days > 10:
                    continue
                if (pd.Timestamp(end) - pd.Timestamp(actual_end)).days > 10:
                    continue
                # Also catches deleted/corrupt cache rows within an exact batch.
                whole, _ = self.read(symbol, req_start, req_end, source, adjustment)
                if len(whole) >= count and whole["date"].min().strftime("%Y-%m-%d") <= actual_start and whole["date"].max().strftime("%Y-%m-%d") >= actual_end:
                    return True
        return False
