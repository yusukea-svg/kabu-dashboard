from datetime import date, datetime

import pandas as pd

from kabu_batch.config import UniverseConfig
from kabu_batch.market_calendar import JST, is_market_open, is_trading_day, previous_trading_day
from kabu_batch.universe import apply_universe

CFG = UniverseConfig(price_min=100, price_max=5000, avg_volume20_min=30_000,
                     avg_value20_min=30_000_000, intraday_max_count=2)


def test_universe_filters_and_ranks():
    df = pd.DataFrame([
        {"code": "A", "close": 1000, "avg_volume20": 100_000, "avg_value20": 1e8},
        {"code": "B", "close": 50, "avg_volume20": 1e7, "avg_value20": 5e8},     # 株価が低すぎ
        {"code": "C", "close": 6000, "avg_volume20": 1e6, "avg_value20": 6e9},   # 株価が高すぎ
        {"code": "D", "close": 500, "avg_volume20": 20_000, "avg_value20": 1e7},  # 出来高不足
        {"code": "E", "close": 3000, "avg_volume20": 200_000, "avg_value20": 6e8},
        {"code": "F", "close": 200, "avg_volume20": 200_000, "avg_value20": 4e7},
        {"code": "G", "close": 800, "avg_volume20": float("nan"), "avg_value20": float("nan")},
    ])
    out = apply_universe(df, CFG).set_index("code")
    assert out["in_universe"].to_dict() == {
        "A": True, "B": False, "C": False, "D": False, "E": True, "F": True, "G": False}
    # 売買代金の大きい順に上位2件
    assert out.loc["E", "intraday_rank"] == 1
    assert out.loc["A", "intraday_rank"] == 2
    assert pd.isna(out.loc["F", "intraday_rank"])


def test_trading_days():
    assert not is_trading_day(date(2026, 10, 17))  # 土曜
    assert not is_trading_day(date(2026, 11, 3))   # 文化の日
    assert not is_trading_day(date(2026, 12, 31))
    assert not is_trading_day(date(2027, 1, 2))
    assert is_trading_day(date(2026, 10, 15))
    assert previous_trading_day(date(2026, 10, 19)) == date(2026, 10, 16)


def test_find_listing_link():
    from kabu_batch.providers.jpx_listing import find_listing_link

    page = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
    html = '<a href="/markets/x-att/data_j.xlsx">一覧</a><a href="/other.pdf">'
    assert find_listing_link(html, page) == "https://www.jpx.co.jp/markets/x-att/data_j.xlsx"
    assert find_listing_link("<html></html>", page) is None


def test_market_hours():
    assert is_market_open(datetime(2026, 10, 15, 9, 0, tzinfo=JST))
    assert not is_market_open(datetime(2026, 10, 15, 12, 0, tzinfo=JST))  # 昼休み
    assert is_market_open(datetime(2026, 10, 15, 15, 30, tzinfo=JST))
    assert not is_market_open(datetime(2026, 10, 15, 15, 31, tzinfo=JST))
