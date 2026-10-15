"""EDINET API v2 による開示書類一覧の取得（書類本体はダウンロードしない。リンクのみ）。

API キーは URL のクエリに入るので、URL をログやエラーに出さない。
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

import httpx

from ..market_calendar import JST

log = logging.getLogger(__name__)

API = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
VIEWER = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc_id},,"


def sec_code_to_code(sec_code: str | None) -> str | None:
    """EDINET の証券コード（5桁、末尾は0）を4桁（英字入りを含む）に変換する。"""
    if not sec_code or len(sec_code) != 5:
        return None
    return sec_code[:4].upper()


def parse_documents(results: list[dict], doc_types: dict[str, str], codes: set[str]) -> list[dict]:
    rows = []
    for d in results:
        if d.get("withdrawalStatus") not in (None, "0"):
            continue  # 取下げ
        dtype = d.get("docTypeCode")
        if dtype not in doc_types:
            continue
        code = sec_code_to_code(d.get("secCode"))
        if code is None or code not in codes:
            continue
        submitted = d.get("submitDateTime")
        submitted_at = (datetime.strptime(submitted, "%Y-%m-%d %H:%M").replace(tzinfo=JST).isoformat()
                        if submitted else None)
        rows.append({
            "id": f"edinet:{d['docID']}",
            "code": code,
            "source": "EDINET",
            "doc_type": doc_types[dtype],
            "title": (d.get("docDescription") or doc_types[dtype])[:300],
            "submitted_at": submitted_at,
            "url": VIEWER.format(doc_id=d["docID"]),
        })
    return rows


class EdinetClient:
    def __init__(self, api_key: str, sleep_seconds: float = 1.0):
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds

    def list_documents(self, day: date) -> list[dict]:
        r = httpx.get(API, params={"date": day.isoformat(), "type": 2, "Subscription-Key": self.api_key},
                      timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"EDINET {day}: HTTP {r.status_code}")
        body = r.json()
        status = str(body.get("metadata", {}).get("status", body.get("StatusCode", "")))
        if status != "200":
            raise RuntimeError(f"EDINET {day}: status {status}")
        time.sleep(self.sleep_seconds)
        return body.get("results") or []
