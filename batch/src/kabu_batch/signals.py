"""シグナル判定。指標を計算済みの DataFrame の「最後の2行」を比べて、その日に条件が成立したかを見る。"""

from __future__ import annotations

import math

import pandas as pd

from .config import SignalRule


def _v(row: pd.Series, col: str | None) -> float | None:
    if col is None or col not in row:
        return None
    v = row[col]
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return None
    return float(v)


def triggered(rule: SignalRule, prev: pd.Series, cur: pd.Series) -> bool:
    if rule.type in ("cross_up", "cross_down"):
        pf, ps, cf, cs = _v(prev, rule.fast), _v(prev, rule.slow), _v(cur, rule.fast), _v(cur, rule.slow)
        if None in (pf, ps, cf, cs):
            return False
        if rule.type == "cross_up":
            return pf <= ps and cf > cs
        return pf >= ps and cf < cs
    if rule.type in ("threshold_up", "threshold_down"):
        p, c = _v(prev, rule.field), _v(cur, rule.field)
        if p is None or c is None or rule.value is None:
            return False
        if rule.type == "threshold_up":
            return p <= rule.value < c
        return p >= rule.value > c
    raise ValueError(f"未知のシグナル種別: {rule.type}")


def evaluate(ind: pd.DataFrame, rules: list[SignalRule]) -> list[tuple[SignalRule, dict]]:
    """成立したルールと、通知・記録用の値（detail）を返す。"""
    if len(ind) < 2:
        return []
    prev, cur = ind.iloc[-2], ind.iloc[-1]
    hits = []
    for rule in rules:
        if triggered(rule, prev, cur):
            cols = {c for c in ("close", rule.fast, rule.slow, rule.field) if c}
            detail = {c: round(v, 4) for c in sorted(cols) if (v := _v(cur, c)) is not None}
            hits.append((rule, detail))
    return hits
