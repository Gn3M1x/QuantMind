"""Explicit live check (excluded from pytest); save traceable real data/report artifacts."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from quantmind.analysis import analyze
from quantmind.charts import build_charts
from quantmind.market_data import AkShareETFSource, MarketDataService
from quantmind.report import generate_report
from quantmind.storage import SQLiteBarStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["510300", "510500", "159915"])
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--source", choices=["eastmoney", "sina"], default="eastmoney")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    (root / "reports").mkdir(exist_ok=True)
    service = MarketDataService(SQLiteBarStore(root / "data" / "quantmind.sqlite3"), [AkShareETFSource(args.source)])
    results = []
    for symbol in args.symbols:
        try:
            history = service.history(symbol, args.start, args.end, refresh=True)
            analysis = analyze(symbol, history.bars, args.start, args.end, history.metadata, history.warnings)
            figures = build_charts(analysis)
            filename = f"QuantMind_{symbol}_{args.start}_{args.end}_{args.source}"
            report = generate_report(analysis)
            (root / "reports" / f"{filename}.md").write_text(report, encoding="utf-8")
            history.bars.to_csv(root / "data" / f"{filename}.csv", index=False)
            result = {"symbol": symbol, "status": "通过", "rows": len(analysis.frame),
                      "actual_start": str(analysis.frame.date.min().date()), "actual_end": str(analysis.frame.date.max().date()),
                      "warmup_rows": analysis.prehistory_count, "metadata": history.metadata,
                      "metrics": analysis.metrics, "chart_trace_counts": {k: len(v.data) for k, v in figures.items()},
                      "report_bytes": len(report.encode("utf-8"))}
        except Exception as exc:
            result = {"symbol": symbol, "status": "失败", "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    evidence = {"executed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "source": args.source, "results": results}
    (root / "reports" / f"live_validation_{args.source}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if all(r["status"] == "通过" for r in results) else 1)


if __name__ == "__main__":
    main()
