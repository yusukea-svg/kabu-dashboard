"""JPX「決算発表予定日」のExcel（kessan*.xlsx）から決算発表の予定を読む。ファイルは保存しない。

掲載ページには「8月に期末・四半期末を迎えた会社」「9月に…」のように月ごとのファイルと、
翌営業日分のファイルが並ぶ。リンクをすべて取得してまとめる（同じ銘柄・日付は1件にする）。
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import httpx
import pandas as pd

log = logging.getLogger(__name__)

LINK_RE = re.compile(r'href="([^"]*kessan[^"]*\.xlsx?)"')
EXCEL_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class EarningsEvent:
    date: date
    code: str
    name: str
    kind: str  # 種別（第２四半期 等）


def find_earnings_links(html: str, page_url: str) -> list[str]:
    return list(dict.fromkeys(urljoin(page_url, m) for m in LINK_RE.findall(html)))


def _clean(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in ("", "-", "nan") else s


def _to_date(v) -> date | None:
    """Excel の日付（日付型・シリアル値・文字列のいずれか）を date にする。未定などは None。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, int | float):
        return EXCEL_EPOCH + timedelta(days=int(v))
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return EXCEL_EPOCH + timedelta(days=int(float(s)))
    try:
        return pd.to_datetime(s.replace("年", "/").replace("月", "/").replace("日", "")).date()
    except (ValueError, TypeError):
        return None


def _code(v) -> str | None:
    s = _clean(v)
    if not s:
        return None
    s = s.upper().removesuffix(".0")
    if len(s) == 5 and s.endswith("0"):  # 5桁コード（末尾0）は4桁にする
        s = s[:4]
    return s if len(s) == 4 else None


def _norm(v) -> str:
    """見出しの比較用。全角・半角の違い、空白・改行（「コード\nCode」のような2段見出し）を無視する。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(v)))


def _find_header(raw: pd.DataFrame) -> int | None:
    for i, row in enumerate(raw.itertuples(index=False)):
        if any(_norm(c).startswith("コード") for c in row):
            return i
    return None


def _preview(raw: pd.DataFrame, rows: int = 8) -> str:
    """見出しが見つからないときの調査用。先頭行の短い文字列だけを出す。"""
    out = []
    for row in raw.head(rows).itertuples(index=False):
        cells = [_norm(c)[:15] for c in row if _norm(c)]
        out.append("|".join(cells[:8]))
    return " / ".join(out)


def _parse_sheet(raw: pd.DataFrame, header_idx: int) -> list[EarningsEvent]:
    cols = [_norm(c) for c in raw.iloc[header_idx].tolist()]

    def col(*cands: str) -> int | None:
        for cand in cands:
            for i, c in enumerate(cols):
                if cand in c:
                    return i
        return None

    i_date, i_code, i_name, i_kind = col("予定日", "発表日"), col("コード"), col("会社名", "銘柄名"), col("種別")
    if i_date is None or i_code is None:
        raise ValueError(f"決算発表予定日のExcelの列が想定と違います: {cols}")
    out: list[EarningsEvent] = []
    for row in raw.iloc[header_idx + 1:].itertuples(index=False):
        d, code = _to_date(row[i_date]), _code(row[i_code])
        if not d or not code:
            continue
        name = (_clean(row[i_name]) if i_name is not None else None) or code
        kind = (_clean(row[i_kind]) if i_kind is not None else None) or ""
        out.append(EarningsEvent(d, code, name, kind))
    return out


def parse_earnings_excel(content: bytes) -> list[EarningsEvent]:
    # 見出し行は先頭ではない（タイトル行の下）。全シートから「コード」で始まる見出しを含む行を探す
    sheets = pd.read_excel(io.BytesIO(content), header=None, sheet_name=None)
    out: list[EarningsEvent] = []
    found = False
    for raw in sheets.values():
        header_idx = _find_header(raw)
        if header_idx is None:
            continue
        found = True
        out += _parse_sheet(raw, header_idx)
    if not found:
        previews = "；".join(f"[{name}] {_preview(raw)}" for name, raw in sheets.items())
        raise ValueError(f"決算発表予定日のExcelに見出し行（コード）が見つかりません: {previews}")
    return out


class JpxEarningsProvider:
    def __init__(self, page_url: str):
        self.page_url = page_url

    def fetch_events(self) -> list[EarningsEvent]:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            page = client.get(self.page_url)
            page.raise_for_status()
            links = find_earnings_links(page.text, self.page_url)
            if not links:
                raise ValueError(f"JPXのページに決算発表予定日のファイルが見つかりません: {self.page_url}")
            events: dict[tuple[str, date], EarningsEvent] = {}
            errors: list[str] = []
            for url in links:
                resp = client.get(url)
                resp.raise_for_status()
                try:
                    parsed = parse_earnings_excel(resp.content)
                except ValueError as e:
                    # 形式の違うファイルが1つあっても、読めたファイルの分は通知する
                    log.warning("%s を読めません: %s", url.rsplit("/", 1)[-1], e)
                    errors.append(url)
                    continue
                for e in parsed:
                    events.setdefault((e.code, e.date), e)
            if len(errors) == len(links):
                raise ValueError("決算発表予定日のファイルをどれも読めませんでした（ログを参照）")
        log.info("決算発表予定: ファイル %d（読めないもの %d）/ %d 件", len(links), len(errors), len(events))
        return list(events.values())
