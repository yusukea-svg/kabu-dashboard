"""設定ファイル（config/*.yaml）と環境変数の読み込み。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = Path(os.environ.get("KABU_CONFIG_DIR", REPO_ROOT / "config"))


@dataclass(frozen=True)
class UniverseConfig:
    markets: list[str] = field(default_factory=list)
    price_min: float = 100
    price_max: float = 5000
    avg_volume20_min: float = 30_000
    avg_value20_min: float = 30_000_000
    intraday_max_count: int = 300


@dataclass(frozen=True)
class ListingConfig:
    page_url: str = ""
    refresh_days: int = 7


@dataclass(frozen=True)
class DailyFetchConfig:
    provider: str = "yfinance"
    lookback_calendar_days: int = 450
    history_trading_days: int = 300
    upsert_recent_days: int = 10
    chunk_size: int = 100
    sleep_seconds: float = 3
    retry_rounds: int = 2
    retry_sleep_seconds: float = 30


@dataclass(frozen=True)
class IntradayConfig:
    # この時間帯（JST）以外に起動したら何もしない（cron が大きく遅れた場合など）
    window_start: str = "09:00"
    window_end: str = "16:00"
    chunk_size: int = 100
    sleep_seconds: float = 3
    retry_rounds: int = 1
    retry_sleep_seconds: float = 30


@dataclass(frozen=True)
class SignalRule:
    id: str
    label: str
    type: str  # cross_up | cross_down | threshold_up | threshold_down
    fast: str | None = None
    slow: str | None = None
    field: str | None = None
    value: float | None = None
    notify: bool = True


@dataclass(frozen=True)
class SignalConfig:
    rules: list[SignalRule] = field(default_factory=list)
    notify_scope: str = "intraday"  # intraday | universe
    notify_max_per_rule: int = 15


@dataclass(frozen=True)
class Settings:
    universe: UniverseConfig
    listing: ListingConfig
    daily: DailyFetchConfig
    intraday: IntradayConfig = field(default_factory=IntradayConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    sources: dict = field(default_factory=dict)  # config/sources.yaml（フェーズ3）


def _read_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    fetch = _read_yaml("fetch.yaml")
    sig = _read_yaml("signals.yaml")
    rules = [SignalRule(**r) for r in sig.pop("rules", [])]
    return Settings(
        universe=UniverseConfig(**_read_yaml("universe.yaml")),
        listing=ListingConfig(**fetch.get("listing", {})),
        daily=DailyFetchConfig(**fetch.get("daily", {})),
        intraday=IntradayConfig(**fetch.get("intraday", {})),
        signals=SignalConfig(rules=rules, **sig),
        sources=_read_yaml("sources.yaml"),
    )


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません（.env.example を参照）")
    return value
