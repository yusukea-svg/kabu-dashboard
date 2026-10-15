"""世界情勢・企業情報の取得（マクロ指標・ニュース・EDINET開示）。

3つは独立して動かし、1つが失敗しても他は保存する。それぞれ job_runs に記録する
（画面の「最終更新時刻」に使う）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ..market_calendar import JST
from ..providers.edinet import EdinetClient, parse_documents
from ..providers.macro import fetch_fred, fetch_yfinance
from ..providers.news import fetch_feeds
from ..storage.base import Store

log = logging.getLogger(__name__)

PARTS = ("macro", "news", "edinet")


@dataclass
class PartResult:
    job: str
    status: str
    ok: int = 0
    failed: int = 0
    message: str = ""


def _record(store: Store, job: str, fn: Callable[[], PartResult]) -> PartResult:
    run_id = store.start_job(job)
    try:
        r = fn()
    except Exception as e:
        log.exception("%s 失敗", job)
        r = PartResult(job, "failed", message=f"{type(e).__name__}")
    store.finish_job(run_id, r.status, r.ok, r.failed, r.message)
    log.info("[%s] %s: %s", job, r.status, r.message)
    return r


def run_macro(store: Store, cfg: dict, today: date) -> PartResult:
    start = today - timedelta(days=cfg.get("history_days", 400))
    series, failed = fetch_yfinance(cfg.get("yfinance", []), start)
    fred_key = os.environ.get("FRED_API_KEY", "").strip()
    note = ""
    if cfg.get("fred"):
        if fred_key:
            s2, f2 = fetch_fred(cfg["fred"], start, fred_key)
            series += s2
            failed += f2
        else:
            note = "（FRED_API_KEY 未設定のため米金利はスキップ）"
    now = datetime.now(UTC).isoformat()
    store.upsert("macro_meta", [
        {"series_id": s.series_id, "label": s.label, "category": s.category, "unit": s.unit,
         "source": s.source, "sort_order": s.sort_order, "updated_at": now} for s in series
    ], on_conflict="series_id")
    rows = [{"series_id": s.series_id, "date": d.isoformat(), "value": round(float(v), 6)}
            for s in series for d, v in s.values.items()]
    store.upsert("macro_series", rows, on_conflict="series_id,date")
    store.delete_where_lt("macro_series", "date", start.isoformat())
    status = "ok" if not failed else ("partial" if series else "failed")
    return PartResult("macro", status, len(series), len(failed),
                      f"系列 {len(series)} / 失敗 {len(failed)} {note}".strip())


def run_news(store: Store, cfg: dict, today: date) -> PartResult:
    rows, failed = fetch_feeds(cfg.get("feeds", []))
    store.upsert("news", rows, on_conflict="id")
    cutoff = datetime.now(UTC) - timedelta(days=cfg.get("keep_days", 14))
    store.delete_where_lt("news", "fetched_at", cutoff.isoformat())
    status = "ok" if not failed else ("partial" if rows else "failed")
    return PartResult("news", status, len(rows), len(failed), f"記事 {len(rows)} / 失敗フィード {len(failed)}")


def run_edinet(store: Store, cfg: dict, today: date, client: EdinetClient | None = None) -> PartResult:
    key = os.environ.get("EDINET_API_KEY", "").strip()
    if client is None and not key:
        return PartResult("edinet", "skipped", message="EDINET_API_KEY 未設定")
    client = client or EdinetClient(key)
    latest = store.max_value("disclosures", "submitted_at")
    days = cfg.get("lookback_days", 7) if latest else cfg.get("initial_days", 120)
    codes = set(store.list_active_codes())
    doc_types = {str(k): v for k, v in cfg.get("doc_types", {}).items()}
    rows: list[dict] = []
    failed_days = 0
    for i in range(days, -1, -1):
        day = today - timedelta(days=i)
        if day.weekday() >= 5:
            continue  # 土日は提出がない
        try:
            rows += parse_documents(client.list_documents(day), doc_types, codes)
        except Exception as e:
            log.warning("EDINET %s: %s", day, type(e).__name__)
            failed_days += 1
    store.upsert("disclosures", rows, on_conflict="id")
    status = "ok" if failed_days == 0 else "partial"
    return PartResult("edinet", status, len(rows), failed_days, f"書類 {len(rows)} / 失敗日 {failed_days}（{days}日分）")


def run_info(store: Store, sources: dict, parts: list[str], today: date | None = None) -> list[PartResult]:
    today = today or datetime.now(JST).date()
    jobs = {
        "macro": lambda: run_macro(store, sources.get("macro", {}), today),
        "news": lambda: run_news(store, sources.get("news", {}), today),
        "edinet": lambda: run_edinet(store, sources.get("edinet", {}), today),
    }
    return [_record(store, p, jobs[p]) for p in parts]
