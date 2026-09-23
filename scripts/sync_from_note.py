#!/usr/bin/env python3
"""note に公開済みの小説を取り込み、publisher/works/<作品>/episodes/ に原稿として保存する。

note への投稿は別の仕組み(PC側)が行う。ここでは note を「正」として、
公開された話を他サイト(カクヨム・なろう・エブリスタ)へ流すための原稿を作るだけ。
note には一切書き込まない。

各作品の work.json の "note_match" で、どの note 記事がその作品の何話かを決める。
すでに取り込んだ話は上書きしない(手で直した原稿を守るため)。

外部ライブラリは使わず標準ライブラリのみで完結させる。
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_publish_kit as kit  # noqa: E402

JST = timezone(timedelta(hours=9))
NOTE_USER = "swi0801"
LIST_URL = "https://note.com/api/v2/creators/{user}/contents?kind=note&page={page}"
NOTE_URL = "https://note.com/api/v3/notes/{key}"
MAX_PAGES = 20
UA = {"User-Agent": "Mozilla/5.0 (compatible; nao-bookshelf-bot/1.0)"}

# 他サイトに持っていかない note 用の行(マガジン案内など)
DEFAULT_STRIP = [
    r"^マガジン(はこちら|↓|→)?\s*$",
    r"^https?://note\.com/\S*$",
    r"^続きをみる$",
    r"^(スキ|フォロー).*(励み|力|嬉しい).*$",
]

KANJI_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                "六": 6, "七": 7, "八": 8, "九": 9}


def kanji_to_int(text: str):
    text = text.strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if text.isdigit():
        return int(text)
    total, current = 0, 0
    for ch in text:
        if ch in KANJI_DIGITS:
            current = KANJI_DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def fetch_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def list_notes(user: str):
    """公開済みの記事一覧(新しい順)。"""
    items = []
    for page in range(1, MAX_PAGES + 1):
        data = fetch_json(LIST_URL.format(user=user, page=page)).get("data", {})
        contents = data.get("contents", [])
        items += contents
        if data.get("isLastPage", True) or not contents:
            break
        time.sleep(1)
    return items


# ---------------------------------------------------------------- 本文(HTML → テキスト)

class NoteBodyParser(HTMLParser):
    """note の本文HTMLを、1段落1行のテキストにする。"""

    BLOCKS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"}

    def __init__(self):
        super().__init__()
        self.lines, self.buf, self.skip = [], [], 0

    def flush(self):
        self.lines.append("".join(self.buf).rstrip())
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("figure", "figcaption", "script", "style"):
            self.skip += 1
        elif tag == "br":
            self.flush()
        elif tag == "hr":
            if self.buf:
                self.flush()
            self.lines.append("***")
        elif tag in ("ruby",):
            self.buf.append("|")
        elif tag == "rt":
            self.buf.append("《")

    def handle_endtag(self, tag):
        if tag in ("figure", "figcaption", "script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "rt":
            self.buf.append("》")
        elif tag in self.BLOCKS:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data.replace("\n", ""))


def html_to_text(html: str) -> str:
    parser = NoteBodyParser()
    parser.feed(html or "")
    parser.close()
    if parser.buf:
        parser.flush()
    return "\n".join(parser.lines)


def clean_body(text: str, match: dict, heading_patterns: list) -> str:
    lines = text.split("\n")
    # 冒頭の「━━━ … ━━━」作品紹介ブロックを外す
    if match.get("strip_header_block", True):
        rules = [i for i, line in enumerate(lines[:15]) if re.match(r"^[━─=]{3,}", line.strip())]
        if len(rules) >= 2:
            lines = lines[rules[1] + 1:]
    patterns = [re.compile(p) for p in DEFAULT_STRIP + match.get("strip_lines", []) + heading_patterns]
    lines = [line for line in lines if not any(p.search(line.strip()) for p in patterns)]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


# ---------------------------------------------------------------- 取り込み

def match_episode(title: str, match: dict):
    """記事タイトルがこの作品のものなら (話数, サブタイトル) を返す。"""
    if match.get("contains") and match["contains"] not in title:
        return None
    m = re.search(match["title_regex"], title) if match.get("title_regex") else None
    if match.get("title_regex") and not m:
        return None
    groups = m.groupdict() if m else {}
    num = kanji_to_int(groups["num"]) if groups.get("num") else None
    subtitle = (groups.get("subtitle") or "").strip().strip("「」")
    return num, subtitle


def existing_keys(ep_dir: Path) -> dict:
    keys = {}
    for path in ep_dir.glob("*.md"):
        ep = kit.parse_episode(path)
        if ep["meta"].get("note_key"):
            keys[ep["meta"]["note_key"]] = path
    return keys


def to_jst(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST)


def main() -> int:
    works = []
    for work_dir in sorted(p for p in kit.WORKS_DIR.iterdir() if p.is_dir()):
        work = kit.load_json(work_dir / "work.json")
        if work and work.get("note_match"):
            works.append((work_dir, work))
    if not works:
        print("[sync_from_note] note_match のある作品がありません")
        return 0

    config = kit.load_json(kit.CONFIG_PATH, {})
    user = config.get("note", {}).get("user", NOTE_USER)
    try:
        notes = list_notes(user)
    except Exception as exc:  # noqa: BLE001
        print(f"[sync_from_note] 記事一覧を取得できませんでした: {exc}", file=sys.stderr)
        return 1
    notes.sort(key=lambda n: n.get("publishAt") or "")
    print(f"[sync_from_note] note の公開記事 {len(notes)} 件")

    added = 0
    for work_dir, work in works:
        match = work["note_match"]
        since = match.get("since")
        ep_dir = work_dir / "episodes"
        ep_dir.mkdir(parents=True, exist_ok=True)
        known = existing_keys(ep_dir)
        seq = max([int(p.stem) for p in ep_dir.glob("*.md") if p.stem.isdigit()] or [0])

        for item in notes:
            title = item.get("name", "")
            found = match_episode(title, match)
            if not found or item.get("key") in known:
                continue
            published = to_jst(item["publishAt"]) if item.get("publishAt") else None
            if since and published and published.strftime("%Y-%m-%d") < since:
                continue
            if item.get("price") and not match.get("allow_paid"):
                print(f"[skip] 有料記事: {title}")
                continue
            num, subtitle = found
            if num is None:
                seq += 1
                num = seq
            else:
                seq = max(seq, num)
            path = ep_dir / f"{num:02d}.md"
            if path.exists():
                print(f"[skip] {path.relative_to(kit.ROOT)} は既にあります: {title}")
                continue

            detail = fetch_json(NOTE_URL.format(key=item["key"])).get("data", {})
            time.sleep(1)
            heading_patterns = []
            if subtitle:
                heading_patterns.append(r"^(第\S+[話章]|\d+[話章]?)?[\s　]*「?" + re.escape(subtitle) + r"」?$")
            body = clean_body(html_to_text(detail.get("body", "")), match, heading_patterns)
            if len(body.strip()) < 50:
                print(f"[skip] 本文が取得できませんでした: {title}", file=sys.stderr)
                continue

            delay = float(work.get("repost_delay_hours", config.get("auto_post", {}).get("repost_delay_hours", 0)))
            publish_at = (published + timedelta(hours=delay)) if published else None
            front = [
                "---",
                f"episode: {num}",
                f"title: {subtitle}",
                f"publish_at: {publish_at:%Y-%m-%d %H:%M}" if publish_at else "publish_at:",
                f"note_url: {item.get('noteUrl') or 'https://note.com/' + user + '/n/' + item['key']}",
                f"note_key: {item['key']}",
                f"note_title: {title}",
                "---",
            ]
            path.write_text("\n".join(front) + "\n" + body, encoding="utf-8")
            known[item["key"]] = path
            added += 1
            print(f"[add] {path.relative_to(kit.ROOT)} ← {title}")

    print(f"[sync_from_note] {added} 話を取り込みました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
