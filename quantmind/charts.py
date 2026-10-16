"""Compact record-based charts; no synthetic calendar or invented observations."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import Analysis
from .presentation import (ACCENT, DOWN, GOLD, GRID, MUTED, PAPER, PLUM, TEXT, UP,
                           display_quantity, quantity_scale, quantity_unit)

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
                showspikes=True, spikecolor=MUTED, spikethickness=1, spikedash="dot", spikemode="across")


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
    for name, color in [("ma5", GOLD), ("ma20", ACCENT), ("ma60", PLUM)]:
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
                            line=dict(color=MUTED, width=.7, dash="dot"), opacity=.35, layer="below")
    rsi = go.Figure(go.Scatter(
        x=dates, y=f.rsi14, customdata=custom_dates, mode="lines", name="RSI14", line=dict(color=PLUM, width=1.4),
        connectgaps=False, hovertemplate="%{customdata[0]}<br>RSI14 %{y:.4f}<extra></extra>"))
    rsi.add_hline(y=70, line_dash="dot", line_color=UP, line_width=.7)
    rsi.add_hline(y=30, line_dash="dot", line_color=DOWN, line_width=.7)
    rsi.update_layout(height=245, yaxis=dict(range=[0, 100], title="RSI", nticks=5))
    macd = go.Figure()
    macd.add_trace(go.Bar(
        x=dates, y=f.macd, customdata=custom_dates, name="MACD 柱", marker_line_width=0,
        marker_color=[UP if v >= 0 else DOWN for v in f.macd],
        hovertemplate="%{customdata[0]}<br>2 × (DIF − DEA) %{y:.4f} 元<extra></extra>"))
    for key, color in [("dif", GOLD), ("dea", ACCENT)]:
        macd.add_trace(go.Scatter(
            x=dates, y=f[key], customdata=custom_dates, name=key.upper(), mode="lines", line=dict(color=color, width=1.3),
            connectgaps=False, hovertemplate="%{customdata[0]}<br>" + key.upper() + " %{y:.4f} 元<extra></extra>"))
    macd.update_layout(height=245, yaxis_title="MACD / 元")
    figures = {"price": price, "rsi": rsi, "macd": macd}
    for name, fig in figures.items():
        fig.update_layout(
            template="plotly_white", paper_bgcolor=PAPER, plot_bgcolor=PAPER,
            font=dict(family="-apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, sans-serif", size=12, color=TEXT),
            margin=dict(l=12, r=72, t=34 if name != "rsi" else 12, b=30),
            legend=dict(orientation="h", y=1.01, yanchor="bottom", x=0, font=dict(size=11), itemclick="toggle"),
            hovermode="x unified", hoversubplots="axis", hoverlabel=dict(font_size=12, bgcolor=PAPER, bordercolor=GRID),
            dragmode="pan", uirevision=f"{result.symbol}:{result.start}:{result.end}")
        fig.update_xaxes(**axis)
        fig.update_yaxes(gridcolor=GRID, gridwidth=.5, zeroline=False, side="right",
                         title_font=dict(size=11, color=MUTED), tickfont=dict(size=11, color=MUTED), fixedrange=False)
    price.update_xaxes(showticklabels=False, row=1, col=1)
    return figures


def build_workspace(result: Analysis, *, months: int | None = None,
                    oscillator: str = "both", show_ma: bool = True) -> go.Figure:
    """One linked chart workspace, using the same unrounded Analysis observations.

    A quick range changes only the initial viewport, never the selected analysis period,
    indicator warm-up, report, or underlying observations. Months are calendar offsets
    from the last returned record, not an assumed number of trading days.
    """
    if oscillator not in {"both", "macd", "rsi", "none"}:
        raise ValueError("未知指标面板。")
    if months is not None and months not in {1, 3, 6}:
        raise ValueError("图表快捷范围仅支持 1、3、6 个月或全部。")
    source = build_charts(result)
    f = result.frame
    axis = record_axis(f.date)
    first = 0 if months is None else int(f.date.searchsorted(f.date.iloc[-1] - pd.DateOffset(months=months)))
    axis["range"] = [first - .5, len(f) - .5]
    # Four ticks also leave room for full year-bearing labels on a phone-width plot.
    axis["nticks"] = 4
    panels = [key for key in ("macd", "rsi") if oscillator in {"both", key}]
    heights = [.58, .14, .15, .13] if len(panels) == 2 else [.67, .15, .18] if panels else [.8, .2]
    fig = make_subplots(rows=2 + len(panels), cols=1, shared_xaxes=True,
                        vertical_spacing=.035, row_heights=heights)
    for trace in source["price"].data:
        if trace.name in {"MA5", "MA20", "MA60"} and not show_ma:
            continue
        fig.add_trace(trace, row=2 if trace.type == "bar" else 1, col=1)
    for row, panel in enumerate(panels, start=3):
        for trace in source[panel].data:
            fig.add_trace(trace, row=row, col=1)
        if panel == "rsi":
            fig.add_hrect(y0=30, y1=70, fillcolor=PLUM, opacity=.05, line_width=0, row=row, col=1)
            for level in (30, 70):
                fig.add_hline(y=level, line_dash="dot", line_color=PLUM, line_width=.8, row=row, col=1)
            fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70], row=row, col=1)
        else:
            fig.add_hline(y=0, line_color=GRID, line_width=1, row=row, col=1)
    for shape in source["price"].layout.shapes:
        fig.add_shape(shape)

    latest = float(f.close.iloc[-1])
    price_color = UP if latest >= float(f.open.iloc[-1]) else DOWN
    fig.add_hline(y=latest, line_dash="dot", line_color=price_color, line_width=.9, row=1, col=1)
    fig.add_annotation(x=1, xref="paper", y=latest, yref="y", xanchor="left",
                       text=f" {latest:.4f} ", showarrow=False, bgcolor=price_color,
                       font=dict(color="#FFFFFF", size=11), borderpad=3)
    visible = f.iloc[first:]
    lows, highs = [float(visible.low.min())], [float(visible.high.max())]
    if show_ma:
        for key in ("ma5", "ma20", "ma60"):
            if visible[key].notna().any():
                lows.append(float(visible[key].min()))
                highs.append(float(visible[key].max()))
    padding = max((max(highs) - min(lows)) * .09, latest * .002)
    fig.update_yaxes(range=[min(lows) - padding, max(highs) + padding], tickformat=".3f", row=1, col=1)
    _, scale_label = quantity_scale(f.volume, quantity_unit(result.metadata, "volume"))
    labels = ["日 K · 不复权 / 元", f"成交量 / {scale_label}"]
    labels += ["MACD  12 · 26 · 9" if p == "macd" else "RSI  14 · Wilder" for p in panels]
    for row, label in enumerate(labels, start=1):
        suffix = "" if row == 1 else str(row)
        fig.add_annotation(x=0, y=1, xref=f"x{suffix} domain", yref=f"y{suffix} domain",
                           text=label, showarrow=False, xanchor="left", yanchor="bottom",
                           font=dict(size=11, color=MUTED))
    fig.update_layout(
        template="plotly_white", height=760 if len(panels) == 2 else 640 if panels else 540,
        paper_bgcolor=PAPER, plot_bgcolor=PAPER, margin=dict(l=12, r=76, t=58, b=32),
        font=dict(family="-apple-system, BlinkMacSystemFont, PingFang SC, Microsoft YaHei, sans-serif", size=11, color=TEXT),
        xaxis_rangeslider_visible=False, bargap=.25, hovermode="x unified", hoversubplots="axis",
        hoverlabel=dict(bgcolor=PAPER, bordercolor=GRID, font=dict(size=12, color=TEXT)),
        legend=dict(orientation="h", x=0, y=1.06, yanchor="bottom", font=dict(size=10), tracegroupgap=4),
        dragmode="pan", uirevision=f"{result.symbol}:{result.start}:{result.end}:{months}:{oscillator}:{show_ma}:{result.metadata.get('fetched_at_max', result.metadata.get('fetched_at'))}")
    fig.update_xaxes(**axis, showline=True, linecolor=GRID)
    fig.update_yaxes(side="right", gridcolor=GRID, gridwidth=.6, zeroline=False, nticks=4,
                     tickfont=dict(color=MUTED, size=10), fixedrange=False,
                     showspikes=True, spikecolor=MUTED, spikethickness=1, spikedash="dot")
    fig.update_yaxes(nticks=3, row=2, col=1)
    for row in range(1, 2 + len(panels)):
        fig.update_xaxes(showticklabels=False, row=row, col=1)
    return fig
