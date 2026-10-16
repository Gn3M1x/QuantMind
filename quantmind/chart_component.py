"""Local chart component. Only analysis snapshots enter the browser; no data fetches."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit.components.v1 as components

from .analysis import Analysis
from .charts import PLOT_CONFIG

ASSETS = Path(__file__).parent / "assets" / "chart"
_chart = components.declare_component("quantmind_chart", path=str(ASSETS))


def chart_payload(result: Analysis, figure: go.Figure, query_id: str, months: int | None) -> dict:
    """JSON-only data channel, never interpolate upstream data into executable HTML."""
    observations = {
        key: [None if pd.isna(v) else float(v) for v in result.frame[key]]
        for key in ("low", "high", "ma5", "ma20", "ma60")
    }
    return {
        "queryId": query_id,
        "rangeKey": str(months),
        "figure": json.loads(figure.to_json()),
        "observations": observations,
        "dates": result.frame.date.dt.strftime("%Y-%m-%d").tolist(),
        "config": PLOT_CONFIG | {"scrollZoom": False, "doubleClick": False, "responsive": True},
    }


def render_chart(result: Analysis, figure: go.Figure, query_id: str, months: int | None) -> None:
    _chart(payload=chart_payload(result, figure, query_id, months), key="workspace")
