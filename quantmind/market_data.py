"""AKShare adapters with bounded requests and honest, partitioned cache fallback."""
from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd

from .instruments import normalize_symbol
from .quality import normalize_bars, validate_bars, range_warnings
from .storage import SQLiteBarStore

logger = logging.getLogger(__name__)
SOURCE_NAME = "AKShare fund_etf_hist_em / 东方财富"


class MarketDataError(RuntimeError):
    pass


@dataclass
class HistoryResult:
    bars: pd.DataFrame
    metadata: dict
    warnings: list[str]


class AkShareETFSource:
    def __init__(self, kind: str = "eastmoney"):
        if kind not in {"eastmoney", "sina"}:
            raise ValueError("未知数据源。")
        self.kind = kind
        self.name = SOURCE_NAME if kind == "eastmoney" else "AKShare fund_etf_hist_sina / 新浪财经"

    def metadata(self) -> dict:
        return {
            "source": self.name,
            "source_url": ("https://push2his.eastmoney.com/api/qt/stock/kline/get" if self.kind == "eastmoney"
                           else "https://finance.sina.com.cn/realstock/company/{market}{symbol}/hisdata_klc2/klc_kl.js"),
            "interface": "fund_etf_hist_em" if self.kind == "eastmoney" else "fund_etf_hist_sina",
            "akshare_version": importlib.metadata.version("akshare"),
            "adjustment": "none", "adjustment_label": "不复权（原始交易价格）",
            "price_unit": "元/份（人民币）",
            "volume_unit": "手（100份；价量关系核验）" if self.kind == "eastmoney" else "份（价量关系推断；官方文档标手存在冲突）",
            "amount_unit": "元（人民币；接口提供时）",
            "unit_note": ("AKShare 东财字段表未注明单位；成交量手、成交额元按成交额/(成交量×100)应落入日内价格区间核验，属于关系推断。"
                          if self.kind == "eastmoney" else "新浪成交量单位按成交额/成交量应落入价格区间推断为份，并以510300样本与东财同日数据交叉核验；与官方文档标手冲突，保留原始值不换算。接口无复权参数，作为不复权行情使用；未独立核对全部分红事件。"),
        }

    def fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Separate process enforces a 50s wall timeout, including AKShare internals."""
        symbol = normalize_symbol(symbol)
        with tempfile.TemporaryDirectory(prefix="quantmind-fetch-") as directory:
            output = Path(directory) / "bars.json"
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "quantmind.market_data", self.kind, symbol, start, end, str(output)],
                    capture_output=True, text=True, timeout=50, cwd=Path(__file__).resolve().parents[1])
            except subprocess.TimeoutExpired as exc:
                raise MarketDataError(f"{self.name} 请求超过 50 秒，已终止本次请求。") from exc
            if proc.returncode != 0:
                logger.warning("AKShare 子进程错误：%s", (proc.stderr or proc.stdout)[-5000:])
                detail = (proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout).strip() else "进程异常退出"
                raise MarketDataError(f"{self.name} 请求失败：{detail}")
            if not output.exists():
                raise MarketDataError(f"{self.name} 未返回有效结果文件。")
            raw = pd.read_json(output, orient="records", convert_dates=False)
        bars = normalize_bars(raw)
        quality = validate_bars(bars)
        if not quality.valid:
            raise MarketDataError("数据源返回行情未通过校验：" + "；".join(quality.errors))
        if bars["date"].min() < pd.Timestamp(start) or bars["date"].max() > pd.Timestamp(end):
            raise MarketDataError("数据源返回超出请求范围的行情，已拒绝写入。")
        return bars


class MarketDataService:
    def __init__(self, store: SQLiteBarStore, sources=None):
        self.store = store
        self.sources = sources if sources is not None else [AkShareETFSource(), AkShareETFSource("sina")]

    def history(self, symbol: str, start: str, end: str, *, refresh: bool = False) -> HistoryResult:
        symbol = normalize_symbol(symbol)
        begin, finish = pd.Timestamp(start), pd.Timestamp(end)
        if pd.isna(begin) or pd.isna(finish) or begin > finish:
            raise ValueError("请输入有效的日期范围，开始日期应不晚于结束日期。")
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if finish.date() > today:
            raise ValueError("结束日期不能晚于今天。")
        warm_start = (begin.date() - timedelta(days=730)).isoformat()
        end = finish.date().isoformat()
        failures, fallback = [], []
        # Scan all partitions before any network call, so a covered Sina cache also avoids EM calls.
        if not refresh and end < today.isoformat():
            for source in self.sources:
                cached, meta = self.store.read(symbol, warm_start, end, source.name)
                fresh = bool(meta) and meta.get("fetched_at", "")[:10] == today.isoformat()
                if fresh and not cached.empty and validate_bars(cached).valid and self.store.covered(symbol, warm_start, end, source.name):
                    meta["status"] = "使用缓存（已检查抓取批次与覆盖范围）"
                    return HistoryResult(cached, meta, meta.get("warnings", []) + [meta.get("unit_note", "")])
        for source in self.sources:
            cached, meta = self.store.read(symbol, warm_start, end, source.name)
            if not cached.empty:
                quality = validate_bars(cached)
                if quality.valid and cached["date"].between(begin, finish).any():
                    fallback.append((cached, meta))
                elif not quality.valid:
                    failures.append(f"{source.name} 缓存校验失败：{'；'.join(quality.errors)}")
            try:
                bars = source.fetch(symbol, warm_start, end)
                quality = validate_bars(bars)
                if not quality.valid:
                    raise MarketDataError("严重行情异常：" + "；".join(quality.errors))
                if bars.empty or not bars["date"].between(begin, finish).any():
                    raise MarketDataError("接口实际返回范围未覆盖所选区间，没有可供分析的日线。")
                fetched_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
                metadata = source.metadata() | {"symbol": symbol, "fetched_at": fetched_at,
                                               "fetched_at_min": fetched_at, "fetched_at_max": fetched_at,
                                               "requested_start": warm_start, "requested_end": end,
                                               "actual_start": str(bars["date"].min().date()),
                                               "actual_end": str(bars["date"].max().date()),
                                               "status": "实时接口获取成功（已校验并写入缓存）"}
                metadata["source_url"] = metadata.get("source_url", "").replace("{market}", "sh" if symbol.startswith("5") else "sz").replace("{symbol}", symbol)
                issues = list(failures) + list(quality.warnings) + [metadata.get("unit_note", "")]
                if bars["date"].max().date() == today:
                    issues.append("包含当日行情；收盘前可能未完成，收盘后公开接口仍可能延迟或修订，请手动刷新确认。")
                issues.extend(range_warnings(bars, warm_start, end, today=today))
                if "amount" not in bars:
                    metadata["amount_unit"] = "未提供"
                if "amount" in bars and getattr(source, "kind", None) in {"eastmoney", "sina"}:
                    active = bars.loc[bars["volume"] > 0]
                    implied_price = active["amount"] / (active["volume"] * (100 if source.kind == "eastmoney" else 1))
                    ratio_valid = ((implied_price >= active["low"] * .98) & (implied_price <= active["high"] * 1.02)).mean()
                    metadata["unit_check_rows"] = len(active)
                    metadata["unit_check_pass_fraction"] = None if active.empty else float(ratio_valid)
                    if active.empty or ratio_valid < .95:
                        metadata["volume_unit"] = "原始值（价量单位核验未通过）"
                        metadata["amount_unit"] = "原始值（价量单位核验未通过）"
                        issues.append("成交额/成交量缺少有效样本或与价格关系未通过 95% 样本核验；单位未核实，不作换算。")
                if "amount" not in bars and getattr(source, "kind", None) in {"eastmoney", "sina"}:
                    metadata["volume_unit"] = "原始值（本次缺少成交额，单位无法核验）"
                    issues.append("本次没有成交额，无法通过价量关系核验成交量单位；保留原始值。")
                metadata["warnings"] = list(dict.fromkeys(w for w in issues if w))
                self.store.save_batch(symbol, bars, metadata, warm_start, end)
                return HistoryResult(bars, metadata, list(dict.fromkeys(w for w in issues if w)))
            except (MarketDataError, ValueError) as exc:
                reason = f"{source.name}：{exc}"
                logger.warning("行情请求失败：%s", reason)
                failures.append(reason)
        if fallback:
            cached, meta = fallback[0]
            meta = meta | {"status": "使用缓存（接口失败）", "failure_reason": "；".join(failures)}
            return HistoryResult(cached, meta, ["使用缓存：" + "；".join(failures), meta.get("unit_note", "")])
        raise MarketDataError("无可用真实缓存，获取行情失败。" + "；".join(failures))


def _worker():
    import akshare as ak
    kind, symbol, start, end, output = sys.argv[1:]
    if kind == "eastmoney":
        frame = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start.replace("-", ""),
                                    end_date=end.replace("-", ""), adjust="")
    else:
        prefix = "sh" if symbol.startswith("5") else "sz"
        frame = ak.fund_etf_hist_sina(symbol=prefix + symbol)
        frame = normalize_bars(frame)
        frame = frame.loc[frame["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
    frame.to_json(output, orient="records", date_format="iso", force_ascii=False, double_precision=15)


if __name__ == "__main__":
    _worker()
