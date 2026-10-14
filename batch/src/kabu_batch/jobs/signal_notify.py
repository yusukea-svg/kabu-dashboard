"""シグナルの記録と Discord 通知（日次・場中で共通）。"""

from __future__ import annotations

import logging
from datetime import date

from ..config import SignalConfig
from ..notify import DISCLAIMER, Notifier, dashboard_link
from ..storage.base import Store

log = logging.getLogger(__name__)


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.1f}円" if v < 1000 else f"{v:,.0f}円"


def build_message(title: str, hits: list[dict], cfg: SignalConfig, names: dict[str, str]) -> str:
    labels = {r.id: r.label for r in cfg.rules}
    lines = [f"**{title}**"]
    for rule in cfg.rules:
        group = [h for h in hits if h["kind"] == rule.id]
        if not group:
            continue
        lines.append(f"\n**{labels[rule.id]}**　{len(group)}件")
        for h in group[: cfg.notify_max_per_rule]:
            close = (h.get("detail") or {}).get("close")
            lines.append(f"・{h['code']} {names.get(h['code'], '')}　{_fmt_price(close)}")
        if len(group) > cfg.notify_max_per_rule:
            lines.append(f"…ほか {len(group) - cfg.notify_max_per_rule} 件（ダッシュボードで確認）")
    if link := dashboard_link():
        lines.append(f"\n{link}")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def record_and_notify(
    store: Store,
    notifier: Notifier,
    cfg: SignalConfig,
    rows: list[dict],
    *,
    timeframe: str,
    trade_date: date,
    notify_codes: set[str],
    title: str,
) -> tuple[int, int]:
    """rows を記録し、新規かつ通知対象のものを1通にまとめて送る。(新規件数, 通知件数) を返す。"""
    if not rows:
        return 0, 0
    inserted = store.insert_signals(rows)
    notify_rules = {r.id for r in cfg.rules if r.notify}
    # 引け後の日次では、同じ日に場中で通知済みのもの（銘柄・種類が同じ）は送らない
    already = store.notified_signal_keys(trade_date, "intraday") if timeframe == "daily" else set()
    to_send = [
        r for r in inserted
        if r["kind"] in notify_rules and r["code"] in notify_codes and (r["code"], r["kind"]) not in already
    ]
    if to_send:
        names = store.security_names()
        notifier.send(build_message(title, to_send, cfg, names))
        # 実際に送ったときだけ「通知済み」にする（Webhook未設定・--no-notify のときは記録のみ）
        if notifier.enabled:
            store.mark_notified([r["id"] for r in to_send])
    log.info("シグナル: 記録 %d 件（新規 %d）/ 通知 %d 件", len(rows), len(inserted), len(to_send))
    return len(inserted), len(to_send)
