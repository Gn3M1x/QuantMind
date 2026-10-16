"""Compact record-based charts; no synthetic calendar or invented observations."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import Analysis
from .presentation import ACCENT, DOWN, MUTED, TEXT, UP, display_quantity, quantity_scale, quantity_unit

PLOT_CONFIG = {
    "displaylogo": False,
    "scrollZoom": True,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "QuantMind_chart"},
}


def record_axis(dates: pd.Series) -> dict:
    """One category per actual row. Auto ticks adapt to width and zoom.

    Category labels never imply that absent dates were exchange holidays.
    Full ISO dates are used in customdata for every hover, independently of tick aliases.
    """
    if dates.empty or dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("绘图日期应为非空、无重复且升序的真实日期。")
    full = dates.dt.strftime("%Y-%m-%d").tolist()
    short = (dates.iloc[-1] - dates.iloc[0]).days <= 93
    aliases = dict(zip(full, dates.dt.strftime("%m-%d" if short else "%y-%m-%d")))
    return dict(type="category", categoryorder="array", categoryarray=full,
                tickmode="auto", nticks=8, labelalias=aliases, tickangle=0,
                range=[-.5, len(full) - .5], showgrid=False, fixedrange=False,
                tickfont=dict(size=11, color=MUTED),
                showspikes=True, spikecolor="#65748B", spikethickness=1, spikedash="dot")


def date_gaps(dates: pd.Series, minimum_days: int = 1) -> pd.DataFrame:
    """Observed elapsed days only; never infer a market holiday or missing trading day."""
    elapsed = dates.diff().dt.days
    rows = [{"前一记录": dates.iloc[i - 1].strftime("%Y-%m-%d"),
             "后一记录": dates.iloc[i].strftime("%Y-%m-%d"), "间隔自然日": int(elapsed.iloc[i])}
            for i in range(1, len(dates)) if elapsed.iloc[i] > minimum_days]
    return pd.DataFrame(rows, columns=["前一记录", "后一记录", "间隔自然日"])


def build_charts(result: Analysis) -> dict[str, go.Figure]:
    f = result.frame
    axis = record_axis(f.date)
    dates = axis["categoryarray"]
    custom_dates = [[d] for d in dates]
    volume_unit = quantity_unit(result.metadata, "volume")
    scale, scale_label = quantity_scale(f.volume, volume_unit)
    price = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.025, row_heights=[.75, .25])
    price.add_trace(go.Candlestick(
        x=dates, open=f.open, high=f.high, low=f.low, close=f.close, customdata=custom_dates,
        name="日 K", increasing_line_color=UP, decreasing_line_color=DOWN,
        increasing_fillcolor=UP, decreasing_fillcolor=DOWN, line_width=1,
        hovertemplate="%{customdata[0]}<br>开 %{open:.4f}　高 %{high:.4f}<br>低 %{low:.4f}　收 %{close:.4f}<extra>日 K</extra>"), row=1, col=1)
    for name, color in [("ma5", "#E6B96D"), ("ma20", ACCENT), ("ma60", "#B49AE8")]:
        price.add_trace(go.Scatter(
            x=dates, y=f[name], customdata=custom_dates, mode="lines", name=name.upper(),
            line=dict(color=color, width=1.15), connectgaps=False,
            hovertemplate="%{customdata[0]}<br>" + name.upper() + " %{y:.4f} 元<extra></extra>"), row=1, col=1)
    colors = [UP if c >= o else DOWN for c, o in zip(f.close, f.open)]
    price.add_trace(go.Bar(
        x=dates, y=f.volume / scale, customdata=[[d, display_quantity(v, volume_unit)] for d, v in zip(dates, f.volume)],
        name="成交量", marker_color=colors, marker_line_width=0, opacity=.8, showlegend=False,
        hovertemplate="%{customdata[0]}<br>成交量 %{customdata[1]}<extra></extra>"), row=2, col=1)
    price.update_yaxes(title_text="价格 / 元", row=1, col=1)
    price.update_yaxes(title_text=f"量 / {scale_label}", nticks=3, row=2, col=1)
    price.update_layout(height=550, xaxis_rangeslider_visible=False, bargap=.24)
    # Dashed markers keep longer gaps visible without allocating fake daily slots.
    for i, elapsed in enumerate(f.date.diff().dt.days):
        if pd.notna(elapsed) and elapsed > 3:
            price.add_shape(type="line", x0=i - .5, x1=i - .5, xref="x", y0=0, y1=1, yref="paper",
                            line=dict(color="#697386", width=.7, dash="dot"), opacity=.55, layer="below")
    rsi = go.Figure(go.Scatter(
        x=dates, y=f.rsi14, customdata=custom_dates, mode="lines", name="RSI14", line=dict(color="#E6B96D", width=1.4),
        connectgaps=False, hovertemplate="%{customdata[0]}<br>RSI14 %{y:.4f}<extra></extra>"))
    rsi.add_hline(y=70, line_dash="dot", line_color=UP, line_width=.7)
    rsi.add_hline(y=30, line_dash="dot", line_color=DOWN, line_width=.7)
    rsi.update_layout(height=245, yaxis=dict(range=[0, 100], title="RSI", nticks=5))
    macd = go.Figure()
    macd.add_trace(go.Bar(
        x=dates, y=f.macd, customdata=custom_dates, name="MACD 柱", marker_line_width=0,
        marker_color=[UP if v >= 0 else DOWN for v in f.macd],
        hovertemplate="%{customdata[0]}<br>2 × (DIF − DEA) %{y:.4f} 元<extra></extra>"))
    for key, color in [("dif", "#E6B96D"), ("dea", ACCENT)]:
        macd.add_trace(go.Scatter(
            x=dates, y=f[key], customdata=custom_dates, name=key.upper(), mode="lines", line=dict(color=color, width=1.3),
            connectgaps=False, hovertemplate="%{customdata[0]}<br>" + key.upper() + " %{y:.4f} 元<extra></extra>"))
    macd.update_layout(height=245, yaxis_title="MACD / 元")
    figures = {"price": price, "rsi": rsi, "macd": macd}
    for name, fig in figures.items():
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="-apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, sans-serif", size=12, color=TEXT),
            margin=dict(l=64, r=16, t=34 if name != "rsi" else 12, b=30),
            legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0, font=dict(size=11), itemclick="toggle"),
            hovermode="x unified", hoversubplots="axis", hoverlabel=dict(font_size=12, bgcolor="#192334"),
            dragmode="zoom", uirevision=f"{result.symbol}:{result.start}:{result.end}")
        fig.update_xaxes(**axis)
        fig.update_yaxes(gridcolor="rgba(139,151,170,.12)", gridwidth=.5, zeroline=False,
                         title_font=dict(size=11, color=MUTED), tickfont=dict(size=11, color=MUTED), fixedrange=False)
    price.update_xaxes(showticklabels=False, row=1, col=1)
    return figures
