"""コマンドライン入口。

    uv run kabu-batch daily              # 日次バッチ（Supabaseへ保存）
    uv run kabu-batch daily --dry-run --limit 50   # 保存せず件数だけ確認
    uv run kabu-batch daily --full       # 初回：全期間を書き込む
    uv run kabu-batch intraday           # 場中バッチ（場中更新の対象だけ）
    uv run kabu-batch bench --sizes 100,300,500    # 取得件数の実測
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import REPO_ROOT, load_settings, require_env
from .jobs.bench import run_bench
from .jobs.daily import run_daily
from .jobs.info import PARTS, run_info
from .jobs.intraday import run_intraday
from .notify import Notifier
from .providers.jpx_listing import JpxListingProvider
from .providers.yfinance_provider import YFinanceDailyProvider
from .storage.base import MemoryStore
from .storage.supabase_store import SupabaseStore

JOB_LABELS = {"daily": "日次", "intraday": "場中", "bench": "実測", "info": "情報"}


def _load_dotenv() -> None:
    """リポジトリ直下の .env を読む（GitHub Actions では Secrets を環境変数で渡す）。"""
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _store(dry_run: bool):
    if dry_run:
        return MemoryStore()
    return SupabaseStore(require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_KEY"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kabu-batch")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--no-notify", action="store_true", help="Discord に通知しない")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daily", help="日次バッチ")
    d.add_argument("--dry-run", action="store_true", help="保存しない（件数のみ表示）")
    d.add_argument("--full", action="store_true", help="全期間を書き込み、銘柄一覧も再取得する")
    d.add_argument("--force", action="store_true", help="休場日・取得済みでも実行する")
    d.add_argument("--limit", type=int, help="先頭N銘柄だけ処理する（動作確認用）")

    i = sub.add_parser("intraday", help="場中バッチ")
    i.add_argument("--force", action="store_true", help="休場日・時間外でも実行する")
    i.add_argument("--limit", type=int, help="先頭N銘柄だけ処理する（動作確認用）")

    b = sub.add_parser("bench", help="取得件数の実測")
    b.add_argument("--sizes", default="100,300,500", help="カンマ区切りの件数")
    b.add_argument("--pause", type=float, default=60, help="各回の間の待機秒数")

    f = sub.add_parser("info", help="マクロ指標・ニュース・EDINET開示の取得")
    f.add_argument("--only", default=",".join(PARTS), help="macro,news,edinet のうち実行するもの")

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # yfinance は失敗銘柄ごとに大量のログを出すので抑える。httpx は URL を出すので抑える
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _load_dotenv()
    settings = load_settings()
    dry_run = getattr(args, "dry_run", False)
    notifier = Notifier("") if (args.no_notify or dry_run) else Notifier()
    label = JOB_LABELS[args.cmd]

    try:
        if args.cmd == "daily":
            c = settings.daily
            summary = run_daily(
                settings,
                _store(dry_run),
                YFinanceDailyProvider(c.chunk_size, c.sleep_seconds, c.retry_rounds, c.retry_sleep_seconds),
                JpxListingProvider(settings.listing.page_url, settings.universe.markets),
                full=args.full,
                force=args.force or dry_run,
                limit=args.limit,
                notifier=notifier,
            )
        elif args.cmd == "intraday":
            c = settings.intraday
            summary = run_intraday(
                settings,
                _store(False),
                YFinanceDailyProvider(c.chunk_size, c.sleep_seconds, c.retry_rounds, c.retry_sleep_seconds),
                force=args.force,
                limit=args.limit,
                notifier=notifier,
            )
        elif args.cmd == "info":
            parts = [p.strip() for p in args.only.split(",") if p.strip() in PARTS]
            results = run_info(_store(False), settings.sources, parts)
            for r in results:
                print(f"[{r.job}] {r.status}: {r.message}")
            bad = [r for r in results if r.status in ("failed", "partial")]
            if bad:
                notifier.send("⚠️ 情報取得で一部失敗：" + " ／ ".join(f"{r.job}={r.status}" for r in bad))
            return 1 if any(r.status == "failed" for r in results) else 0
        else:
            c = settings.intraday
            run_bench(
                settings,
                _store(False),
                lambda: YFinanceDailyProvider(c.chunk_size, c.sleep_seconds, retry_rounds=0),
                [int(x) for x in args.sizes.split(",") if x.strip()],
                pause_seconds=args.pause,
                notifier=notifier,
                runner="GitHub Actions" if os.environ.get("GITHUB_ACTIONS") else "ローカル",
            )
            return 0
    except Exception as e:
        # 例外メッセージにはデータが含まれ得るので、通知には種類だけを載せる
        notifier.send(f"❌ {label}バッチが失敗しました：{type(e).__name__}\n詳細は GitHub Actions のログを確認してください。")
        raise

    print(f"[{args.cmd}] {summary.status}: {summary.message()}")
    if summary.status == "partial":
        notifier.send(f"⚠️ {label}バッチは一部失敗しました：{summary.message()}")
    if summary.status == "failed":
        notifier.send(f"❌ {label}バッチが失敗しました：{summary.message()}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
