#!/usr/bin/env python3
"""原稿ごとの Higgsfield プロンプト(episodes/NN.visual.md)から、サムネ画像を自動で生成する。

- 生成先: publisher/works/<作品>/images/<NN>-<用途>.<拡張子>
- すでに画像がある話は作り直さない(クレジットを無駄にしないため)。作り直したいときは画像を消す。
- 認証は Higgsfield の API キー(環境変数 HF_KEY = "APIキー:シークレット")。GitHub の Secrets に登録する。
- 生成した note 用の画像は、auto_post.py が note の見出し画像として貼り付ける。

使う用途・モデル・比率は publisher/config.json の "higgsfield" で変えられる。
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_publish_kit as kit  # noqa: E402

DEFAULTS = {
    "model": "bytedance/seedream/v4/text-to-image",
    "resolution": "2K",
    "variant": "少し凝った版",
    # visual.md の見出し(## の行)に含まれる文字 → 用途名と比率
    "kinds": [
        {"name": "note", "heading": "note", "aspect_ratio": "16:9"},
    ],
}


def extract_prompt(visual_text: str, heading_key: str, variant: str):
    """visual.md から、指定した見出し・版のプロンプトを取り出す。(prompt, negative)"""
    sections = re.split(r"^## ", visual_text, flags=re.M)
    section = next((s for s in sections if heading_key in s.split("\n", 1)[0]), None)
    if section is None:
        return None, None
    parts = re.split(r"^### ", section, flags=re.M)
    part = next((p for p in parts if variant in p.split("\n", 1)[0]), None) or (parts[1] if len(parts) > 1 else None)
    if part is None:
        return None, None
    m = re.search(r"```(?:\w+)?\n(.*?)```", part, flags=re.S)
    if not m:
        return None, None
    lines = m.group(1).strip().split("\n")
    negative = ""
    kept = []
    for line in lines:
        if line.lower().startswith("negative:"):
            negative = line.split(":", 1)[1].strip()
        else:
            kept.append(line)
    prompt = " ".join(l.strip() for l in kept if l.strip())
    # 比率はAPIの引数で指定するので、プロンプト中の比率指定は外す
    prompt = re.sub(r",?\s*aspect ratio [0-9.:]+", "", prompt)
    return prompt, negative


def download(url: str, dest_base: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "nao-bookshelf-bot/1.0"})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = res.read()
        ctype = res.headers.get("Content-Type", "")
    ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpg"
    path = dest_base.with_suffix(ext)
    path.write_bytes(data)
    return path


def existing_image(work_dir: Path, stem: str, kind: str):
    for path in (work_dir / "images").glob(f"{stem}-{kind}.*"):
        return path
    return None


def main() -> int:
    config = {**DEFAULTS, **kit.load_json(kit.CONFIG_PATH, {}).get("higgsfield", {})}
    if not (os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET"))):
        print("[thumbnails] Higgsfield の API キー(Secret HF_KEY)が未登録のため、生成しません")
        return 0

    todo = []
    for work_dir in sorted(p for p in kit.WORKS_DIR.iterdir() if p.is_dir()):
        for visual in sorted((work_dir / "episodes").glob("*.visual.md")):
            stem = visual.name.split(".")[0]
            text = visual.read_text(encoding="utf-8")
            for kind in config["kinds"]:
                if existing_image(work_dir, stem, kind["name"]):
                    continue
                prompt, negative = extract_prompt(text, kind["heading"], config["variant"])
                if not prompt:
                    print(f"[skip] {visual.relative_to(kit.ROOT)} に「{kind['heading']}」のプロンプトがありません")
                    continue
                todo.append((work_dir, stem, kind, prompt, negative))

    if not todo:
        print("[thumbnails] 生成する画像はありません")
        return 0

    import higgsfield_client

    failed = 0
    for work_dir, stem, kind, prompt, negative in todo:
        label = f"{work_dir.name}/{stem}-{kind['name']}"
        full_prompt = prompt + (f". Avoid: {negative}" if negative else "")
        print(f"[thumbnails] 生成中 {label} ({kind['aspect_ratio']})")
        try:
            result = higgsfield_client.subscribe(
                config["model"],
                arguments={
                    "prompt": full_prompt,
                    "resolution": config["resolution"],
                    "aspect_ratio": kind["aspect_ratio"],
                },
            )
            url = result["images"][0]["url"]
            (work_dir / "images").mkdir(exist_ok=True)
            path = download(url, work_dir / "images" / f"{stem}-{kind['name']}")
            print(f"  → {path.relative_to(kit.ROOT)}")
        except Exception as exc:  # noqa: BLE001 - 1枚の失敗で全体を止めない
            failed += 1
            print(f"  ✗ {label}: {exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
