"""Discord Webhook への通知。

Webhook URL は GitHub Secrets / .env の DISCORD_WEBHOOK_URL に置く（未設定なら通知しない）。
"""

from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

DISCORD_LIMIT = 2000
DISCLAIMER = "※個人の情報整理用です。投資助言ではありません。"


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """行の途中で切らずに、Discord の文字数上限ごとに分ける。"""
    chunks: list[str] = []
    cur = ""
    for line in text.splitlines():
        line = line[: limit - 1]
        if len(cur) + len(line) + 1 > limit:
            chunks.append(cur.rstrip("\n"))
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur.rstrip("\n"))
    return chunks


class Notifier:
    def __init__(self, webhook_url: str | None = None):
        self.url = webhook_url if webhook_url is not None else os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        self.sent: list[str] = []  # テスト・ドライラン用

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, text: str) -> None:
        self.sent.append(text)
        if not self.enabled:
            log.info("通知（Webhook未設定のため送信なし）: %d 文字", len(text))
            return
        for chunk in split_message(text):
            for attempt in range(3):
                try:
                    r = httpx.post(self.url, json={"content": chunk, "allowed_mentions": {"parse": []}},
                                   timeout=20)
                    if r.status_code == 429:  # レート制限：指示された秒数待つ
                        time.sleep(float(r.json().get("retry_after", 2)))
                        continue
                    r.raise_for_status()
                    break
                except httpx.HTTPError as e:
                    log.warning("Discord 通知に失敗（%d 回目）: %s", attempt + 1, type(e).__name__)
                    time.sleep(2)
            time.sleep(0.5)


def dashboard_link(code: str | None = None) -> str:
    base = os.environ.get("DASHBOARD_URL", "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/stock/?code={code}" if code else base
