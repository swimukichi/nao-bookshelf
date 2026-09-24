#!/usr/bin/env python3
"""原稿を各サイトの予約機能で自動投稿する。

原稿は2種類ある:
  - note から取り込んだ話(sync_from_note.py が作る。note_key あり)
      → note には PC 側の仕組みが投稿済みなので、カクヨム・なろう・エブリスタにだけ流す
  - このリポジトリで書いた話(note_key なし)
      → note を含め、work.json の auto_post にあるサイトすべてに投稿する
publish_at が未来なら各サイトの予約機能で予約し、過ぎていればすぐ公開する。

GitHub Actions から実行する。ログインは保存済みのログイン状態(Cookie)を
Secrets から読み込んで行う(パスワードは使わない)。

モード:
  probe    投稿画面を開いて、入力欄やボタンの一覧をログに出す(画面の調査用・何も入力しない)
  dry-run  入力と日時設定まで行い、最後のボタンは押さない(スクリーンショットを保存)
  post     投稿/予約まで実行し、publisher/state.json に記録する

投稿済みの話は state.json に記録され、二重に投稿されることはない。
同じ作品・同じサイトで1話失敗したら、話の順番が狂わないよう以降の話は次回に回す。
"""
import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_publish_kit as kit  # noqa: E402

JST = timezone(timedelta(hours=9))
PUBLISHER_DIR = kit.PUBLISHER_DIR
STATE_PATH = PUBLISHER_DIR / "state.json"
SELECTORS_PATH = PUBLISHER_DIR / "poster" / "selectors.json"
ARTIFACT_DIR = PUBLISHER_DIR / "poster" / "artifacts"
PLATFORMS = ["note", "kakuyomu", "narou", "estar"]
SECRET_NAMES = {p: f"{p.upper()}_STORAGE_STATE" for p in PLATFORMS}


class LoginExpired(Exception):
    pass


class NotFound(Exception):
    pass


# ---------------------------------------------------------------- 準備

