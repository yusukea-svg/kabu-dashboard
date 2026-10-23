import io
from datetime import date, datetime

import pandas as pd

from kabu_batch.jobs.earnings import run_earnings, week_window
from kabu_batch.notify import Notifier
from kabu_batch.providers.jpx_earnings import EarningsEvent, find_earnings_links, parse_earnings_excel
from kabu_batch.storage.base import MemoryStore


class FakeNotifier(Notifier):
    def __init__(self):
        super().__init__("https://example.invalid/webhook")

    def send(self, text: str) -> None:
        self.sent.append(text)


def _excel() -> bytes:
    """JPXのファイルと同じく、タイトル行の下に見出し行がある形を作る（日付はシリアル値と日付型を混在）。"""
    rows = [
        ["9月に期末・四半期末を迎えた会社", None, None, None, None, None],
        [None] * 6,
        ["2026年10月22日現在", None, None, None, None, None],
        [None] * 6,
        ["決算発表予定日", "コード", "会社名", "Issue Name", "決算期末", "種別"],
        [46322, "7203", "トヨタ自動車", "TOYOTA", "3月", "第２四半期"],  # 2026-10-27
        [datetime(2026, 10, 27), 6758, "ソニーグループ", "SONY", "3月", "第２四半期"],
        ["2026/11/05", "130A0", "テスト社", "TEST", "9月", "本決算"],
        ["未定", "9999", "未定社", "TBD", "3月", "第２四半期"],
    ]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_parse_earnings_excel():
    events = parse_earnings_excel(_excel())
    assert [(e.date, e.code, e.name, e.kind) for e in events] == [
        (date(2026, 10, 27), "7203", "トヨタ自動車", "第２四半期"),
        (date(2026, 10, 27), "6758", "ソニーグループ", "第２四半期"),
        (date(2026, 11, 5), "130A", "テスト社", "本決算"),
    ]


def test_find_links():
    html = '<a href="./tvdivq-att/kessan.xlsx">x</a><a href="/a/kessan09_1023.xlsx">y</a><a href="/a/data_j.xls">z</a>'
    links = find_earnings_links(html, "https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html")
    assert links == [
        "https://www.jpx.co.jp/listing/event-schedules/financial-announcement/tvdivq-att/kessan.xlsx",
        "https://www.jpx.co.jp/a/kessan09_1023.xlsx",
    ]


def test_week_window():
    assert week_window(date(2026, 10, 26)) == (date(2026, 10, 26), date(2026, 11, 8))
    assert week_window(date(2026, 10, 28)) == (date(2026, 10, 26), date(2026, 11, 8))


EVENTS = [
    EarningsEvent(date(2026, 10, 27), "6758", "ソニーグループ", "第２四半期"),
    EarningsEvent(date(2026, 10, 27), "7203", "トヨタ自動車", "第２四半期"),
    EarningsEvent(date(2026, 10, 27), "1111", "小型株", "第２四半期"),
    EarningsEvent(date(2026, 11, 5), "130A", "テスト社", "本決算"),
    EarningsEvent(date(2026, 11, 9), "8306", "期間外", "第２四半期"),
]


def _store():
    store = MemoryStore()
    store.upsert("snapshots", [
        {"code": "7203", "in_universe": True, "avg_value20": 300, "intraday_rank": 1},
        {"code": "6758", "in_universe": True, "avg_value20": 200, "intraday_rank": 2},
        {"code": "130A", "in_universe": True, "avg_value20": 100, "intraday_rank": None},
        {"code": "8306", "in_universe": True, "avg_value20": 50, "intraday_rank": None},
        {"code": "1111", "in_universe": False, "avg_value20": 1},
    ], on_conflict="code")
    return store


def test_run_earnings_universe():
    store, n = _store(), FakeNotifier()
    msg = run_earnings(store, lambda: EVENTS, n, {"scope": "universe", "max_per_day": 1}, date(2026, 10, 26))
    assert "3 件" in msg
    text = n.sent[0]
    assert "10/26〜11/8" in text
    assert "**10/27（火）**　2社" in text
    assert "・7203 トヨタ自動車　第２四半期" in text  # 売買代金の大きい順
    assert "ソニー" not in text and "…ほか 1 社" in text  # 上限1社
    assert "小型株" not in text and "期間外" not in text
    assert "**11/5（木）**　1社" in text and "来週" in text
    assert store.jobs[-1]["status"] == "ok"


def test_run_earnings_all_and_empty():
    n = FakeNotifier()
    run_earnings(_store(), lambda: EVENTS, n, {"scope": "all", "max_per_day": 0}, date(2026, 10, 26))
    assert "小型株" in n.sent[0] and "ソニー" in n.sent[0]
    n2 = FakeNotifier()
    run_earnings(_store(), lambda: [], n2, {}, date(2026, 10, 26))
    assert "予定はありません" in n2.sent[0]


def test_skip_when_sent_today():
    store, n = _store(), FakeNotifier()
    store.jobs.append({"job": "earnings", "status": "ok", "started_at": "2026-10-25T22:40:00+00:00"})  # 10/26 7:40 JST
    assert "スキップ" in run_earnings(store, lambda: EVENTS, n, {}, date(2026, 10, 26))
    assert n.sent == []
    run_earnings(store, lambda: EVENTS, n, {}, date(2026, 10, 26), force=True)
    assert len(n.sent) == 1
