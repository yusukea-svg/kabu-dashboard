from datetime import date

import pandas as pd

from kabu_batch.jobs import info
from kabu_batch.providers.edinet import parse_documents, sec_code_to_code
from kabu_batch.providers.macro import MacroSeries
from kabu_batch.providers.news import news_id, parse_feed
from kabu_batch.storage.base import MemoryStore

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>test</title>
<item><title>見出しA</title><link>https://example.com/a</link><pubDate>Wed, 14 Oct 2026 23:53:12 GMT</pubDate></item>
<item><title>見出しB</title><link>https://example.com/b</link></item>
<item><title></title><link>https://example.com/empty</link></item>
</channel></rss>""".encode()

DOC_TYPES = {"120": "有価証券報告書", "180": "臨時報告書"}


def test_parse_feed():
    rows = parse_feed(RSS, "テスト")
    assert [r["title"] for r in rows] == ["見出しA", "見出しB"]
    assert rows[0]["published_at"] == "2026-10-14T23:53:12+00:00"
    assert rows[1]["published_at"] is None
    assert rows[0]["id"] == news_id("https://example.com/a")


def test_sec_code():
    assert sec_code_to_code("72030") == "7203"
    assert sec_code_to_code("130a0") == "130A"
    assert sec_code_to_code(None) is None
    assert sec_code_to_code("7203") is None


def test_parse_documents_filters():
    results = [
        {"docID": "S1", "secCode": "72030", "docTypeCode": "120", "docDescription": "有価証券報告書－第1期",
         "submitDateTime": "2026-06-20 15:00", "withdrawalStatus": "0"},
        {"docID": "S2", "secCode": "72030", "docTypeCode": "350", "submitDateTime": "2026-06-20 15:00"},  # 対象外の種別
        {"docID": "S3", "secCode": "99990", "docTypeCode": "120", "submitDateTime": "2026-06-20 15:00"},  # 対象外の銘柄
        {"docID": "S4", "secCode": None, "docTypeCode": "120", "submitDateTime": "2026-06-20 15:00"},     # ファンド等
        {"docID": "S5", "secCode": "72030", "docTypeCode": "180", "submitDateTime": "2026-06-20 16:00",
         "withdrawalStatus": "1"},                                                                       # 取下げ
    ]
    rows = parse_documents(results, DOC_TYPES, {"7203"})
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "edinet:S1" and r["code"] == "7203" and r["doc_type"] == "有価証券報告書"
    assert r["submitted_at"] == "2026-06-20T15:00:00+09:00"
    assert r["url"].endswith("S1,,")


class FakeEdinet:
    def __init__(self):
        self.days = []

    def list_documents(self, day):
        self.days.append(day)
        if day == date(2026, 10, 13):
            raise RuntimeError("boom")
        return [{"docID": f"D{day:%m%d}", "secCode": "72030", "docTypeCode": "180",
                 "submitDateTime": f"{day} 15:00"}]


def test_run_edinet_initial_then_incremental():
    store = MemoryStore()
    store.upsert("securities", [{"code": "7203", "name": "T", "is_active": True}], "code")
    cfg = {"lookback_days": 3, "initial_days": 10, "doc_types": {"180": "臨時報告書"}}
    fake = FakeEdinet()
    r = info.run_edinet(store, cfg, date(2026, 10, 15), client=fake)
    assert len(fake.days) == 9  # 10/5〜10/15 の平日
    assert r.status == "partial" and r.failed == 1
    fake.days.clear()
    info.run_edinet(store, cfg, date(2026, 10, 15), client=fake)
    assert fake.days == [date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)]


def test_run_edinet_without_key_is_skipped(monkeypatch):
    monkeypatch.delenv("EDINET_API_KEY", raising=False)
    assert info.run_edinet(MemoryStore(), {}, date(2026, 10, 15)).status == "skipped"


def test_run_info_isolates_failures(monkeypatch):
    s = pd.Series([1.0, 2.0], index=[date(2026, 10, 14), date(2026, 10, 15)])
    monkeypatch.setattr(info, "fetch_yfinance", lambda items, start: (
        [MacroSeries("yf:^GSPC", "S&P500", "株価指数", "pt", "yfinance", 0, s)], []))
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    def boom(feeds):
        raise RuntimeError("network")

    monkeypatch.setattr(info, "fetch_feeds", boom)
    monkeypatch.delenv("EDINET_API_KEY", raising=False)
    store = MemoryStore()
    sources = {"macro": {"yfinance": [{}], "fred": [{"series": "DGS10"}]}}
    results = {r.job: r for r in info.run_info(store, sources, ["macro", "news", "edinet"], date(2026, 10, 15))}
    assert results["macro"].status == "ok" and "FRED_API_KEY" in results["macro"].message
    assert results["news"].status == "failed"
    assert results["edinet"].status == "skipped"
    assert len(store.tables["macro_series"]) == 2
    assert [j["status"] for j in store.jobs] == ["ok", "failed", "skipped"]
