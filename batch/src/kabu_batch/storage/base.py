"""保存先のインターフェース。Supabase 以外（SQLite 等）に変える場合はこれを実装する。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Store(Protocol):
    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> int: ...

    def delete_daily_prices_before(self, cutoff: date) -> None: ...

    def deactivate_securities(self, codes: list[str]) -> None: ...

    def latest_job_run(self, job: str, status: str = "ok") -> dict | None: ...

    def securities_updated_at(self) -> datetime | None: ...

    def list_active_codes(self) -> list[str]: ...

    def start_job(self, job: str) -> int | None: ...

    def finish_job(self, run_id: int | None, status: str, ok: int, fail: int, message: str) -> None: ...

    # --- フェーズ2 ---
    def security_names(self) -> dict[str, str]: ...

    def intraday_targets(self) -> list[str]: ...

    def update_last_prices(self, rows: list[dict]) -> int: ...

    def insert_signals(self, rows: list[dict]) -> list[dict]:
        """新規に入った行だけを返す（既にある組み合わせは無視）。"""
        ...

    def notified_signal_keys(self, trade_date: date, timeframe: str) -> set[tuple[str, str]]: ...

    def mark_notified(self, ids: list[int]) -> None: ...

    def universe_by_value(self) -> list[str]: ...


class MemoryStore:
    """ドライラン・テスト用。書き込み内容を保持するだけ。"""

    def __init__(self) -> None:
        self.tables: dict[str, dict[tuple, dict]] = {}
        self.jobs: list[dict] = []
        self.deleted_before: date | None = None

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> int:
        keys = on_conflict.split(",")
        t = self.tables.setdefault(table, {})
        for r in rows:
            t[tuple(r[k] for k in keys)] = {**t.get(tuple(r[k] for k in keys), {}), **r}
        return len(rows)

    def delete_daily_prices_before(self, cutoff: date) -> None:
        self.deleted_before = cutoff

    def deactivate_securities(self, codes: list[str]) -> None:
        for k, v in self.tables.get("securities", {}).items():
            if k[0] in codes:
                v["is_active"] = False

    def latest_job_run(self, job: str, status: str = "ok") -> dict | None:
        runs = [j for j in self.jobs if j["job"] == job and j["status"] == status]
        return runs[-1] if runs else None

    def securities_updated_at(self) -> datetime | None:
        return None

    def list_active_codes(self) -> list[str]:
        return sorted(k[0] for k, v in self.tables.get("securities", {}).items() if v.get("is_active"))

    def start_job(self, job: str) -> int | None:
        self.jobs.append({"job": job, "status": "running"})
        return len(self.jobs) - 1

    def finish_job(self, run_id: int | None, status: str, ok: int, fail: int, message: str) -> None:
        if run_id is not None:
            self.jobs[run_id].update(status=status, ok_count=ok, fail_count=fail, message=message)

    def security_names(self) -> dict[str, str]:
        return {k[0]: v.get("name", k[0]) for k, v in self.tables.get("securities", {}).items()}

    def intraday_targets(self) -> list[str]:
        snaps = [v for v in self.tables.get("snapshots", {}).values() if v.get("intraday_rank") is not None]
        return [s["code"] for s in sorted(snaps, key=lambda s: s["intraday_rank"])]

    def update_last_prices(self, rows: list[dict]) -> int:
        snaps = self.tables.setdefault("snapshots", {})
        n = 0
        for r in rows:
            if (r["code"],) in snaps:
                snaps[(r["code"],)].update(last_price=r["last_price"], last_price_at=r["last_price_at"])
                n += 1
        return n

    def insert_signals(self, rows: list[dict]) -> list[dict]:
        t = self.tables.setdefault("signals", {})
        inserted = []
        for r in rows:
            key = (r["code"], r["kind"], r["timeframe"], r["trade_date"])
            if key not in t:
                t[key] = {**r, "id": len(t) + 1, "notified_at": None}
                inserted.append(t[key])
        return inserted

    def notified_signal_keys(self, trade_date: date, timeframe: str) -> set[tuple[str, str]]:
        d = trade_date.isoformat()
        return {(v["code"], v["kind"]) for v in self.tables.get("signals", {}).values()
                if v["trade_date"] == d and v["timeframe"] == timeframe and v.get("notified_at")}

    def mark_notified(self, ids: list[int]) -> None:
        for v in self.tables.get("signals", {}).values():
            if v["id"] in ids:
                v["notified_at"] = "now"

    def universe_by_value(self) -> list[str]:
        snaps = [v for v in self.tables.get("snapshots", {}).values() if v.get("in_universe")]
        return [s["code"] for s in sorted(snaps, key=lambda s: -(s.get("avg_value20") or 0))]
