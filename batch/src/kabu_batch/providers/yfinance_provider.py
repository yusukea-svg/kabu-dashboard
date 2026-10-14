"""yfinance による日足取得（非公式。個人利用に限る）。

公開リポジトリの Actions ログは誰でも見られるため、価格の値はログに出さない（件数のみ）。
"""

from __future__ import annotations

import logging
import time
from datetime import date

import pandas as pd

from .base import PRICE_COLUMNS, PriceFetchResult

log = logging.getLogger(__name__)


def to_symbol(code: str) -> str:
    return f"{code}.T"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df = df[[c for c in PRICE_COLUMNS + ["stock splits"] if c in df.columns]]
    df = df.dropna(subset=["close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df[~df.index.duplicated(keep="last")].sort_index()


class YFinanceDailyProvider:
    source_id = 1

    def __init__(
        self,
        chunk_size: int = 100,
        sleep_seconds: float = 3,
        retry_rounds: int = 2,
        retry_sleep_seconds: float = 30,
        split_window_days: int = 10,
    ):
        self.chunk_size = chunk_size
        self.sleep_seconds = sleep_seconds
        self.retry_rounds = retry_rounds
        self.retry_sleep_seconds = retry_sleep_seconds
        self.split_window_days = split_window_days

    def _download_chunk(self, codes: list[str], start: date) -> dict[str, pd.DataFrame]:
        import yfinance as yf

        symbols = [to_symbol(c) for c in codes]
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            actions=True,
            threads=True,
            progress=False,
            multi_level_index=True,
        )
        out: dict[str, pd.DataFrame] = {}
        if raw is None or raw.empty:
            return out
        top = set(raw.columns.get_level_values(0))
        for code, sym in zip(codes, symbols, strict=True):
            if sym not in top:
                continue
            df = _normalize(raw[sym])
            if not df.empty:
                out[code] = df
        return out

    def fetch_daily(self, codes: list[str], start: date) -> PriceFetchResult:
        result = PriceFetchResult()
        pending = list(codes)
        for round_no in range(self.retry_rounds + 1):
            if not pending:
                break
            if round_no > 0:
                wait = self.retry_sleep_seconds * (2 ** (round_no - 1))
                log.info("再試行 %d 回目: %d 銘柄（%ds 待機）", round_no, len(pending), wait)
                time.sleep(wait)
            failed: list[str] = []
            for i in range(0, len(pending), self.chunk_size):
                chunk = pending[i : i + self.chunk_size]
                try:
                    got = self._download_chunk(chunk, start)
                except Exception as e:  # レート制限・通信エラー等はチャンク単位で失敗扱い
                    log.warning("チャンク取得失敗 (%d 銘柄): %s", len(chunk), type(e).__name__)
                    got = {}
                result.prices.update(got)
                failed.extend(c for c in chunk if c not in got)
                if i + self.chunk_size < len(pending):
                    time.sleep(self.sleep_seconds)
            pending = failed
        result.failed = pending

        # 直近に分割・併合があった銘柄を記録し、列を落とす
        for code, df in result.prices.items():
            if "stock splits" in df.columns:
                recent = df["stock splits"].tail(self.split_window_days)
                if (recent.fillna(0) != 0).any():
                    result.split_codes.add(code)
                result.prices[code] = df.drop(columns=["stock splits"])
        log.info(
            "日足取得: 成功 %d / 失敗 %d / 分割検知 %d",
            len(result.prices), len(result.failed), len(result.split_codes),
        )
        return result
