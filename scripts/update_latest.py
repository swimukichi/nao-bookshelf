#!/usr/bin/env python3
"""note.com のマガジンRSSを取得し、data/latest.json を生成する。

GitHub Actions から定期実行される。外部ライブラリは使わず標準ライブラリのみで完結させ、
追加のインストール(=費用やメンテコスト)が発生しないようにしている。
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

RSS_URL = "https://note.com/swi0801/m/me98fd692c5c2/rss"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"
MAX_ITEMS = 12

# タイトルにこれらの文字列が含まれる場合、R18バッジを付ける
R18_SERIES_MARKERS = ["淫蜜の館"]

NS = {
    "media": "http://search.yahoo.com/mrss/",
    "note": "https://note.com",
}


def fetch_rss(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; nao-bookshelf-bot/1.0)"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read()


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    return unescape(text).strip()


def is_r18(title: str) -> bool:
    return any(marker in title for marker in R18_SERIES_MARKERS)


def parse_items(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = strip_html(item.findtext("description") or "")
        thumb_el = item.find("media:thumbnail", NS)
        thumbnail = None
        if thumb_el is not None:
            thumbnail = thumb_el.get("url") or (thumb_el.text or "").strip() or None

        if not title or not link:
            continue

        items.append({
            "title": title,
            "link": link,
            "pubDate": pub_date,
            "excerpt": description[:80],
            "thumbnail": thumbnail,
            "r18": is_r18(title),
        })

    return items


def main() -> int:
    try:
        xml_bytes = fetch_rss(RSS_URL)
        items = parse_items(xml_bytes)
    except Exception as exc:  # noqa: BLE001 - スクリプトの失敗はワークフロー側でログに出す
        print(f"[update_latest] failed to fetch/parse RSS: {exc}", file=sys.stderr)
        return 1

    if not items:
        print("[update_latest] no items parsed, keeping existing data/latest.json", file=sys.stderr)
        return 1

    items = items[:MAX_ITEMS]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[update_latest] wrote {len(items)} items to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