def load_storage_state(platform: str):
    """Secret の中身(base64 または JSON)を Playwright の storage_state にする。

    Playwright の storage_state 形式と、ブラウザ拡張でエクスポートした
    Cookie 配列の形式のどちらでも受け付ける。
    """
    raw = os.environ.get(SECRET_NAMES[platform], "").strip()
    if not raw:
        return None
    if not raw.startswith(("{", "[")):
        raw = base64.b64decode(raw).decode("utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and "cookies" in data:
        return data
    cookies = []
    for c in data:
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", True)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }
        expires = c.get("expirationDate") or c.get("expires")
        if expires:
            cookie["expires"] = int(float(expires))
        same_site = str(c.get("sameSite", "")).lower()
        cookie["sameSite"] = {"strict": "Strict", "lax": "Lax", "none": "None",
                              "no_restriction": "None"}.get(same_site, "Lax")
        cookies.append(cookie)
    return {"cookies": cookies, "origins": []}


def parse_publish_at(value: str):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


def post_url(platform: str, work: dict, selectors: dict) -> str:
    """その作品の「新しい話を書く」画面のURL。"""
    urls = work.get("post_urls", {})
    if urls.get(platform):
        return urls[platform]
    if platform == "note":
        return selectors["note"]["new_url"]
    if platform == "kakuyomu":
        m = re.search(r"kakuyomu\.jp/works/(\d+)", work.get("links", {}).get("kakuyomu", ""))
        if m:
            return selectors["kakuyomu"]["new_episode_url"].format(work_id=m.group(1))
    return ""


def collect_jobs(config: dict, selectors: dict, state: dict, only_platform: str, only_target: str, mode: str):
    """予約すべき (作品, 話, 投稿先) の一覧を作る。"""
    window = int(config.get("auto_post", {}).get("window_days", 30))
    margin = int(config.get("auto_post", {}).get("min_lead_minutes", 15))
    now = datetime.now(JST)
    jobs, skipped = [], []

    for work_dir in sorted(p for p in kit.WORKS_DIR.iterdir() if p.is_dir()):
        work = kit.load_json(work_dir / "work.json")
        if not work:
            continue
        targets = work.get("auto_post", [])
        if mode != "post" and not targets:
            # 調査・入力テストは、まだ自動予約を有効にしていない作品でも行えるようにする
            targets = work.get("platforms", [])
        targets = [p for p in targets if p in PLATFORMS]
        for ep_path in sorted((work_dir / "episodes").glob("*.md")):
            ep = kit.parse_episode(ep_path)
            key = f"{work_dir.name}/{ep_path.stem}"
            if only_target and only_target != key and only_target != work_dir.name:
                continue
            when = parse_publish_at(ep["meta"].get("publish_at", ""))
            for platform in targets:
                if only_platform and platform != only_platform:
                    continue
                if platform == "note" and ep["meta"].get("note_key"):
                    continue  # note から取り込んだ話は note に投稿済み
                done = state.get(key, {}).get(platform, {})
                if mode == "post" and done.get("status") == "scheduled":
                    continue
                reason = None
                if not when:
                    reason = "publish_at がない/読めない"
                elif mode == "post" and when > now + timedelta(days=window):
                    reason = f"まだ先({window}日以内になったら予約)"
                elif not post_url(platform, work, selectors):
                    reason = "work.json の post_urls に投稿画面のURLがない"
                if reason:
                    skipped.append((key, platform, reason))
                    continue
                jobs.append({"key": key, "work": work, "ep": ep, "platform": platform,
                             "when": when, "url": post_url(platform, work, selectors),
                             # 公開予定が過ぎている/直前なら、予約せずにすぐ公開する
                             "immediate": when < now + timedelta(minutes=margin)})
    return jobs, skipped


# ---------------------------------------------------------------- 画面操作

def first(page, candidates, timeout=4000, required=True):
    """候補のセレクタを順に試し、最初に見えたものを返す。"""
    for sel in candidates or []:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:  # noqa: BLE001
            continue
    if required:
        raise NotFound(f"見つからない: {candidates}")
    return None


def ensure_logged_in(page):
    if re.search(r"/login|/signin|login\.", page.url):
        raise LoginExpired("ログイン画面に移動しました。ログイン状態(Secret)を保存し直してください。")


def select_value(loc, value: int):
    for v in (str(value), f"{value:02d}", f"{value}年", f"{value}月", f"{value}日", f"{value}時", f"{value}分"):
        try:
            loc.select_option(value=v, timeout=1500)
            return
        except Exception:  # noqa: BLE001
            try:
                loc.select_option(label=v, timeout=1500)
                return
            except Exception:  # noqa: BLE001
                continue
    raise NotFound(f"選択肢に {value} がない")


def set_datetime(page, sel: dict, when: datetime) -> str:
    loc = first(page, sel.get("datetime_local"), timeout=1500, required=False)
    if loc:
        loc.fill(when.strftime("%Y-%m-%dT%H:%M"))
        return "datetime-local"
    date_loc = first(page, sel.get("date"), timeout=1500, required=False)
    time_loc = first(page, sel.get("time"), timeout=1500, required=False)
    if date_loc and time_loc:
        date_loc.fill(when.strftime("%Y-%m-%d"))
        time_loc.fill(when.strftime("%H:%M"))
        return "date+time"
    selects = sel.get("selects") or {}
    if selects:
        parts = {"year": when.year, "month": when.month, "day": when.day,
                 "hour": when.hour, "minute": when.minute}
        found = False
        for name, value in parts.items():
            loc = first(page, selects.get(name), timeout=1500, required=False)
            if loc:
                select_value(loc, value)
                found = True
        if found:
            return "selects"
    raise NotFound("予約日時の入力欄が見つからない")


def paste_html(page, target, html: str, text: str):
    """リッチエディタ(note)に貼り付けとして本文を入れる。"""
    target.click()
    target.evaluate(
        """(el, [html, text]) => {
            el.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', text);
            el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
        }""",
        [html, text],
    )


def note_html(text: str) -> str:
    import html as h
    out = []
    for block in re.split(r"\n{2,}", text.strip()):
        lines = [h.escape(line) for line in block.split("\n")]
        lines = [re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line) for line in lines]
        out.append("<p>" + "<br>".join(lines) + "</p>")
    return "".join(out)


