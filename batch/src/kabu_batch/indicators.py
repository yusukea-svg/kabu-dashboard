"""テクニカル指標。

pandas だけで実装する（pandas-ta は依存関係の制約が厳しいため不採用）。
定義は一般的なチャートツールと同じもの。web/lib/indicators.ts も同じ定義で、
batch/tests/fixtures/indicators.json を使って両者の値が一致することをテストしている。
"""

from __future__ import annotations

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    # 最初のn本の単純平均を起点にする（TradingView 等と同じ）
    out = pd.Series(float("nan"), index=s.index, dtype="float64")
    values = s.to_numpy(dtype="float64")
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = values[:n].mean()
    out.iloc[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out.iloc[i] = prev
    return out


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder の RSI。最初のn本は単純平均、その後は (prev*(n-1)+x)/n。"""
    out = pd.Series(float("nan"), index=s.index, dtype="float64")
    diff = s.diff().to_numpy(dtype="float64")
    if len(diff) <= n:
        return out
    gains = [max(d, 0.0) for d in diff[1:]]
    losses = [max(-d, 0.0) for d in diff[1:]]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    def value(g: float, lo: float) -> float:
        if lo == 0:
            return 100.0 if g > 0 else 50.0
        return 100 - 100 / (1 + g / lo)

    out.iloc[n] = value(avg_gain, avg_loss)
    for i in range(n + 1, len(diff)):
        avg_gain = (avg_gain * (n - 1) + gains[i - 1]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i - 1]) / n
        out.iloc[i] = value(avg_gain, avg_loss)
    return out


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line.dropna(), signal).reindex(s.index)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)  # 母標準偏差
    return pd.DataFrame({"bb_upper": mid + k * sd, "bb_mid": mid, "bb_lower": mid - k * sd})


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """日足（列: open, high, low, close, volume。日付昇順）から全指標を計算して列を追加する。"""
    close = df["close"].astype("float64")
    out = df.copy()
    for n in (5, 25, 75, 200):
        out[f"sma{n}"] = sma(close, n)
    out["ema12"] = ema(close, 12)
    out["ema26"] = ema(close, 26)
    out["rsi14"] = rsi(close, 14)
    out = out.join(macd(close)).join(bollinger(close))
    out["avg_volume20"] = df["volume"].astype("float64").rolling(20, min_periods=20).mean()
    out["avg_value20"] = (close * df["volume"].astype("float64")).rolling(20, min_periods=20).mean()
    out["change_pct"] = close.pct_change(fill_method=None) * 100
    return out
