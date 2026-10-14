import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kabu_batch import indicators as ind

FIXTURE = Path(__file__).parent / "fixtures" / "indicators.json"


def synthetic_prices(n: int = 320, seed: int = 7) -> pd.DataFrame:
    """実データではない合成価格（リポジトリに置いてよい）。"""
    rng = np.random.default_rng(seed)
    close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    volume = rng.integers(50_000, 500_000, n)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": volume}, index=idx)


def test_sma():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert ind.sma(s, 3).tolist()[2:] == [2, 3, 4]
    assert ind.sma(s, 3).isna().sum() == 2


def test_ema_seed_and_convergence():
    s = synthetic_prices()["close"]
    e = ind.ema(s, 12)
    assert e.iloc[11] == pytest.approx(s.iloc[:12].mean())
    # 十分に長い期間の後は pandas の指数平滑（adjust=False）とほぼ一致する
    ref = s.ewm(span=12, adjust=False).mean()
    assert e.iloc[-1] == pytest.approx(ref.iloc[-1], rel=1e-6)


def test_rsi_bounds_and_convergence():
    s = synthetic_prices()["close"]
    r = ind.rsi(s, 14)
    assert r.iloc[:14].isna().all()
    assert ((r.dropna() >= 0) & (r.dropna() <= 100)).all()
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    lo = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    ref = 100 - 100 / (1 + g / lo)
    assert r.iloc[-1] == pytest.approx(ref.iloc[-1], rel=1e-4)


def test_rsi_monotonic_up_is_100():
    s = pd.Series(range(1, 40), dtype=float)
    assert ind.rsi(s, 14).iloc[-1] == 100


def test_bollinger_uses_population_std():
    s = pd.Series([1, 2, 3, 4, 5] * 4, dtype=float)
    bb = ind.bollinger(s, 20, 2)
    assert bb["bb_mid"].iloc[-1] == pytest.approx(3)
    assert bb["bb_upper"].iloc[-1] == pytest.approx(3 + 2 * np.sqrt(2))


def test_compute_all_columns():
    out = ind.compute_all(synthetic_prices())
    for c in ["sma5", "sma200", "ema12", "rsi14", "macd", "macd_signal", "bb_upper", "avg_value20"]:
        assert pd.notna(out[c].iloc[-1]), c
    # MACD シグナルは MACD 線が出揃ってから9本目に初めて値が出る
    assert out["macd"].first_valid_index() == out.index[25]
    assert out["macd_signal"].first_valid_index() == out.index[33]


def test_fixture_matches_implementation():
    """web/lib/indicators.ts と共有するフィクスチャ。値を変えたら scripts で再生成する。"""
    data = json.loads(FIXTURE.read_text())
    s = pd.Series(data["close"], dtype=float)
    df = pd.DataFrame({"close": s, "volume": data["volume"],
                       "open": s, "high": s, "low": s})
    out = ind.compute_all(df)
    for key, expected in data["expected"].items():
        got = out[key].tolist()
        for a, b in zip(got, expected, strict=True):
            if b is None:
                assert pd.isna(a), key
            else:
                assert a == pytest.approx(b, rel=1e-9), key
