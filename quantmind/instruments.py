"""Supported ETF identifiers and display names."""

ETF_NAMES = {
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
}


def normalize_symbol(symbol: str) -> str:
    code = str(symbol).strip()
    if code not in ETF_NAMES:
        raise ValueError(f"不支持的 ETF 代码：{code}；支持 {', '.join(ETF_NAMES)}")
    return code
