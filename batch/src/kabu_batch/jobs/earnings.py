"""今週・来週の決算発表予定を日付別にまとめて Discord に送る（毎週月曜）。

対象銘柄は config/sources.yaml の earnings.scope で選ぶ。
  universe : ユニバース（20日平均売買代金の大きい順）
  intraday : 場中更新の対象
  all      : JPXの一覧にある全銘柄（コード順）
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

from ..market_calendar import JST
from ..notify import DISCLAIMER, Notifier, dashboard_link
from ..providers.jpx_earnings import EarningsEvent
from ..storage.base import Store

log = logging.getLogger(__name__)

JOB = "earnings"
WEEKDAYS = "月火水木金土日"
SCOPE_LABELS = {"universe": "ユニバース", "intraday": "場中更新の対象", "all": "全上場銘柄"}


def week_window(today: date) -> tuple[date, date]:
    """今週の月曜〜来週の日曜。"""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=13)


def _md(d: date) -> str:
    return f"{d.month}/{d.day}"


def build_message(events: list[EarningsEvent], start: date, end: date, *, order: dict[str, int],
                  scope: str, max_per_day: int) -> str:
    next_monday = start + timedelta(days=7)
    lines = [f"**📅 決算発表予定　{_md(start)}〜{_md(end)}**（{SCOPE_LABELS.get(scope, scope)}）"]
    if not events:
        lines.append("\n今週・来週に決算発表の予定はありません（JPX掲載分）。")
    for week_label, w_start in (("今週", start), ("来週", next_monday)):
        in_week = [e for e in events if w_start <= e.date < w_start + timedelta(days=7)]
        if not events:
            break
        lines.append(f"\n__**{week_label}**__　{len(in_week)}社")
        if not in_week:
            lines.append("予定なし")
        for d in sorted({e.date for e in in_week}):
            day = sorted((e for e in in_week if e.date == d), key=lambda e: (order.get(e.code, len(order)), e.code))
            lines.append(f"**{_md(d)}（{WEEKDAYS[d.weekday()]}）**　{len(day)}社")
            shown = day[:max_per_day] if max_per_day > 0 else day
            for e in shown:
                kind = f"　{e.kind}" if e.kind else ""
                lines.append(f"・{e.code} {e.name}{kind}")
            if len(day) > len(shown):
                lines.append(f"…ほか {len(day) - len(shown)} 社")
    lines.append("\n※JPX「決算発表予定日」より。日付は変更されることがあります。")
    if link := dashboard_link():
        lines.append(link)
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def _sent_today(store: Store, today: date) -> bool:
    last = store.latest_job_run(JOB)
    started = (last or {}).get("started_at")
    if not started:
        return False
    return datetime.fromisoformat(str(started)).astimezone(JST).date() == today


def run_earnings(store: Store, fetch_events: Callable[[], list[EarningsEvent]], notifier: Notifier, cfg: dict,
                 today: date, *, force: bool = False) -> str:
    """結果の要約を返す。同じ日に送信済みなら何もしない（予備の cron 用）。"""
    if not force and _sent_today(store, today):
        return "本日は送信済みのためスキップ"
    run_id = store.start_job(JOB)
    try:
        scope = cfg.get("scope", "universe")
        max_per_day = int(cfg.get("max_per_day", 30))
        start, end = week_window(today)
        events = [e for e in fetch_events() if start <= e.date <= end]
        if scope == "all":
            order: dict[str, int] = {}
        else:
            codes = store.intraday_targets() if scope == "intraday" else store.universe_by_value()
            order = {c: i for i, c in enumerate(codes)}
            events = [e for e in events if e.code in order]
        notifier.send(build_message(events, start, end, order=order, scope=scope, max_per_day=max_per_day))
        msg = f"{start}〜{end} の予定 {len(events)} 件を通知"
    except Exception as e:
        store.finish_job(run_id, "failed", 0, 1, type(e).__name__)
        raise
    store.finish_job(run_id, "ok", len(events), 0, msg)
    log.info(msg)
    return msg
