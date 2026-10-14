"""データ取得層のインターフェース。

ここを実装したクラスを差し替えれば、yfinance から J-Quants 有料プラン等へ移行できる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd

PRICE_COLUMNS = ["open", "high", "low", "close", "volume"]


@dataclass
class PriceFetchResult:
    # code -> 日足 DataFrame（index: date 昇順、列: PRICE_COLUMNS）
    prices: dict[str, pd.DataFrame] = field(default_factory=dict)
    # 直近に株式分割・併合があった銘柄（全期間をDBに書き直す）
    split_codes: set[str] = field(default_factory=set)
    failed: list[str] = field(default_factory=list)


class DailyPriceProvider(Protocol):
    source_id: int

    def fetch_daily(self, codes: list[str], start: date) -> PriceFetchResult: ...


@dataclass
class Listing:
    code: str
    name: str
    market: str
    sector33: str | None = None
    sector17: str | None = None
    scale: str | None = None


class ListingProvider(Protocol):
    def fetch_listings(self) -> list[Listing]: ...
