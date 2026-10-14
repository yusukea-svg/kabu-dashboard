"""日次バッチ：銘柄一覧更新 → 全銘柄の日足取得 → 指標計算 → ユニバース判定 → 保存。

何度実行しても結果が同じになるように作る（upsert）。当日すでに成功していれば何もしない。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from ..config import Settings
from ..indicators import compute_all
from ..market_calendar import JST, is_trading_day
from ..notify import Notifier
from ..providers.base import DailyPriceProvider, ListingProvider
from ..signals import evaluate
from ..storage.base import Store
from ..universe import apply_universe
from .signal_notify import record_and_notify

log = logging.getLogger(__name__)

JOB = "daily"

SNAPSHOT_FIELDS = [
    "close", "change_pct", "volume", "avg_volume20", "avg_value20",
    "sma5", "sma25", "sma75", "sma200", "ema12", "ema26", "rsi14",
    "macd", "macd_signal", "macd_hist", "bb_upper", "bb_mid", "bb_lower",
]


@dataclass
class DailySummary:
    status: str
    ok: int = 0
    failed: int = 0
    universe: int = 0
    intraday: int = 0
    price_rows: int = 0
    notes: list[str] = field(default_factory=list)

    def message(self) -> str:
        parts = [f"取得成功 {self.ok}", f"失敗 {self.failed}", f"ユニバース {self.universe}",
                 f"場中対象 {self.intraday}", f"日足書込 {self.price_rows}行"]
        return " / ".join(parts + self.notes)


def _num(v):
    """JSON に載せられる値へ変換（NaN → None）。"""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        return round(v, 4)
    return v


def _already_done_today(store: Store, today: date) -> bool:
    last = store.latest_job_run(JOB)
    if not last:
        return False
    started = datetime.fromisoformat(last["started_at"]).astimezone(JST)
    return started.date() == today


def refresh_listings(store: Store, provider: ListingProvider, settings: Settings, force: bool) -> int | None:
    updated = store.securities_updated_at()
    if not force and updated and datetime.now(UTC) - updated < timedelta(days=settings.listing.refresh_days):
        return None
    listings = provider.fetch_listings()
    if len(listings) < 1000:
        # 取得ミスで全銘柄を無効化しないための安全装置
        raise RuntimeError(f"JPX一覧の件数が少なすぎます（{len(listings)}件）")
    before = set(store.list_active_codes())
    now = datetime.now(UTC).isoformat()
    rows = [{**vars(x), "is_active": True, "updated_at": now} for x in listings]
    gone = before - {x.code for x in listings}
    store.upsert("securities", rows, on_conflict="code")
    # 上場廃止等で一覧から消えた銘柄は is_active=false にする（履歴は保持期間が過ぎれば消える）
    store.deactivate_securities(sorted(gone))
    log.info("銘柄マスタ更新: %d 件（無効化 %d 件）", len(rows), len(gone))
    return len(rows)


def run_daily(
    settings: Settings,
    store: Store,
    prices: DailyPriceProvider,
    listing: ListingProvider,
    *,
    today: date | None = None,
    full: bool = False,
    force: bool = False,
    limit: int | None = None,
    notifier: Notifier | None = None,
) -> DailySummary:
    today = today or datetime.now(JST).date()

    if not force and not is_trading_day(today):
        run_id = store.start_job(JOB)
        store.finish_job(run_id, "skipped", 0, 0, "休場日")
        return DailySummary(status="skipped", notes=["休場日"])
    if not force and not full and _already_done_today(store, today):
        log.info("本日分は取得済みのため終了")
        return DailySummary(status="skipped", notes=["取得済み"])

    run_id = store.start_job(JOB)
    try:
        summary = _run(settings, store, prices, listing, today=today, full=full, limit=limit,
                       notifier=notifier or Notifier(""))
    except Exception as e:
        store.finish_job(run_id, "failed", 0, 0, f"{type(e).__name__}: {e}")
        raise
    store.finish_job(run_id, summary.status, summary.ok, summary.failed, summary.message())
    return summary


def _run(settings, store, prices, listing, *, today, full, limit, notifier) -> DailySummary:
    cfg = settings.daily
    refresh_listings(store, listing, settings, force=full)

    codes = store.list_active_codes()
    if limit:
        codes = codes[:limit]
    if not codes:
        raise RuntimeError("銘柄マスタが空です")

    start = today - timedelta(days=cfg.lookback_calendar_days)
    result = prices.fetch_daily(codes, start)

    price_rows: list[dict] = []
    snaps: list[dict] = []
    signal_rows: list[dict] = []
    all_dates: set[pd.Timestamp] = set()
    for code, df in result.prices.items():
        df = df.tail(cfg.history_trading_days)
        all_dates.update(df.index)
        write = df if (full or code in result.split_codes) else df.tail(cfg.upsert_recent_days)
        for d, r in write.iterrows():
            price_rows.append({
                "code": code, "date": d.date().isoformat(),
                "open": _num(r["open"]), "high": _num(r["high"]), "low": _num(r["low"]),
                "close": _num(r["close"]),
                "volume": int(r["volume"]) if pd.notna(r["volume"]) else None,
                "source": prices.source_id,
            })
        ind = compute_all(df)
        last = ind.iloc[-1]
        as_of = ind.index[-1].date().isoformat()
        snaps.append({"code": code, "as_of": as_of, **{k: last.get(k) for k in SNAPSHOT_FIELDS}})
        for rule, detail in evaluate(ind, settings.signals.rules):
            signal_rows.append({"code": code, "kind": rule.id, "timeframe": "daily",
                                "trade_date": as_of, "detail": {**detail, "label": rule.label}})

    summary = DailySummary(status="ok", ok=len(result.prices), failed=len(result.failed))
    if not snaps:
        summary.status = "failed"
        summary.notes.append("1銘柄も取得できませんでした")
        return summary

    snap_df = apply_universe(pd.DataFrame(snaps), settings.universe)
    now = datetime.now(UTC).isoformat()
    # 引け後の確定値で上書きするので、場中の暫定値は消す
    snap_rows = [
        {k: _num(v) for k, v in r.items()} | {"updated_at": now, "last_price": None, "last_price_at": None}
        for r in snap_df.to_dict("records")
    ]
    for r in snap_rows:
        if r["volume"] is not None:
            r["volume"] = int(r["volume"])

    summary.price_rows = store.upsert("daily_prices", price_rows, on_conflict="code,date")
    store.upsert("snapshots", snap_rows, on_conflict="code")
    summary.universe = int(snap_df["in_universe"].sum())
    summary.intraday = int(snap_df["intraday_rank"].notna().sum())

    # シグナル：記録はユニバース全体、通知は設定の範囲だけ
    universe_codes = set(snap_df.loc[snap_df["in_universe"], "code"])
    intraday_codes = set(snap_df.loc[snap_df["intraday_rank"].notna(), "code"])
    notify_codes = intraday_codes if settings.signals.notify_scope == "intraday" else universe_codes
    new, sent = record_and_notify(
        store, notifier, settings.signals,
        [r for r in signal_rows if r["code"] in universe_codes],
        timeframe="daily", trade_date=today, notify_codes=notify_codes,
        title=f"📊 日次シグナル {today:%m/%d}（引け後・確定値）",
    )
    summary.notes.append(f"シグナル新規 {new} / 通知 {sent}")

    # 保持期間より古い日足を削除
    dates = sorted(all_dates)
    if len(dates) >= cfg.history_trading_days:
        store.delete_daily_prices_before(dates[-cfg.history_trading_days].date())

    fail_ratio = summary.failed / max(len(codes), 1)
    if fail_ratio > 0.05:
        summary.status = "partial"
    if result.split_codes:
        summary.notes.append(f"分割検知 {len(result.split_codes)}")
    return summary
