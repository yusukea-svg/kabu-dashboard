"""東証の営業日・取引時間の判定。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import jpholiday

JST = ZoneInfo("Asia/Tokyo")

MORNING = (time(9, 0), time(11, 30))
AFTERNOON = (time(12, 30), time(15, 30))  # 2024-11-05 から大引けは15:30


def now_jst() -> datetime:
    return datetime.now(JST)


def is_trading_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if jpholiday.is_holiday(d):
        return False
    # 年末年始の休場（12/31〜1/3）
    if (d.month == 12 and d.day == 31) or (d.month == 1 and d.day <= 3):
        return False
    return True


def is_market_open(dt: datetime) -> bool:
    dt = dt.astimezone(JST)
    if not is_trading_day(dt.date()):
        return False
    t = dt.time()
    return MORNING[0] <= t <= MORNING[1] or AFTERNOON[0] <= t <= AFTERNOON[1]


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d