def dump_form(page, label: str):
    """probe 用: 画面の入力欄・ボタンをログに出す。"""
    items = page.evaluate(
        """() => Array.from(document.querySelectorAll(
              'input, textarea, select, button, [contenteditable=true], label, a[href*="new"], a[href*="episode"]'))
            .filter(el => el.offsetParent !== null || el.type === 'hidden')
            .slice(0, 250)
            .map(el => ({
              tag: el.tagName.toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
              cls: (el.className && el.className.toString().slice(0, 60)) || '',
              placeholder: el.placeholder || '', value: (el.value || '').toString().slice(0, 40),
              text: (el.innerText || '').trim().slice(0, 40),
              href: el.getAttribute('href') || '',
              options: el.tagName === 'SELECT' ? Array.from(el.options).slice(0, 5).map(o => o.value + ':' + o.text) : undefined,
            }))"""
    )
    print(f"\n===== PROBE {label} =====\nURL: {page.url}\nTITLE: {page.title()}")
    for it in items:
        print(json.dumps({k: v for k, v in it.items() if v}, ensure_ascii=False))
    print(f"===== END {label} =====\n")


def shot(page, name: str):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"{name.replace('/', '_')}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:  # noqa: BLE001
        pass
    return path


# ---------------------------------------------------------------- 投稿処理

def run_form_site(page, job, sel, mode, title, body):
    """カクヨム・なろう・エブリスタ(テキストエリア型の投稿画面)。"""
    page.goto(job["url"], wait_until="domcontentloaded")
    ensure_logged_in(page)
    if mode == "probe":
        dump_form(page, f"{job['platform']} {job['key']}")
        shot(page, f"probe_{job['platform']}_{job['key']}")
        return "probed", page.url

    first(page, sel["title"]).fill(title)
    first(page, sel["body"]).fill(body)
    if job["immediate"]:
        print("  公開予定を過ぎているため、すぐ公開する")
        submit = sel.get("submit_now") or sel["submit"]
    else:
        toggle = first(page, sel.get("reserve_toggle"), timeout=3000, required=False)
        if toggle:
            toggle.click()
        method = set_datetime(page, sel, job["when"])
        print(f"  日時入力: {method}")
        submit = sel["submit"]
    shot(page, f"{mode}_{job['platform']}_{job['key']}")
    if mode == "dry-run":
        return "dry-run", page.url

    page.on("dialog", lambda d: d.accept())
    first(page, submit).click()
    page.wait_for_load_state("domcontentloaded")
    confirm = first(page, sel.get("confirm"), timeout=3000, required=False)
    if confirm:
        confirm.click()
        page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    shot(page, f"done_{job['platform']}_{job['key']}")
    content = page.content()
    if not any(t in content for t in sel.get("success_text", [])):
        raise NotFound("予約完了の表示を確認できなかった(スクリーンショットを確認してください)")
    return "scheduled", page.url.split("?")[0]


def run_note(page, job, sel, mode, title, body, tags):
    page.goto(job["url"], wait_until="domcontentloaded")
    ensure_logged_in(page)
    page.wait_for_timeout(3000)
    if mode == "probe":
        dump_form(page, f"note editor {job['key']}")
        shot(page, f"probe_note_{job['key']}")
        opener = first(page, sel.get("open_publish"), timeout=3000, required=False)
        if opener and opener.is_enabled():
            opener.click()
            page.wait_for_timeout(2500)
            dump_form(page, f"note publish settings {job['key']}")
            shot(page, f"probe_note_settings_{job['key']}")
        return "probed", page.url

    first(page, sel["title"]).fill(title)
    paste_html(page, first(page, sel["body"]), note_html(body), body)
    page.wait_for_timeout(1500)
    first(page, sel["open_publish"]).click()
    page.wait_for_timeout(2500)
    tag_input = first(page, sel.get("hashtag_input"), timeout=2000, required=False)
    if tag_input:
        for tag in tags[:10]:
            tag_input.fill(tag)
            tag_input.press("Enter")
    if job["immediate"]:
        print("  公開予定を過ぎているため、すぐ公開する")
        submit = sel.get("submit_now") or sel["submit"]
    else:
        toggle = first(page, sel.get("reserve_toggle"), timeout=3000, required=False)
        if toggle:
            toggle.click()
        method = set_datetime(page, sel, job["when"])
        print(f"  日時入力: {method}")
        submit = sel["submit"]
    shot(page, f"{mode}_note_{job['key']}")
    if mode == "dry-run":
        return "dry-run", page.url

    first(page, submit).click()
    confirm = first(page, sel.get("confirm"), timeout=3000, required=False)
    if confirm:
        confirm.click()
    page.wait_for_timeout(4000)
    shot(page, f"done_note_{job['key']}")
    if not any(t in page.content() for t in sel.get("success_text", [])):
        raise NotFound("予約完了の表示を確認できなかった(スクリーンショットを確認してください)")
    return "scheduled", page.url.split("?")[0]


