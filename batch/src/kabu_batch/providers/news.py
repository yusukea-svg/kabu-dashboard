"""ニュース RSS の取得。見出し・リンク・日時だけを扱い、本文は保存しない。"""

from __future__ import annotations

import calendar
import hashlib
import logging
from datetime import UTC, datetime

import feedparser
import httpx

log = logging.getLogger(__name__)

USER_AGENT = "kabu-dashboard (personal use; +https://github.com/)"


def news_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def parse_feed(content: bytes, source: str) -> list[dict]:
    feed = feedparser.parse(content)
    rows = []
    for e in feed.entries:
        url = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        if not url or not title:
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(t), UTC).isoformat() if t else None
        rows.append({"id": news_id(url), "source": source, "title": title[:300], "url": url,
                     "published_at": published})
    return rows


def fetch_feeds(feeds: list[dict]) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    failed: list[str] = []
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for f in feeds:
            try:
                r = client.get(f["url"])
                r.raise_for_status()
                got = parse_feed(r.content, f["name"])
                if not got:
                    raise ValueError("記事が0件")
                rows.extend(got)
            except Exception as e:
                log.warning("RSS取得失敗 %s: %s", f["name"], type(e).__name__)
                failed.append(f["name"])
    # 同じURLが複数のフィードに載っている場合は1件に
    uniq = {r["id"]: r for r in rows}
    return list(uniq.values()), failed
