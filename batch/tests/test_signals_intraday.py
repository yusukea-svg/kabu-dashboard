from datetime import date, datetime

import numpy as np
import pandas as pd

from kabu_batch.config import (
    DailyFetchConfig,
    IntradayConfig,
    ListingConfig,
    Settings,
    SignalConfig,
    SignalRule,
    UniverseConfig,
)
from kabu_batch.jobs.intraday import run_intraday
from kabu_batch.jobs.signal_notify import build_message, record_and_notify
from kabu_batch.market_calendar import JST
from kabu_batch.notify import Notifier, split_message
from kabu_batch.providers.base import PriceFetchResult
from kabu_batch.signals import evaluate, triggered
from kabu_batch.storage.base import MemoryStore

GC = SignalRule(id="gc", label="GC", type="cross_up", fast="sma25", slow="sma75")
RSI30 = SignalRule(id="rsi30", label="RSI30", type="threshold_down", field="rsi14", value=30)
SIG = SignalConfig(rules=[GC, RSI30], notify_scope="intraday", notify_max_per_rule=2)


class FakeNotifier(Notifier):
    """送信せずに記録だけする（enabled 扱い）。"""

    def __init__(self):
        super().__init__("https://example.invalid/webhook")

    def send(self, text: str) -> None:
        self.sent.append(text)


def s(**kw):
    return pd.Series(kw, dtype="float64")


def test_cross_and_threshold():
    assert triggered(GC, s(sma25=99, sma75=100), s(sma25=101, sma75=100))
    assert not triggered(GC, s(sma25=101, sma75=100), s(sma25=102, sma75=100))  # 既に上
    assert not triggered(GC, s(sma25=np.nan, sma75=100), s(sma25=101, sma75=100))
    assert triggered(RSI30, s(rsi14=31), s(rsi14=29))
    assert not triggered(RSI30, s(rsi14=29), s(rsi14=28))


def test_evaluate_returns_detail():
    df = pd.DataFrame({"close": [10, 11], "sma25": [9, 11], "sma75": [10, 10], "rsi14": [50, 50]})
    hits = evaluate(df, [GC, RSI30])
    assert [r.id for r, _ in hits] == ["gc"]
    assert hits[0][1] == {"close": 11.0, "sma25": 11.0, "sma75": 10.0}


def test_split_message_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    chunks = split_message(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert "\n".join(chunks).count("line ") == 100


def test_build_message_truncates_per_rule():
    hits = [{"code": c, "kind": "gc", "detail": {"close": 1234.0}} for c in ["1", "2", "3"]]
    msg = build_message("T", hits, SIG, {"1": "A社"})
    assert "・1 A社　1,234円" in msg and "ほか 1 件" in msg and "投資助言ではありません" in msg


def test_record_and_notify_dedupes_and_skips_intraday_already_sent():
    store, n = MemoryStore(), FakeNotifier()
    d = date(2026, 10, 15)
    row = {"code": "1", "kind": "gc", "timeframe": "intraday", "trade_date": d.isoformat(), "detail": {}}
    assert record_and_notify(store, n, SIG, [row], timeframe="intraday", trade_date=d,
                             notify_codes={"1"}, title="場中") == (1, 1)
    # 同じものをもう一度 → 新規0・通知0
    assert record_and_notify(store, n, SIG, [row], timeframe="intraday", trade_date=d,
                             notify_codes={"1"}, title="場中") == (0, 0)
    # 引け後の日次で同じ銘柄・種類 → 記録はするが通知しない
    daily = {**row, "timeframe": "daily"}
    assert record_and_notify(store, n, SIG, [daily], timeframe="daily", trade_date=d,
                             notify_codes={"1"}, title="日次") == (1, 0)
    # 通知範囲外の銘柄は通知しない
    other = {**daily, "code": "2"}
    assert record_and_notify(store, n, SIG, [other], timeframe="daily", trade_date=d,
                             notify_codes={"1"}, title="日次") == (1, 0)
    assert len(n.sent) == 1


def prices_ending(end: str, n: int = 320, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    idx = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close,
                         "volume": rng.integers(1e5, 1e6, n)}, index=idx)


class FakePrices:
    source_id = 9

    def __init__(self, frames):
        self.frames = frames

    def fetch_daily(self, codes, start):
        r = PriceFetchResult()
        for c in codes:
            if c in self.frames:
                r.prices[c] = self.frames[c]
            else:
                r.failed.append(c)
        return r


def settings():
    return Settings(universe=UniverseConfig(), listing=ListingConfig(), daily=DailyFetchConfig(),
                    intraday=IntradayConfig(), signals=SIG)


def seeded_store():
    store = MemoryStore()
    for i, code in enumerate(["A", "B", "C"]):
        store.upsert("snapshots", [{"code": code, "intraday_rank": i + 1, "in_universe": True}], "code")
    return store


def test_intraday_updates_last_price():
    store = seeded_store()
    frames = {"A": prices_ending("2026-10-15"), "B": prices_ending("2026-10-14")}  # B は当日値なし、C は失敗
    now = datetime(2026, 10, 15, 12, 5, tzinfo=JST)
    out = run_intraday(settings(), store, FakePrices(frames), now=now)
    assert (out.updated, out.no_today_bar, out.failed) == (1, 1, 1)
    snaps = store.tables["snapshots"]
    assert snaps[("A",)]["last_price"] == frames["A"]["close"].iloc[-1]
    assert snaps[("B",)].get("last_price") is None
    assert store.jobs[-1]["status"] == "partial"


def test_intraday_skips_outside_window_and_holiday():
    store = seeded_store()
    late = datetime(2026, 10, 15, 17, 30, tzinfo=JST)
    assert run_intraday(settings(), store, FakePrices({}), now=late).status == "skipped"
    sat = datetime(2026, 10, 17, 12, 5, tzinfo=JST)
    assert run_intraday(settings(), store, FakePrices({}), now=sat).status == "skipped"