def kit_text(job, platform):
    out = kit.OUTPUT_DIR / job["key"]
    path = out / ("note.md" if platform == "note" else f"{platform}.txt")
    if not path.exists():
        raise NotFound(f"{path} がない(先に build_publish_kit.py を実行)")
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["probe", "dry-run", "post"], default="post")
    parser.add_argument("--platform", default="", help="note / kakuyomu / narou / estar(空なら全部)")
    parser.add_argument("--target", default="", help="作品フォルダ名 または 作品/話(例: sample/01)")
    parser.add_argument("--check", action="store_true", help="対象があるかだけ調べる(GitHub Actions 用)")
    args = parser.parse_args()

    config = kit.load_json(kit.CONFIG_PATH, {})
    selectors = kit.load_json(SELECTORS_PATH, {})
    state = kit.load_json(STATE_PATH, {}) or {}

    jobs, skipped = collect_jobs(config, selectors, state, args.platform, args.target, args.mode)
    for key, platform, reason in skipped:
        print(f"[skip] {key} {platform}: {reason}")
    if args.check:
        print(f"[auto_post] 対象 {len(jobs)} 件")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write(f"jobs={len(jobs)}\n")
        return 0
    if not jobs:
        print("[auto_post] 予約する話はありません")
        write_summary([], skipped)
        return 0

    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for platform in PLATFORMS:
            pjobs = [j for j in jobs if j["platform"] == platform]
            if not pjobs:
                continue
            storage = load_storage_state(platform)
            if storage is None:
                for j in pjobs:
                    results.append((j, "error", f"Secret {SECRET_NAMES[platform]} が未設定"))
                continue
            context = browser.new_context(storage_state=storage, locale="ja-JP",
                                          timezone_id="Asia/Tokyo", viewport={"width": 1280, "height": 900})
            failed = set()
            for job in pjobs:
                chain = job["key"].split("/")[0]
                if chain in failed:
                    results.append((job, "error", "前の話が失敗したため次回に回す"))
                    continue
                page = context.new_page()
                page.set_default_timeout(20000)
                print(f"[auto_post] {args.mode} {platform} {job['key']} → {job['when']:%Y-%m-%d %H:%M}")
                try:
                    work, ep = job["work"], job["ep"]
                    body = kit_text(job, platform)
                    if platform == "note":
                        tags = work.get("tags", []) + config.get("sns", {}).get("default_tags", [])
                        status, url = run_note(page, job, selectors["note"], args.mode,
                                               kit.note_title(work, ep), body, tags)
                    else:
                        status, url = run_form_site(page, job, selectors[platform], args.mode,
                                                    kit.episode_label(work, ep), body)
                    results.append((job, status, url))
                    if status == "scheduled":
                        state.setdefault(job["key"], {})[platform] = {
                            "status": "scheduled",
                            "published_now": job["immediate"],
                            "publish_at": job["when"].strftime("%Y-%m-%d %H:%M"),
                            "scheduled_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                            "url": url,
                        }
                        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
                except Exception as exc:  # noqa: BLE001 - 1件の失敗で全体を止めない
                    failed.add(chain)
                    shot(page, f"error_{platform}_{job['key']}")
                    results.append((job, "error", str(exc).splitlines()[0][:200]))
                    print(f"  ✗ {exc}", file=sys.stderr)
                finally:
                    page.close()
            context.close()
        browser.close()

    write_summary(results, skipped)
    return 1 if any(r[1] == "error" for r in results) else 0


def write_summary(results, skipped):
    lines = ["## 自動予約の結果", "", "| 話 | 投稿先 | 公開予定 | 結果 | 詳細 |", "|---|---|---|---|---|"]
    icons = {"scheduled": "✅ 投稿/予約済", "dry-run": "🟡 入力のみ", "probed": "🔍 調査", "error": "❌ 失敗"}
    for job, status, detail in results:
        lines.append(f"| {job['key']} | {kit.PLATFORM_LABELS[job['platform']]} | "
                     f"{job['when']:%m/%d %H:%M} | {icons.get(status, status)} | {detail} |")
    if skipped:
        lines += ["", "<details><summary>対象外</summary>", ""]
        lines += [f"- {k} {kit.PLATFORM_LABELS[p]}：{r}" for k, p, r in skipped]
        lines += ["", "</details>"]
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
