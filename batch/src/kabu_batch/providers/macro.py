"""マクロ指標の取得：指数・為替・商品は yfinance、米金利は FRED。

FRED の API キーは URL に入るので、URL をログやエラーに出さない。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import httpx
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class MacroSeries:
    series_id: str
    label: str
    category: str
    unit: str
    source: str
    sort_order: int
    values: pd.Series  # index: date, values: float


def fetch_yfinance(items: list[dict], start: date, order_base: int = 0) -> tuple[list[MacroSeries], list[str]]:
    import yfinance as yf

    tickers = [i["ticker"] for i in items]
    raw = yf.download(tickers, start=start.isoformat(), interval="1d", group_by="ticker",
                      auto_adjust=True, progress=False, threads=True, multi_level_index=True)
    out, failed = [], []
    top = set(raw.columns.get_level_values(0)) if raw is not None and not raw.empty else set()
    for n, item in enumerate(items):
        t = item["ticker"]
        if t not in top:
            failed.append(t)
            continue
        close = raw[t]["Close"].dropna()
        if close.empty:
            failed.append(t)
            continue
        close.index = pd.to_datetime(close.index).tz_localize(None).date
        out.append(MacroSeries(f"yf:{t}", item["label"], item["category"], item.get("unit", ""),
                               "yfinance", order_base + n, close.astype(float)))
    return out, failed


def fetch_fred(items: list[dict], start: date, api_key: str, order_base: int = 100) -> tuple[list[MacroSeries], list[str]]:
    out, failed = [], []
    with httpx.Client(timeout=30) as client:
        for n, item in enumerate(items):
            sid = item["series"]
            try:
                r = client.get("https://api.stlouisfed.org/fred/series/observations", params={
                    "series_id": sid, "api_key": api_key, "file_type": "json",
                    "observation_start": start.isoformat(),
                })
                if r.status_code != 200:
                    log.warning("FRED %s: HTTP %d", sid, r.status_code)  # URL にキーが含まれるので出さない
                    failed.append(sid)
                    continue
                obs = [(o["date"], o["value"]) for o in r.json().get("observations", []) if o["value"] not in (".", "")]
            except httpx.HTTPError as e:
                log.warning("FRED %s: %s", sid, type(e).__name__)
                failed.append(sid)
                continue
            if not obs:
                failed.append(sid)
                continue
            s = pd.Series([float(v) for _, v in obs], index=[date.fromisoformat(d) for d, _ in obs])
            out.append(MacroSeries(f"fred:{sid}", item["label"], item["category"], item.get("unit", ""),
                                   "FRED", order_base + n, s))
    return out, failed
