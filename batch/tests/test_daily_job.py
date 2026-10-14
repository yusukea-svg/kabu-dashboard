from datetime import date

import pytest

from kabu_batch.config import DailyFetchConfig, ListingConfig, Settings, UniverseConfig
from kabu_batch.jobs.daily import run_daily
from kabu_batch.providers.base import Listing, PriceFetchResult
from kabu_batch.storage.base import MemoryStore

from .test_indicators import synthetic_prices

TODAY = date(2026, 10, 15)


class FakeListing:
    def __init__(self, n=1200):
        self.n = n

    def fetch_listings(self):
        return [Listing(code=f"{1000 + i}", name=f"銘柄{i}", market="プライム（内国株式）")
                for i in range(self.n)]


class FakePrices:
    source_id = 9

    def __init__(self, fail=(), split=()):
        self.fail, self.split = set(fail), set(split)
        self.calls = []

    def fetch_daily(self, codes, start):
        self.calls.append((list(codes), start))
        r = PriceFetchResult()
        for i, c in enumerate(codes):
            if c in self.fail:
                r.failed.append(c)
            else:
                r.prices[c] = synthetic_prices(320, seed=i)
        r.split_codes = self.split & set(r.prices)
        return r


def settings(**daily):
    return Settings(
        universe=UniverseConfig(intraday_max_count=3, avg_volume20_min=0, avg_value20_min=0,
                                price_min=0, price_max=1e9),
        listing=ListingConfig(page_url="x", refresh_days=7),
        daily=DailyFetchConfig(history_trading_days=300, upsert_recent_days=10),
    )


def test_daily_end_to_end():
    store = MemoryStore()
    prices = FakePrices(fail={"1002"}, split={"1001"})
    s = run_daily(settings(), store, prices, FakeListing(), today=TODAY, limit=5)

    assert s.status == "ok" or s.status == "partial"
    assert s.ok == 4 and s.failed == 1
    snaps = store.tables["snapshots"]
    assert len(snaps) == 4
    assert sum(1 for v in snaps.values() if v["intraday_rank"] is not None) == 3
    rows = store.tables["daily_prices"]
    # 通常銘柄は直近10日、分割銘柄は全300日
    per_code = {}
    for (code, _d) in rows:
        per_code[code] = per_code.get(code, 0) + 1
    assert per_code["1001"] == 300
    assert per_code["1000"] == 10
    assert store.deleted_before is not None
    assert store.jobs[-1]["status"] in ("ok", "partial")
    # NaN が JSON に混ざらない
    for v in snaps.values():
        assert all(not (isinstance(x, float) and x != x) for x in v.values())


def test_holiday_is_skipped():
    store = MemoryStore()
    s = run_daily(settings(), store, FakePrices(), FakeListing(), today=date(2026, 10, 17))
    assert s.status == "skipped"
    assert store.jobs[-1]["status"] == "skipped"


def test_listing_too_small_is_rejected():
    store = MemoryStore()
    with pytest.raises(RuntimeError):
        run_daily(settings(), store, FakePrices(), FakeListing(n=10), today=TODAY)
    assert store.jobs[-1]["status"] == "failed"
