"""場中更新の対象数 N を決めるための実測（GitHub Actions 上で手動実行する）。

売買代金の大きい順に N 銘柄を、場中バッチと同じ方法で取得し、成功率と所要時間を測る。
再試行はしない（素の成功率を見るため）。結果は job_runs と Discord に残す。価格はどこにも出さない。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import Settings
from ..market_calendar import JST
from ..notify import Notifier
from ..providers.base import DailyPriceProvider
from ..storage.base import Store

log = logging.getLogger(__name__)

JOB = "bench"


@dataclass
class BenchRow:
    size: int
    ok: int
    failed: int
    seconds: float

    @property
    def rate(self) -> float:
        return self.ok / self.size if self.size else 0.0


def format_report(rows: list[BenchRow], started: datetime, runner: str) -> str:
    lines = [f"**🧪 取得件数の実測** {started:%m/%d %H:%M} JST（{runner}）", "```",
             "   N  成功  失敗  成功率   秒数"]
    for r in rows:
        lines.append(f"{r.size:4d} {r.ok:5d} {r.failed:5d} {r.rate:6.1%} {r.seconds:6.1f}")
    lines.append("```")
    return "\n".join(lines)


def run_bench(
    settings: Settings,
    store: Store,
    make_provider: Callable[[], DailyPriceProvider],
    sizes: list[int],
    *,
    pause_seconds: float = 60,
    notifier: Notifier | None = None,
    runner: str = "local",
) -> list[BenchRow]:
    notifier = notifier or Notifier("")
    started = datetime.now(JST)
    run_id = store.start_job(JOB)
    try:
        codes = store.universe_by_value()
        if not codes:
            raise RuntimeError("ユニバースが空です（日次バッチを先に実行してください）")
        start = started.date() - timedelta(days=settings.daily.lookback_calendar_days)
        rows: list[BenchRow] = []
        for i, n in enumerate(sorted(set(min(s, len(codes)) for s in sizes))):
            if i:
                time.sleep(pause_seconds)
            t0 = time.monotonic()
            res = make_provider().fetch_daily(codes[:n], start)
            rows.append(BenchRow(n, len(res.prices), len(res.failed), time.monotonic() - t0))
            log.info("N=%d: 成功 %d / 失敗 %d / %.1f 秒", n, rows[-1].ok, rows[-1].failed, rows[-1].seconds)
    except Exception as e:
        store.finish_job(run_id, "failed", 0, 0, f"{type(e).__name__}: {e}")
        raise
    report = format_report(rows, started, runner)
    print(report)
    notifier.send(report)
    store.finish_job(run_id, "ok", sum(r.ok for r in rows), sum(r.failed for r in rows),
                     " / ".join(f"N={r.size}: {r.rate:.0%} {r.seconds:.0f}s" for r in rows))
    return rows
