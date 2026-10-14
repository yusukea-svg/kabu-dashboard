"""Python と TypeScript の指標計算を突き合わせるためのフィクスチャを作る（合成データのみ）。

    uv run python scripts/make_indicator_fixture.py
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from test_indicators import FIXTURE, synthetic_prices  # noqa: E402

from kabu_batch.indicators import compute_all  # noqa: E402

KEYS = ["sma5", "sma25", "sma75", "ema12", "ema26", "rsi14", "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_mid", "bb_lower"]

df = synthetic_prices(120)
out = compute_all(df)


def clean(v: float):
    return None if math.isnan(v) else float(v)


data = {
    "note": "合成データ（実在銘柄の価格ではない）",
    "close": [float(x) for x in df["close"]],
    "volume": [int(x) for x in df["volume"]],
    "expected": {k: [clean(v) for v in out[k]] for k in KEYS},
}
FIXTURE.parent.mkdir(parents=True, exist_ok=True)
FIXTURE.write_text(json.dumps(data))
print(f"wrote {FIXTURE}")
