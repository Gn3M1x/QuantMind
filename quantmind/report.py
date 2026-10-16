"""Rule-based Chinese report; no model calls, estimates, or separate calculations."""
from .analysis import Analysis, METRIC_LABELS, format_metric
from .presentation import quantity_unit

METHODS = """- MA5/20/60：收盘价完整窗口简单平均；不足窗口不计算。
- RSI14：首 14 个收盘价变动（需 15 个收盘价）的正、负变动分别取简单平均作为初值，之后按 (前值×13+当期值)/14 递推。平均跌幅为零且涨幅为正时为 100，只有跌幅时为 0，完全横盘时约定为 50。
- MACD：EMA12、EMA26 以首个收盘价初始化，α=2/(N+1)，递推计算；第 26 个收盘价起输出 DIF；DEA 以首个有效 DIF 初始化，满 9 个 DIF（第 34 个收盘价）后输出。柱状值=2×(DIF−DEA)，单位元。加载所选起点前 730 个自然日作预热，目标至少 250 条前置日线；上市较晚或覆盖不足时会提示。EMA 为有限历史近似，仍可能受起点影响。
- 20 日价格收益率：close[t]/close[t−20]−1，需要至少 21 个收盘价。
- 20 日年化历史波动率：20 个日简单收益率的样本标准差（ddof=1）×√252，需要至少 21 个收盘价；252 为年交易日数量假设。
- 区间价格收益率：所选区间最后收盘价/最初收盘价−1，至少 2 条日线。
- 区间最大回撤：仅在实际所选区间计算 min(close/close.cummax()−1)，以非正百分比展示，至少 2 条日线。"""


def generate_report(result: Analysis) -> str:
    m, f = result.metadata, result.frame
    metric_rows = "\n".join(f"| {label} | {format_metric(key, result.metrics[key])} |" for key, label in METRIC_LABELS.items())
    issues = "\n".join("- " + w.replace("\n", " ") for w in result.warnings)
    unit_descriptions = {}
    for field in ("volume", "amount"):
        unit = quantity_unit(m, field)
        unit_descriptions[field] = unit.name + ("（已核实）" if unit.verified else "（未核实；保留原始值）")
    rsi = result.metrics["rsi14"]
    rsi_text = "样本不足" if rsi is None else ("处于常用高位观察区（≥70）" if rsi >= 70 else "处于常用低位观察区（≤30）" if rsi <= 30 else "处于 30–70 的中间观察区")
    return f"""# QuantMind ETF 研究报告

## 标的与数据

- ETF：{result.symbol} · {result.name}
- 查询区间：{result.start} 至 {result.end}
- 实际覆盖区间：{f['date'].min().date()} 至 {f['date'].max().date()}（{len(f)} 条日线）
- 数据截至日期：{f['date'].max().date()}
- 接口及上游来源：{m['source']}
- 上游地址：{m.get('source_url', '未记录')}
- 复权方式：{m.get('adjustment_label', m['adjustment'])}
- 价格单位：{m.get('price_unit', '未核实')}；成交量单位：{unit_descriptions['volume']}；成交额单位：{unit_descriptions['amount'] if 'amount' in f else '未提供'}
- 抓取时间（含时区）：{m.get('fetched_at_min', m['fetched_at'])} 至 {m.get('fetched_at_max', m['fetched_at'])}
- 数据状态：{m.get('status', '未知')}
- 预热历史：{result.prehistory_count} 条日线
- 收益口径：不复权收盘价格收益率，不含现金分红，非包含现金分红的总收益率。

单位核实说明：价量关系仅用于一致性诊断，旧来源备注中的推断不作为已核实单位的依据，未进行物理单位换算。

## 行情与技术指标

| 指标 | 数值 |
| --- | ---: |
{metric_rows}

RSI14 {rsi_text}。均线反映历史价格的平滑趋势，DIF/DEA 和柱状值反映不同平滑周期之间的差异；这些技术描述不构成确定性预测。MA、RSI 与 MACD 的样本不足状态均保留。

## 数据质量与样本限制

{issues}

## 计算口径

{METHODS}

## 风险说明

本报告仅用于个人研究与学习。技术指标基于历史价格，不保证未来表现；波动率与回撤均为样本内历史统计，不是未来损失上限。数据来自公开接口，可能延迟、修订或中断；不复权价格在分红等事件前后可能不连续。本报告未引入新闻、基本面、交易成本、现金分红再投资或策略回测，不提供自动交易或投资建议。
"""
