#!/usr/bin/env python3
"""原稿から各投稿先向けの「投稿キット」を生成する。

publisher/works/<作品>/ に置いた原稿(共通記法)を読み、
note / カクヨム / 小説家になろう / エブリスタ 用の本文と、
X / Threads / Instagram / TikTok 用の告知文、投稿チェックリストを
publisher/output/ に書き出す。

投稿そのものは手動で行う前提(各サイトに公式の投稿APIがないため)。
data/latest.json に note の公開記事が入っていれば、告知文のURLを自動で埋める。

外部ライブラリは使わず標準ライブラリのみで完結させる。
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHER_DIR = ROOT / "publisher"
WORKS_DIR = PUBLISHER_DIR / "works"
OUTPUT_DIR = PUBLISHER_DIR / "output"
CONFIG_PATH = PUBLISHER_DIR / "config.json"
LATEST_PATH = ROOT / "data" / "latest.json"

PLATFORM_LABELS = {
    "note": "note",
    "kakuyomu": "カクヨム",
    "narou": "小説家になろう",
    "estar": "エブリスタ",
}

# 1話あたりの文字数上限(超えたら警告を出す)
CHAR_LIMITS = {
    "kakuyomu": 100_000,
    "narou": 70_000,
    "estar": 100_000,
}

# 字下げしない行頭文字(会話文・記号)
NO_INDENT_HEADS = tuple("「『（(〈《【―…─—　 ")

RUBY_EXPLICIT = re.compile(r"[|｜]([^|｜《》\n]+?)《([^《》\n]+?)》")
RUBY_IMPLICIT = re.compile(r"([一-龥々〆ヵヶ]+)《([^《》\n]+?)》")
EMPHASIS = re.compile(r"《《([^《》\n]+?)》》")
IMAGE_MARK = re.compile(r"^\[画像[:：]\s*(.*?)\]$")
SCENE_BREAK = re.compile(r"^(\*\*\*|＊＊＊|◇|◆|---)$")


# ---------------------------------------------------------------- 読み込み

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def parse_episode(path: Path) -> dict:
    """先頭の --- で囲まれた key: value を読み、残りを本文とする。"""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            body = text[end + 4:].lstrip("\n")
    meta.setdefault("episode", re.sub(r"\D", "", path.stem) or path.stem)
    meta.setdefault("title", "")
    return {"meta": meta, "body": body.rstrip() + "\n", "file": path.name}


# ---------------------------------------------------------------- 本文変換

def convert_markup(text: str, platform: str) -> str:
    """共通記法(ルビ・傍点)を各サイトの記法に変換する。"""
    if platform in ("kakuyomu",):
        # カクヨムはルビ・傍点とも共通記法のまま使える
        return text

    def emphasis(m):
        chars = m.group(1)
        if platform == "narou":
            # なろうは傍点記法がないため、1文字ずつ「﹅」のルビで表現する
            return "".join(f"|{c}《﹅》" for c in chars)
        if platform == "note":
            return f"**{chars}**"
        return chars

    text = EMPHASIS.sub(emphasis, text)

    if platform == "narou":
        text = RUBY_EXPLICIT.sub(lambda m: f"|{m.group(1)}《{m.group(2)}》", text)
        return text

    # note・エブリスタ用: ルビは「漢字（かんじ）」の括弧書きにする
    text = RUBY_EXPLICIT.sub(lambda m: f"{m.group(1)}（{m.group(2)}）", text)
    text = RUBY_IMPLICIT.sub(lambda m: f"{m.group(1)}（{m.group(2)}）", text)
    return text


def format_body(body: str, platform: str, indent: bool) -> str:
    lines_out = []
    for line in body.split("\n"):
        # 全角スペース(作者の字下げ)は残す
        stripped = line.strip(" \t\r")
        image = IMAGE_MARK.match(stripped.strip())
        if image:
            if platform == "note":
                lines_out.append(f"【画像挿入：{image.group(1)}】")
            continue
        if SCENE_BREAK.match(stripped.strip()):
            lines_out.append("")
            lines_out.append("───" if platform == "note" else "◇　◇　◇")
            lines_out.append("")
            continue
        if not stripped.strip():
            lines_out.append("")
            continue
        converted = convert_markup(stripped, platform)
        if indent and not converted.startswith(NO_INDENT_HEADS):
            converted = "　" + converted
        lines_out.append(converted)
    text = "\n".join(lines_out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


def plain_length(text: str) -> int:
    """空白・改行・ルビ記法を除いた文字数。"""
    text = EMPHASIS.sub(lambda m: m.group(1), text)
    text = RUBY_EXPLICIT.sub(lambda m: m.group(1), text)
    text = RUBY_IMPLICIT.sub(lambda m: m.group(1), text)
    text = re.sub(r"^\[画像[:：].*?\]$", "", text, flags=re.M)
    return len(re.sub(r"\s", "", text))


# ---------------------------------------------------------------- ラベル類

def to_kanji(num) -> str:
    """1〜99 を漢数字にする(第十章 などの表記用)。"""
    if not str(num).isdigit() or not 0 < int(num) < 100:
        return str(num)
    digits = "〇一二三四五六七八九"
    tens, ones = divmod(int(num), 10)
    head = "" if tens == 0 else ("十" if tens == 1 else digits[tens] + "十")
    return head + (digits[ones] if ones else "")


def episode_label(work: dict, ep: dict) -> str:
    num = ep["meta"]["episode"]
    unit = work.get("episode_unit", "第{n}話")
    label = unit.replace("{n}", str(num)).replace("{kanji}", to_kanji(num))
    title = ep["meta"].get("title")
    if not label:
        return title
    return f"{label}　{title}" if title else label


def full_title(work: dict, ep: dict) -> str:
    prefix = work.get("title_prefix", "")
    return f"{prefix}{work['title']}　{episode_label(work, ep)}"


def note_title(work: dict, ep: dict) -> str:
    """note に投稿するときの記事タイトル。

    work.json の note_title_format で変えられる(例: 短編集なら "【ホラー短編】{ep_title}")。
    使える差し込み: {prefix} {title} {label} {ep_title}
    """
    fmt = work.get("note_title_format")
    if not fmt:
        return full_title(work, ep)
    return fmt.format(prefix=work.get("title_prefix", ""), title=work["title"],
                      label=episode_label(work, ep), ep_title=ep["meta"].get("title", ""))


def find_note_url(work: dict, ep: dict, latest: list) -> str:
    """data/latest.json から公開済みの note 記事URLを探す。"""
    if ep["meta"].get("note_url"):
        return ep["meta"]["note_url"]
    ep_title = ep["meta"].get("title", "")
    for item in latest or []:
        title = item.get("title", "")
        if work["title"] in title and ep_title and ep_title in title:
            return item.get("link", "")
    return ""


def hashtags(tags, limit=None) -> str:
    seen = []
    for tag in tags:
        tag = str(tag).lstrip("#").replace(" ", "")
        if tag and tag not in seen:
            seen.append(tag)
    if limit:
        seen = seen[:limit]
    return " ".join(f"#{t}" for t in seen)


def x_weight(text: str) -> int:
    """X の文字数カウント(全角2・半角1、URLは23)。"""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(1 if ord(c) < 0x1100 else 2 for c in text)


def fit_x(parts: list, limit: int = 280) -> str:
    """X の上限に収まるよう、フック文(2番目)を削って調整する。"""
    text = "\n".join(p for p in parts if p)
    if x_weight(text) <= limit:
        return text
    hook = parts[1]
    while hook and x_weight("\n".join(p for p in [parts[0], hook + "…", *parts[2:]] if p)) > limit:
        hook = hook[:-1]
    parts = [parts[0], hook + "…" if hook else "", *parts[2:]]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------- 各出力

def build_note(work, ep, config, next_ep) -> str:
    cfg = config.get("note", {})
    magazine = work.get("links", {}).get("note_magazine") or cfg.get("magazine_url", "")
    if work.get("note_header") is False:
        header = []
    else:
        header = [
            "━━━",
            f"{work.get('genre_label', work.get('genre', ''))}『{work['title']}』"
            + (f"全{work['total_episodes']}話" if work.get("total_episodes") else ""),
            work.get("catch", ""),
            "━━━",
            "",
            episode_label(work, ep),
            "",
        ]
    footer = ["", "───", ""] if header else ["", ""]
    if work.get("anthology"):
        footer.append("（了）")
    elif next_ep:
        footer.append(f"次回：{episode_label(work, next_ep)}"
                      + (f"（{next_ep['meta']['publish_at']} 公開予定）" if next_ep["meta"].get("publish_at") else ""))
    else:
        footer.append("（完）" if work.get("status") == "完結" else "（つづく）")
    if magazine:
        footer += ["", f"マガジンはこちら", magazine]
    if cfg.get("cta"):
        footer += ["", cfg["cta"]]
    return ("\n".join(header) + "\n" if header else "") + format_body(ep["body"], "note", indent=False) + "\n".join(footer) + "\n"


def build_novel_site(work, ep, platform) -> str:
    return format_body(ep["body"], platform, indent=work.get("indent", True))


def build_sns(work, ep, config, note_url, r18) -> str:
    sns = config.get("sns", {})
    tags_ja = work.get("tags", []) + sns.get("default_tags", [])
    tags_en = work.get("tags_en", []) + sns.get("default_tags_en", [])
    label = episode_label(work, ep)
    hook = ep["meta"].get("hook") or work.get("catch", "")
    url = note_url or "{{noteのURLを貼る}}"
    is_last = str(ep["meta"]["episode"]) == str(work.get("total_episodes", ""))
    kind = "【完結】" if is_last else ("【連載開始】" if str(ep["meta"]["episode"]) == "1" else "【更新】")
    head = f"『{work['title']}』{label}"
    if work.get("anthology"):
        # 短編集は1話ずつ独立しているので、記事タイトルをそのまま使う
        kind, head = "", note_title(work, ep)

    out = [f"# SNS告知文 — {full_title(work, ep)}", ""]
    if r18:
        out += [
            "> ⚠️ R18作品です。一般向けSNSでは本文の引用・表紙の直接掲載を避け、",
            "> 年齢確認のあるページ(r18.html)への誘導にとどめてください。",
            "",
        ]
    if not note_url:
        out += ["> ℹ️ noteのURLが未確定です。公開後に `{{noteのURLを貼る}}` を置き換えてください。",
                "> (6時間ごとのフィード更新で公開が検知されると、自動で埋まります)", ""]

    # X
    x_simple = fit_x([f"{kind}{head}", hook, url, hashtags(tags_ja, 3)])
    x_rich = fit_x([hook, "", f"{head}", url, hashtags(tags_ja[:2] + tags_en[:1])])
    out += ["## X", "", "### すぐ使う版", "```", x_simple, "```",
            f"({x_weight(x_simple)}/280)", "", "### 少し凝った版(フック先出し)", "```", x_rich, "```",
            f"({x_weight(x_rich)}/280)", ""]

    # Threads
    summary = work.get("summary", "")
    threads_simple = "\n".join([f"{kind}{head}", "", hook, "", url, "", hashtags(tags_ja, 1)])
    threads_rich = "\n".join([hook, "", summary, "", f"▶ {head}", url, "",
                              "感想をもらえると次の話の燃料になります。", hashtags(tags_ja, 1)])
    out += ["## Threads", "", "### すぐ使う版", "```", threads_simple, "```", "",
            "### 少し凝った版", "```", threads_rich, "```", ""]

    # Instagram
    ig_tags = hashtags(tags_ja + tags_en, 20)
    ig_simple = "\n".join([f"{kind}{head}", "", hook, "",
                           "▶ 続きはプロフィールのリンクから", "", ig_tags])
    ig_rich = "\n".join([hook, "", "・", "・", "・", "", summary, "",
                         f"📖{head}",
                         "▶ プロフィールのリンク(note)から読めます",
                         "保存しておくと、続きを見逃しません。", "", ".", ig_tags])
    out += ["## Instagram", "", "### すぐ使う版", "```", ig_simple, "```", "",
            "### 少し凝った版(保存誘導つき)", "```", ig_rich, "```", ""]

    # TikTok
    tt_tags = hashtags(tags_ja[:3] + tags_en[:2] + sns.get("tiktok_tags", []), 6)
    tt_simple = "\n".join([f"{hook}", f"{head}はプロフィールから", tt_tags])
    tt_rich = "\n".join([f"{hook}", "最後の一行まで読んでほしい。", f"続き→プロフィールのリンク『{work['title']}』", tt_tags])
    out += ["## TikTok", "", "### すぐ使う版", "```", tt_simple, "```", "",
            "### 少し凝った版", "```", tt_rich, "```", ""]
    return "\n".join(out)


def build_checklist(work, ep, platforms, counts, warnings, note_url) -> str:
    when = ep["meta"].get("publish_at", "未定")
    out = [f"# 投稿チェックリスト — {full_title(work, ep)}", "",
           f"- 公開予定：{when}", f"- 文字数：{counts} 字(空白・ルビ除く)", ""]
    if warnings:
        out += ["## ⚠️ 注意", ""] + [f"- {w}" for w in warnings] + [""]
    out += ["## 投稿", ""]
    for p in platforms:
        target = {"note": "note.md", "kakuyomu": "kakuyomu.txt", "narou": "narou.txt", "estar": "estar.txt"}[p]
        link = work.get("links", {}).get(p, "")
        line = f"- [ ] {PLATFORM_LABELS[p]}：`{target}` の中身を貼り付け"
        if link:
            line += f"(作品ページ：{link})"
        out.append(line)
    out += ["", "- タイトル欄にはこれをコピー：", "```", full_title(work, ep), "```", ""]
    out += ["## 告知", "", "- [ ] X", "- [ ] Threads", "- [ ] Instagram", "- [ ] TikTok",
            "", "(文面は `sns.md`)", ""]
    out += ["## 公開後", "",
            "- [ ] 公開した note のURLを原稿の `note_url:` に書く(自動検知される場合は不要)"
            + (f" → 検知済み：{note_url}" if note_url else ""),
            "- [ ] 完結・新作ならトップページ(index.html)の作品カードを更新", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- メイン

def build_work(work_dir: Path, config: dict, latest: list):
    work = load_json(work_dir / "work.json")
    if not work:
        print(f"[publish_kit] skip {work_dir.name}: work.json がありません", file=sys.stderr)
        return []
    episodes = sorted(
        (parse_episode(p) for p in (work_dir / "episodes").glob("*.md")),
        key=lambda e: (int(e["meta"]["episode"]) if str(e["meta"]["episode"]).isdigit() else 0, e["file"]),
    )
    platforms = [p for p in work.get("platforms", ["note"]) if p in PLATFORM_LABELS]
    r18 = bool(work.get("r18"))
    rows = []

    for i, ep in enumerate(episodes):
        next_ep = episodes[i + 1] if i + 1 < len(episodes) else None
        out_dir = OUTPUT_DIR / work_dir.name / Path(ep["file"]).stem
        out_dir.mkdir(parents=True, exist_ok=True)

        count = plain_length(ep["body"])
        warnings = []
        for p in platforms:
            if p in CHAR_LIMITS and count > CHAR_LIMITS[p]:
                warnings.append(f"{PLATFORM_LABELS[p]}の1話上限({CHAR_LIMITS[p]:,}字)を超えています。分割してください。")
        if r18 and "narou" in platforms:
            warnings.append("R18作品は「小説家になろう」本体には投稿できません(ノクターンノベルズを使用)。")

        for p in platforms:
            if p == "note":
                content = build_note(work, ep, config, next_ep)
                (out_dir / "note.md").write_text(content, encoding="utf-8")
            else:
                (out_dir / f"{p}.txt").write_text(build_novel_site(work, ep, p), encoding="utf-8")

        note_url = find_note_url(work, ep, latest)
        (out_dir / "sns.md").write_text(build_sns(work, ep, config, note_url, r18), encoding="utf-8")
        (out_dir / "checklist.md").write_text(
            build_checklist(work, ep, platforms, count, warnings, note_url), encoding="utf-8")

        rows.append({
            "publish_at": ep["meta"].get("publish_at", ""),
            "work": work["title"],
            "episode": episode_label(work, ep),
            "chars": count,
            "path": f"{work_dir.name}/{Path(ep['file']).stem}",
            "note_url": note_url,
            "warnings": len(warnings),
        })
    return rows


def write_schedule(rows: list):
    rows = sorted(rows, key=lambda r: r["publish_at"] or "9999")
    out = ["# 投稿スケジュール", "",
           "自動生成ファイルです(手で編集しない)。原稿は publisher/works/ に置きます。", "",
           "| 公開予定 | 作品 | 話 | 文字数 | note | キット |", "|---|---|---|---|---|---|"]
    for r in rows:
        note = "✅ 公開済" if r["note_url"] else "—"
        warn = " ⚠️" if r["warnings"] else ""
        out.append(f"| {r['publish_at'] or '未定'} | {r['work']} | {r['episode']}{warn} | {r['chars']:,} | {note} "
                   f"| [開く]({r['path']}/checklist.md) |")
    (OUTPUT_DIR / "README.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    config = load_json(CONFIG_PATH, {})
    latest = load_json(LATEST_PATH, [])
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    rows = []
    for work_dir in sorted(p for p in WORKS_DIR.iterdir() if p.is_dir()):
        rows += build_work(work_dir, config, latest)
    write_schedule(rows)
    print(f"[publish_kit] built {len(rows)} episode kit(s) into {OUTPUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
