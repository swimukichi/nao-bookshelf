#!/usr/bin/env python3
"""自分のパソコンで実行し、各サイトのログイン状態を GitHub Secret 用の文字列にする。

使い方:
  pip install playwright
  python -m playwright install chromium
  python scripts/save_login.py kakuyomu      # narou / estar / note も同じ

ブラウザが開くので普段どおりログインし、ターミナルに戻って Enter を押す。
表示された文字列を GitHub の Settings → Secrets and variables → Actions に
KAKUYOMU_STORAGE_STATE などの名前で登録する。
この文字列はログインそのものなので、他人に見せたり、ファイルとしてコミットしたりしないこと。
"""
import base64
import json
import sys

LOGIN_URLS = {
    "kakuyomu": "https://kakuyomu.jp/login",
    "narou": "https://syosetu.com/login/input/",
    "estar": "https://estar.jp/login",
    "note": "https://note.com/login",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in LOGIN_URLS:
        print(f"使い方: python scripts/save_login.py [{' | '.join(LOGIN_URLS)}]")
        return 1
    platform = sys.argv[1]
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(LOGIN_URLS[platform])
        input("ブラウザでログインしてください(「ログイン状態を保持」があればチェック)。終わったら Enter: ")
        state = context.storage_state()
        browser.close()

    encoded = base64.b64encode(json.dumps(state).encode("utf-8")).decode("ascii")
    print(f"\n↓ これを Secret「{platform.upper()}_STORAGE_STATE」に貼り付け ↓\n")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
