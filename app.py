"""QuantMind: a paper-and-ink ETF research workspace with linked chart panels."""
from datetime import date, datetime, timedelta
from html import escape
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4

import streamlit as st

from quantmind.analysis import analyze, format_metric
from quantmind.charts import build_workspace, date_gaps
from quantmind.chart_component import render_chart
from quantmind.instruments import ETF_NAMES
from quantmind.market_data import AkShareETFSource, MarketDataService, MarketDataError
from quantmind.presentation import display_quantity, metric_color, quantity_unit
from quantmind.report import generate_report, METHODS
from quantmind.storage import SQLiteBarStore

ROOT = Path(__file__).resolve().parent
SOURCES = {"auto": "自动 · 东方财富 → 新浪财经", "eastmoney": "东方财富", "sina": "新浪财经"}
CORE_METRICS = ("close", "return20", "rsi14", "volatility20", "max_drawdown")
CARD_LABELS = {"close": "最新收盘价（元）", "return20": "20 日价格收益率", "rsi14": "RSI14",
               "volatility20": "20 日年化波动率", "max_drawdown": "区间最大回撤"}
SAMPLE_HELP = {"close": "需要至少 1 条有效收盘记录。", "return20": "需要至少 21 个有效收盘价。",
               "rsi14": "Wilder 初值需要至少 15 个有效收盘价。", "volatility20": "需要 20 个日收益率，即至少 21 个收盘价。",
               "max_drawdown": "所选区间需要至少 2 条日线。"}


