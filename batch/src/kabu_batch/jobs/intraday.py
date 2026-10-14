"""場中バッチ（12:05 / 15:05 JST）：場中更新の対象銘柄だけ、当日の暫定値で現在値と指標・シグナルを更新する。

yfinance の日足は場中だと「当日の途中までの値」を返す（約20分遅延）。
当日の暫定日足は daily_prices には書かない（18時の日次で確定値を書く）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from ..config import Settings
from ..indicators import compute_all
from ..market_calendar import JST, is_trading_day
from ..notify import Notifier
from ..providers.base import DailyPriceProvider
from ..signals import evaluate
from ..storage.base import Store
from .signal_notify import record_and_notify

log = logging.getLogger(__name__)

JOB = "intraday"


@dataclass
class IntradaySummary:
    status: str
    targets: int = 0
    updated: int = 0
    failed: int = 0
    no_today_bar: int = 0
    signals_new: int = 0
    signals_sent: int = 0
    note: str = ""

    def message(self) -> str:
        if self.note:
            return self.note
        return (f"対象 {self.targets} / 更新 {self.updated} / 失敗 {self.failed} / 当日値なし {self.no_today_bar}"
                f" / シグナル新規 {self.signals_new} / 通知 {self.signals_sent}")


def _in_window(now: datetime, start: str, end: str) -> bool:
    t = now.astimezone(JST).time()
    return time.fromisoformat(start) <= t <= time.fromisoformat(end)


def run_intraday(
    settings: Settings,
    store: Store,
    prices: DailyPriceProvider,
    *,
    now: datetime | None = None,
    force: bool = False,
    limit: int | None = None,
    notifier: Notifier | None = None,
) -> IntradaySummary:
    now = (now or datetime.now(JST)).astimezone(JST)
    today = now.date()
    cfg = settings.intraday

    if not force:
        reason = None
        if not is_trading_day(today):
            reason = "休場日"
        elif not _in_window(now, cfg.window_start, cfg.window_end):
            reason = f"時間外の起動（{now:%H:%M}）"
        if reason:
            run_id = store.start_job(JOB)
            store.finish_job(run_id, "skipped", 0, 0, reason)
            return IntradaySummary(status="skipped", note=reason)

    run_id = store.start_job(JOB)
    try:
        summary = _run(settings, store, prices, now=now, limit=limit, notifier=notifier or Notifier(""))
    except Exception as e:
        store.finish_job(run_id, "failed", 0, 0, f"{type(e).__name__}: {e}")
        raise
    store.finish_job(run_id, summary.status, summary.updated, summary.failed, summary.message())
    return summary


def _run(settings: Settings, store: Store, prices: DailyPriceProvider, *, now, limit, notifier) -> IntradaySummary:
    today = now.date()
    codes = store.intraday_targets()
    if limit:
        codes = codes[:limit]
    if not codes:
        return IntradaySummary(status="skipped", note="場中更新の対象がありません（日次バッチが未実行）")

    start = today - timedelta(days=settings.daily.lookback_calendar_days)
    result = prices.fetch_daily(codes, start)

    s = IntradaySummary(status="ok", targets=len(codes), failed=len(result.failed))
    last_rows: list[dict] = []
    signal_rows: list[dict] = []
    for code, df in result.prices.items():
        df = df.tail(settings.daily.history_trading_days)
        if df.index[-1].date() != today:
            s.no_today_bar += 1  # 寄り付き前・売買停止など
            continue
        last_rows.append({"code": code, "last_price": float(df["close"].iloc[-1]),
                          "last_price_at": now.isoformat()})
        for rule, detail in evaluate(compute_all(df), settings.signals.rules):
            signal_rows.append({"code": code, "kind": rule.id, "timeframe": "intraday",
                                "trade_date": today.isoformat(), "detail": {**detail, "label": rule.label}})

    s.updated = store.update_last_prices(last_rows) if last_rows else 0
    s.signals_new, s.signals_sent = record_and_notify(
        store, notifier, settings.signals, signal_rows,
        timeframe="intraday", trade_date=today, notify_codes=set(codes),
        title=f"⏱ 場中シグナル {now:%m/%d %H:%M}時点（約20分遅延・暫定値）",
    )
    if s.updated == 0 or s.failed / len(codes) > 0.05:
        s.status = "partial"
    return s
