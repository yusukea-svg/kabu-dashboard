"""銘柄ユニバースの絞り込みと、場中更新対象の順位付け。"""

from __future__ import annotations

import math

import pandas as pd

from .config import UniverseConfig


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def in_universe(row: dict, cfg: UniverseConfig) -> bool:
    close, vol, value = row.get("close"), row.get("avg_volume20"), row.get("avg_value20")
    if not (_ok(close) and _ok(vol) and _ok(value)):
        return False
    return (
        cfg.price_min <= close <= cfg.price_max
        and vol >= cfg.avg_volume20_min
        and value >= cfg.avg_value20_min
    )


def apply_universe(snapshots: pd.DataFrame, cfg: UniverseConfig) -> pd.DataFrame:
    """snapshots（1銘柄1行）に in_universe と intraday_rank 列を付けて返す。"""
    out = snapshots.copy()
    out["in_universe"] = [in_universe(r, cfg) for r in out.to_dict("records")]
    ranked = out[out["in_universe"]].sort_values("avg_value20", ascending=False)
    top = ranked.head(cfg.intraday_max_count)
    rank = pd.Series(range(1, len(top) + 1), index=top.index)
    out["intraday_rank"] = rank.reindex(out.index).astype("Int64")
    return out
