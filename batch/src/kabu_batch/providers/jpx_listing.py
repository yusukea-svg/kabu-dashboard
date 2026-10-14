"""JPX「東証上場銘柄一覧」（data_j.xls / .xlsx）から銘柄マスタを作る。ファイルは保存しない。"""

from __future__ import annotations

import io
import logging
import re
from urllib.parse import urljoin

import httpx
import pandas as pd

from .base import Listing

log = logging.getLogger(__name__)


def _clean(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in ("", "-") else s


def parse_listing_excel(content: bytes, markets: list[str]) -> list[Listing]:
    df = pd.read_excel(io.BytesIO(content), dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    required = ["コード", "銘柄名", "市場・商品区分"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"JPX一覧の列が想定と違います: 不足={missing} 実際={list(df.columns)}")
    if markets:
        df = df[df["市場・商品区分"].isin(markets)]
    out: list[Listing] = []
    for r in df.to_dict("records"):
        code = _clean(r["コード"])
        if not code:
            continue
        out.append(
            Listing(
                code=code.upper(),
                name=_clean(r["銘柄名"]) or code,
                market=_clean(r["市場・商品区分"]) or "",
                sector33=_clean(r.get("33業種区分")),
                sector17=_clean(r.get("17業種区分")),
                scale=_clean(r.get("規模区分")),
            )
        )
    return out


LINK_RE = re.compile(r'href="([^"]*data_j\.xlsx?)"')


def find_listing_link(html: str, page_url: str) -> str | None:
    m = LINK_RE.search(html)
    return urljoin(page_url, m.group(1)) if m else None


class JpxListingProvider:
    """掲載ページからファイルのリンクを探して取得する（拡張子・パスの変更に追従するため）。"""

    def __init__(self, page_url: str, markets: list[str]):
        self.page_url = page_url
        self.markets = markets

    def fetch_listings(self) -> list[Listing]:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            page = client.get(self.page_url)
            page.raise_for_status()
            url = find_listing_link(page.text, self.page_url)
            if not url:
                raise ValueError(f"JPXのページに銘柄一覧ファイルのリンクが見つかりません: {self.page_url}")
            resp = client.get(url)
            resp.raise_for_status()
        listings = parse_listing_excel(resp.content, self.markets)
        log.info("JPX一覧: %d 銘柄", len(listings))
        return listings
