"""Supabase（PostgREST）への書き込み。service キーを使うので RLS は適用されない。"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import httpx

log = logging.getLogger(__name__)

BATCH_SIZE = 1000


class SupabaseStore:
    def __init__(self, url: str, service_key: str):
        headers = {"apikey": service_key, "Content-Type": "application/json"}
        # 旧形式の service_role キー（JWT）は Authorization ヘッダーも必要
        if service_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {service_key}"
        self.client = httpx.Client(base_url=f"{url.rstrip('/')}/rest/v1", headers=headers, timeout=60)

    def _check(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code >= 400:
            # レスポンス本文にはデータが含まれ得るので、先頭だけ出す
            raise RuntimeError(f"Supabase {resp.request.method} {resp.request.url.path}: "
                               f"{resp.status_code} {resp.text[:300]}")
        return resp

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> int:
        for i in range(0, len(rows), BATCH_SIZE):
            self._check(self.client.post(
                f"/{table}",
                params={"on_conflict": on_conflict},
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                json=rows[i : i + BATCH_SIZE],
            ))
        return len(rows)

    def delete_daily_prices_before(self, cutoff: date) -> None:
        self._check(self.client.delete("/daily_prices", params={"date": f"lt.{cutoff.isoformat()}"}))

    def deactivate_securities(self, codes: list[str]) -> None:
        for i in range(0, len(codes), 200):
            chunk = ",".join(f'"{c}"' for c in codes[i : i + 200])
            self._check(self.client.patch("/securities", params={"code": f"in.({chunk})"},
                                          json={"is_active": False}))

    def latest_job_run(self, job: str, status: str = "ok") -> dict | None:
        resp = self._check(self.client.get("/job_runs", params={
            "job": f"eq.{job}", "status": f"eq.{status}", "order": "started_at.desc", "limit": 1,
        }))
        rows = resp.json()
        return rows[0] if rows else None

    def securities_updated_at(self) -> datetime | None:
        resp = self._check(self.client.get("/securities", params={
            "select": "updated_at", "order": "updated_at.desc", "limit": 1,
        }))
        rows = resp.json()
        return datetime.fromisoformat(rows[0]["updated_at"]) if rows else None

    def list_active_codes(self) -> list[str]:
        codes: list[str] = []
        offset = 0
        while True:
            resp = self._check(self.client.get(
                "/securities",
                params={"select": "code", "is_active": "eq.true", "order": "code"},
                headers={"Range": f"{offset}-{offset + BATCH_SIZE - 1}"},
            ))
            rows = resp.json()
            codes.extend(r["code"] for r in rows)
            if len(rows) < BATCH_SIZE:
                return codes
            offset += BATCH_SIZE

    def _get_all(self, path: str, params: dict) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            resp = self._check(self.client.get(path, params=params,
                                               headers={"Range": f"{offset}-{offset + BATCH_SIZE - 1}"}))
            rows = resp.json()
            out.extend(rows)
            if len(rows) < BATCH_SIZE:
                return out
            offset += BATCH_SIZE

    def security_names(self) -> dict[str, str]:
        rows = self._get_all("/securities", {"select": "code,name", "order": "code"})
        return {r["code"]: r["name"] for r in rows}

    def intraday_targets(self) -> list[str]:
        rows = self._get_all("/snapshots", {"select": "code", "intraday_rank": "not.is.null",
                                            "order": "intraday_rank"})
        return [r["code"] for r in rows]

    def update_last_prices(self, rows: list[dict]) -> int:
        total = 0
        for i in range(0, len(rows), BATCH_SIZE):
            resp = self._check(self.client.post("/rpc/update_last_prices",
                                                json={"rows": rows[i : i + BATCH_SIZE]}))
            total += int(resp.json())
        return total

    def insert_signals(self, rows: list[dict]) -> list[dict]:
        inserted: list[dict] = []
        for i in range(0, len(rows), BATCH_SIZE):
            resp = self._check(self.client.post(
                "/signals",
                params={"on_conflict": "code,kind,timeframe,trade_date"},
                headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
                json=rows[i : i + BATCH_SIZE],
            ))
            inserted.extend(resp.json())
        return inserted

    def notified_signal_keys(self, trade_date: date, timeframe: str) -> set[tuple[str, str]]:
        rows = self._get_all("/signals", {
            "select": "code,kind", "trade_date": f"eq.{trade_date.isoformat()}",
            "timeframe": f"eq.{timeframe}", "notified_at": "not.is.null",
        })
        return {(r["code"], r["kind"]) for r in rows}

    def mark_notified(self, ids: list[int]) -> None:
        now = datetime.now(UTC).isoformat()
        for i in range(0, len(ids), 200):
            chunk = ",".join(str(x) for x in ids[i : i + 200])
            self._check(self.client.patch("/signals", params={"id": f"in.({chunk})"},
                                          json={"notified_at": now}))

    def start_job(self, job: str) -> int | None:
        resp = self._check(self.client.post(
            "/job_runs",
            headers={"Prefer": "return=representation"},
            json={"job": job, "started_at": datetime.now(UTC).isoformat(), "status": "running"},
        ))
        return resp.json()[0]["id"]

    def finish_job(self, run_id: int | None, status: str, ok: int, fail: int, message: str) -> None:
        if run_id is None:
            return
        self._check(self.client.patch("/job_runs", params={"id": f"eq.{run_id}"}, json={
            "finished_at": datetime.now(UTC).isoformat(), "status": status,
            "ok_count": ok, "fail_count": fail, "message": message[:1000],
        }))

    def universe_by_value(self) -> list[str]:
        rows = self._get_all("/snapshots", {"select": "code", "in_universe": "eq.true",
                                            "order": "avg_value20.desc.nullslast"})
        return [r["code"] for r in rows]