@st.cache_resource
def service(db_path: str, source_choice: str = "auto") -> MarketDataService:
    (ROOT / "logs").mkdir(exist_ok=True)
    logger = logging.getLogger("quantmind")
    if not logger.handlers:
        handler = RotatingFileHandler(ROOT / "logs" / "quantmind.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    sources = None if source_choice == "auto" else [AkShareETFSource(source_choice)]
    return MarketDataService(SQLiteBarStore(db_path), sources)


st.set_page_config(page_title="QuantMind · ETF 研究室", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"<style>{(ROOT / 'quantmind' / 'assets' / 'workbench.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
with st.sidebar:
    st.markdown('''<div class="qm-brand"><span class="qm-seal">研</span><div>
        <div class="qm-brand-name">QuantMind</div><div class="qm-brand-sub">静 観 · ETF RESEARCH</div></div></div>
        <div class="qm-section">01 / <b>研究范围</b></div>''', unsafe_allow_html=True)
    with st.form("query_form"):
        symbol = st.selectbox("ETF", list(ETF_NAMES), format_func=lambda s: f"{s} · {ETF_NAMES[s]}", key="query_symbol")
        start = st.date_input("开始日期", today - timedelta(days=365), min_value=date(2000, 1, 1), max_value=today,
                              format="YYYY-MM-DD", key="query_start")
        end = st.date_input("结束日期", today - timedelta(days=1), min_value=date(2000, 1, 1), max_value=today,
                            format="YYYY-MM-DD", key="query_end")
        source_choice = st.selectbox("数据源", list(SOURCES), format_func=SOURCES.get, key="query_source")
        query = st.form_submit_button("查询行情", type="primary", width="stretch")
        refresh = st.form_submit_button("刷新行情", width="stretch")
    st.caption("调整条件后点击查询；刷新会重新请求数据源并更新缓存。")
    st.divider()
    st.markdown('''<div class="qm-side-note">静观其变，<br>有据而行。</div>
        <div class="qm-side-foot">不复权 / 日线研究<br>价格收益不含现金分红。<br><br>
        基于真实行情与可追溯缓存，<br>技术指标不构成确定性预测。</div>''', unsafe_allow_html=True)

st.markdown(f'''<div class="qm-masthead"><div><div class="qm-masthead-title">市场研究手帖</div>
    <div class="qm-eyebrow">QUANTMIND / MARKET OBSERVATORY</div></div>
    <div class="qm-edition">{today.strftime('%Y.%m.%d')}<br>日线 · 不复权 · 本地研究</div></div>''', unsafe_allow_html=True)

if query or refresh:
    st.session_state.pop("analysis", None)
    st.session_state.pop("report", None)
    if start > end:
        st.error("开始日期不能晚于结束日期，请调整研究范围。")
    else:
        try:
            with st.spinner("正在读取真实行情并校验……每个来源最多等待 50 秒。"):
                history = service(os.environ.get("QUANTMIND_DB_PATH", str(ROOT / "data" / "quantmind.sqlite3")), source_choice).history(
                    symbol, start.isoformat(), end.isoformat(), refresh=refresh)
                result = analyze(symbol, history.bars, start.isoformat(), end.isoformat(), history.metadata, history.warnings)
                st.session_state.analysis = result
                st.session_state.report = generate_report(result)
                st.session_state.chart_query_id = uuid4().hex
                st.session_state.chart_range = "全部"
        except (MarketDataError, ValueError) as exc:
            st.error(str(exc))
        except Exception:
            logging.getLogger("quantmind").exception("工作台运行失败")
            st.error("处理行情时发生运行错误。请检查 logs/quantmind.log；未生成研究结果。")

if "analysis" not in st.session_state:
    st.markdown('''<div class="qm-empty"><div class="qm-enso" aria-hidden="true"></div>
        <div class="qm-eyebrow">相場の記録 / A QUIETER VIEW OF THE MARKET</div>
        <h1>静看市场，<br>让研究有迹可循。</h1>
        <p>从一段真实行情开始，观察价格、趋势与风险。<br>
        选择左侧 ETF、日期和数据源，点击「查询行情」。</p></div>
        <div class="qm-empty-grid"><div><span>一 / PRICE</span><h3>观价格</h3>
        <p>日 K 与成交量同轴呈现，<br>每一个位置都对应真实行情记录。</p></div>
        <div><span>二 / INDICATORS</span><h3>察趋势</h3>
        <p>均线、MACD 与 RSI 分层观察，<br>在同一时间坐标中寻找线索。</p></div>
        <div><span>三 / RESEARCH</span><h3>留依据</h3>
        <p>保留来源、口径与研究报告，<br>让每一次观察都可以回看。</p></div></div>''', unsafe_allow_html=True)
    st.caption("仅使用真实接口或有来源记录的真实缓存；数据不可用时会明确提示。窄屏可通过左上角展开研究范围。")
    st.stop()

result = st.session_state.analysis
m, frame = result.metadata, result.frame
source_label = m["source"].split(" / ")[-1]
cache_status = "使用缓存" if "使用缓存" in m["status"] else "接口获取 · 已校验"
st.markdown(f'''<div class="qm-heading"><h1>{escape(result.name)}</h1>
    <span class="qm-symbol">{escape(result.symbol)} / ETF</span>
    <span class="qm-status">{escape(cache_status)}</span></div>''', unsafe_allow_html=True)
st.caption(f"数据截至 {frame.date.max().date()}　·　{source_label}　·　实际 {frame.date.min().date()} — {frame.date.max().date()}　·　{len(frame)} 条日线")
st.caption(f"已提交研究区间　{result.start} — {result.end}　 / 　不复权 · 价格收益不含现金分红")
if "使用缓存" in m["status"]:
    st.warning(f"{m['status']}；最后抓取：{m.get('fetched_at_max', m['fetched_at'])}")
if m.get("failure_reason"):
    st.error("本次接口失败原因：" + m["failure_reason"])
for warning in result.warnings:
    if "数据可能陈旧" in warning or "数据可能过期" in warning:
        st.warning(warning)

previous = float(frame.close.iloc[-2]) if len(frame) >= 2 else None
colors = "\n".join(f".st-key-metric_{k} [data-testid='stMetricValue'] {{color:{metric_color(k, result.metrics[k], previous)};}}" for k in CORE_METRICS)
st.markdown(f"<style>{colors}</style>", unsafe_allow_html=True)
for column, key in zip(st.columns(5, gap="small"), CORE_METRICS):
    with column, st.container(key=f"metric_{key}"):
        value = result.metrics[key]
        st.metric(CARD_LABELS[key], "—" if value is None else format_metric(key, value), help=SAMPLE_HELP[key], border=True)
missing = [CARD_LABELS[k] + "：" + SAMPLE_HELP[k] for k in CORE_METRICS if result.metrics[k] is None]
if missing:
    st.caption("— 表示样本不足。" + "；".join(missing))

vunit, aunit = quantity_unit(m, "volume"), quantity_unit(m, "amount")
technical_tab, table_tab, report_tab, source_tab = st.tabs(["行情图表", "历史行情", "研究报告", "数据说明"])
with technical_tab:
    with st.container(border=True, key="main_chart"):
        st.markdown('<div class="qm-chart-heading"><b>价格与技术指标</b> CHART WORKSPACE</div>', unsafe_allow_html=True)
        range_col, panel_col, ma_col = st.columns([2.5, 1.6, .9], gap="medium", vertical_alignment="bottom")
        with range_col:
            selected_range = st.segmented_control("图表视窗", ["1个月", "3个月", "6个月", "全部"], default="全部",
                                                  key="chart_range", help="仅缩放当前图表，不改变已提交的研究区间和报告。")
        with panel_col:
            panel = st.selectbox("副图指标", ["MACD + RSI", "MACD", "RSI", "仅价量"], key="chart_panel")
        with ma_col:
            show_ma = st.toggle("均线", value=True, key="chart_ma", help="显示 MA5、MA20、MA60。")
        latest = frame.iloc[-1]
        ohlc = "".join(f'<span>{label}<b>{latest[key]:.4f}</b></span>' for key, label in
                       (("open", "开"), ("high", "高"), ("low", "低"), ("close", "收")))
        st.markdown(f'<div class="qm-ohlc"><span>{latest.date.date()}</span>{ohlc}</div>', unsafe_allow_html=True)
        chart_months = {"1个月": 1, "3个月": 3, "6个月": 6}.get(selected_range)
        figure = build_workspace(result, months=chart_months,
                                 oscillator={"MACD + RSI": "both", "MACD": "macd", "RSI": "rsi", "仅价量": "none"}[panel],
                                 show_ma=show_ma)
        if "chart_query_id" not in st.session_state:
            st.session_state.chart_query_id = uuid4().hex
        render_chart(result, figure, st.session_state.chart_query_id, chart_months)
        amount = display_quantity(float(latest.amount), aunit) if "amount" in frame else "未提供"
        st.caption(f"最新成交量 {display_quantity(float(latest.volume), vunit)}　·　成交额 {amount}")
        st.caption("　 ·　 ".join(f"{key.upper()} {format_metric(key, result.metrics[key])}" for key in ("ma5", "ma20", "ma60")))
    st.caption("左键拖动或双指左右滑动平移 · Ctrl/⌘ + 滚轮或捏合缩放 · 双击恢复视图。普通上下滚动可滚动页面，图表外操作保持正常。")
    st.caption("自动跟随使中心 K 线的高低价中点保持垂直居中；关闭后可拖动右侧价格轴调整。快捷视窗只改变图表，顶部统计与报告仍对应已提交研究区间。")
    st.caption("按实际记录紧凑排列；未返回日期不判定为休市，日期完整性尚未严格核验。虚线标出超过 3 个自然日的记录间隔。")
    with st.expander("图表阅读与指标口径"):
        st.write("红涨绿跌；K 线颜色比较当条记录的收盘与开盘，顶部收盘价颜色比较所选区间内前一条收盘。右侧色签为最后一条记录的收盘价。")
        st.write("均线与指标基于完整前置历史计算。指标空段表示样本不足；RSI 30/70 为常用观察线，MACD 柱为 2 × (DIF − DEA)。")
        st.write("1/3/6 个月以最后一条行情向前回溯自然月，仅缩放已有记录；不会请求或补齐新行情。副图共享横轴，缩放与平移同步。")
with table_tab:
    view = frame.copy()
    view["date"] = view.date.dt.strftime("%Y-%m-%d")
    view["volume"] = view.volume.map(lambda x: display_quantity(x, vunit))
    if "amount" in view:
        view["amount"] = view.amount.map(lambda x: display_quantity(x, aunit))
    names = {"date": "交易日期", "open": "开盘（元）", "high": "最高（元）", "low": "最低（元）", "close": "收盘（元）",
             "volume": "成交量", "amount": "成交额", "return20": "20日收益率", "volatility20": "年化波动率", "drawdown": "区间回撤"}
    st.dataframe(view.rename(columns=names), hide_index=True, width="stretch", height=430)
    st.caption("万/亿仅为展示缩写。单位未经核实时保留“原始单位”说明；转换不写回行情或数据库。")
    with st.expander("原始数值与完整精度"):
        st.dataframe(frame, hide_index=True, width="stretch")
with report_tab:
    st.download_button("下载 Markdown 研究报告", data=st.session_state.report.encode("utf-8"),
                       file_name=f"QuantMind_{result.symbol}_{result.start}_{result.end}.md",
                       mime="text/markdown; charset=utf-8", on_click="ignore", type="primary")
    st.markdown(st.session_state.report)
with source_tab:
    st.write(f"**来源**：{m['source']}　·　**接口**：`{m.get('interface', '未记录')}`")
    st.write(f"**抓取时间**：{m.get('fetched_at_min', m['fetched_at'])} 至 {m.get('fetched_at_max', m['fetched_at'])}")
    st.write(f"**复权**：{m['adjustment_label']}　·　**价格单位**：{m['price_unit']}")
    st.write(f"**成交量单位**：{vunit.name}{'（已核实）' if vunit.verified else '（未核实）'}　·　**成交额单位**：{aunit.name}{'（已核实）' if aunit.verified else '（未核实）'}")
    st.caption("价量关系检查仅为一致性诊断，不代替字段单位的权威定义；旧缓存中的单位推断不会自动获得已核实状态。")
    with st.expander(f"数据质量与完整性 · {len(result.warnings)} 项说明"):
        for warning in result.warnings:
            if warning:
                st.write("- " + warning)
        gaps = date_gaps(frame.date)
        st.write("记录间隔（自然日）仅表示相邻返回日期的距离，未判定任何间隔为休市或缺失交易日。")
        if not gaps.empty:
            st.dataframe(gaps, hide_index=True, width="stretch")
    with st.expander("来源原始声明与单位依据"):
        st.write(f"上游地址：{m.get('source_url', '未记录')}")
        st.write(f"AKShare {m.get('akshare_version', '未记录')}")
        st.write(f"原始成交量声明：{m.get('volume_unit', '未核实')}；原始成交额声明：{m.get('amount_unit', '未核实')}")
        st.write(m.get("unit_note", "尚无可独立核实的字段单位说明。"))
        for field in ("volume", "amount"):
            if m.get(f"{field}_unit_evidence"):
                st.write(m[f"{field}_unit_evidence"])
    with st.expander("指标口径与研究限制"):
        st.markdown(METHODS)
        st.write("价格收益不含现金分红；历史统计不保证未来表现。")

st.markdown('''<div class="qm-footer"><span>QUANTMIND / 静观 · 有据</span>
    <span>真实记录　·　确定性指标　·　可追溯研究</span></div>''', unsafe_allow_html=True)
