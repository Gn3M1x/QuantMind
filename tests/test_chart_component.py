"""Offline TEST samples verify the component consumes the existing Analysis snapshot."""
import json

import pandas as pd

from quantmind.analysis import analyze
from quantmind.chart_component import ASSETS, chart_payload
from quantmind.charts import build_workspace


def test_payload_preserves_precision_gaps_and_single_analysis(make_bars, metadata):
    bars = make_bars(close=[10.12345678,11.1,12.2])
    bars['date'] = pd.to_datetime(['2025-09-26','2025-09-29','2025-10-08'])
    result = analyze('510300',bars,'2025-09-26','2025-10-08',metadata)
    before = result.frame.copy(deep=True)
    p = chart_payload(result,build_workspace(result),'TEST-query-1',None)
    assert p['dates'] == ['2025-09-26','2025-09-29','2025-10-08']
    assert p['observations']['low'][0] == 9.62345678
    assert p['observations']['ma20'] == [None,None,None]
    assert p['queryId'] == 'TEST-query-1' and p['rangeKey'] == 'None'
    assert not p['config']['scrollZoom']
    json.dumps(p,allow_nan=False)
    pd.testing.assert_frame_equal(result.frame,before)


def test_local_component_assets_ship_without_remote_dependencies():
    html = (ASSETS/'index.html').read_text()
    assert 'https://' not in html and 'http://' not in html
    for filename in ('viewport.js','controller.js','chart.css','plotly.min.js','PLOTLY-LICENSE.txt'):
        assert (ASSETS/filename).is_file()
    assert 'plotly.js v3.7.0' in (ASSETS/'plotly.min.js').read_text()[:200]


def test_browsable_records_exclude_warmup_even_when_ma_uses_it(make_bars, metadata):
    bars = make_bars(count=70)
    start, end = bars.date.iloc[-3].strftime('%Y-%m-%d'), bars.date.iloc[-1].strftime('%Y-%m-%d')
    result = analyze('510300',bars,start,end,metadata)
    p = chart_payload(result,build_workspace(result),'TEST-selected-only',None)
    assert result.prehistory_count == 67
    assert len(p['dates']) == len(p['observations']['low']) == 3
    assert p['dates'][0] == start
    assert p['observations']['ma60'] == [38.5,39.5,40.5]
    assert p['figure']['layout']['xaxis']['range'] == [-.5,2.5]
    # A one-record date selection has one whole candle slot, no future padding.
    single = analyze('510300',bars,end,end,metadata)
    assert build_workspace(single).layout.xaxis.range == (-.5,.5)
