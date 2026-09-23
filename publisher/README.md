# 小説 投稿キット

原稿を1つ書くだけで、各サイト用の本文とSNSの告知文を自動で作り、
**各サイトの予約投稿機能を使って自動で予約**します(下の「自動予約」を参照)。

## 流れ

1. `publisher/works/<作品名>/` に `work.json`(作品情報)と `episodes/01.md`(原稿)を置く
2. main ブランチに push する(GitHub 上で直接ファイルを追加してもOK)
3. GitHub Actions が `publisher/output/` に投稿キットを作る(1〜2分)
4. `publisher/output/README.md` の予定表から、その話の `checklist.md` を開き、上から順に貼り付けて投稿する
5. note に公開すると、6時間ごとのフィード更新で自動的に検知され、告知文のURLが埋まる

手元で作る場合：`python3 scripts/build_publish_kit.py`

## 自動予約

GitHub Actions がブラウザを自動で操作し、各サイトの「予約公開/予約掲載/予約投稿」で予約します。
6時間ごと、または原稿を push したときに動きます。予約済みの話は `publisher/state.json` に記録され、二重には予約しません。

### 最初の設定(サイトごとに1回)

1. **ログイン状態を保存する**(パスワードは GitHub に置きません)
   自分のパソコンで次を実行し、開いたブラウザでログイン → Enter。
   ```
   pip install playwright
   python -m playwright install chromium
   python scripts/save_login.py kakuyomu
   ```
   表示された長い文字列を、GitHub の Settings → Secrets and variables → Actions → New repository secret に登録します。

   | サイト | Secret の名前 |
   |---|---|
   | カクヨム | `KAKUYOMU_STORAGE_STATE` |
   | 小説家になろう | `NAROU_STORAGE_STATE` |
   | エブリスタ | `ESTAR_STORAGE_STATE` |
   | note | `NOTE_STORAGE_STATE` |

   ブラウザ拡張(Cookie-Editor など)でエクスポートした Cookie の JSON をそのまま登録しても動きます。
   ログインが切れると実行結果に「ログイン画面に移動しました」と出るので、その時は保存し直してください。

2. **work.json に投稿画面のURLを書く**
   各サイトで、その作品の「新しいエピソードを書く/次話投稿」画面を開き、アドレスバーのURLを `post_urls` に貼ります。
   (カクヨムは `links.kakuyomu` に作品URLがあれば自動で組み立てます。note は不要)

3. **動作確認 → 本番**
   GitHub の Actions → 「Auto schedule novel posts」→ Run workflow で、モードを選んで実行します。
   - `probe`：投稿画面を開いて、入力欄やボタンの一覧をログに出すだけ(何も入力しない)
   - `dry-run`：タイトル・本文・日時の入力まで行い、最後の予約ボタンは押さない。画面のスクリーンショットが実行結果の Artifacts に残る
   - `post`：実際に予約する

   `dry-run` のスクリーンショットで問題がなければ、work.json の `auto_post` に予約したいサイトを入れます(例：`["kakuyomu", "note"]`)。
   以後は自動です。

### うまくいかないとき

サイトの画面が変わると、入力欄が見つからずに失敗します。実行結果の「詳細」とスクリーンショットを確認し、
`publisher/poster/selectors.json`(入力欄・ボタンの探し方)を直します。`probe` のログを渡してもらえれば、こちらで直します。

## 1話ごとにできるもの

| ファイル | 用途 |
|---|---|
| `note.md` | note用。冒頭の作品紹介ブロック、次回予告、マガジンリンク、CTAつき |
| `kakuyomu.txt` | カクヨム用。ルビ・傍点はカクヨムの記法のまま |
| `narou.txt` | なろう用。傍点は「﹅」のルビに変換 |
| `estar.txt` | エブリスタ用。ルビは「漢字（かんじ）」の括弧書きに変換 |
| `sns.md` | X / Threads / Instagram / TikTok の告知文。どれも「すぐ使う版」と「少し凝った版」の2案 |
| `checklist.md` | 投稿チェックリスト(タイトル欄にコピーする文字列、文字数、注意点) |

## 原稿の書き方(共通記法)

```
---
episode: 1
title: 表札
publish_at: 2026-09-25 12:00
hook: 告知文の1行目に使う、引きの強い一文
note_url: (任意)公開後のURL。自動で見つからないときだけ書く
---
本文。1行1段落。空行は空行として残ります。

|表札《ひょうさつ》       ← ルビ(漢字だけなら 表札《ひょうさつ》 でも可)
《《一つ》》              ← 傍点
***                       ← 場面転換(「◇　◇　◇」/ note では「───」)
[画像: 説明]              ← note にだけ「【画像挿入：説明】」として残る
```

- 行頭の字下げ(全角スペース)は自動です。「」『』などで始まる行には付きません。note では字下げしません。
- 字下げを止めたい作品は `work.json` の `"indent": false` にしてください。

## work.json の項目

| 項目 | 説明 |
|---|---|
| `title` / `title_prefix` | 作品名 / 頭に付ける文字列(例：`【ホラー長編】`) |
| `genre_label` / `catch` / `summary` | note冒頭とSNSで使う ジャンル / キャッチコピー / あらすじ |
| `episode_unit` | 話数の書き方。`第{n}話` → 第1話、`第{kanji}章` → 第十章 |
| `total_episodes` / `status` | 全話数 / `連載中` か `完結` |
| `r18` | `true` にすると、SNSに注意書きが付き、なろうへの投稿に警告が出る |
| `tags` / `tags_en` | ハッシュタグ(日本語 / 英語)。`config.json` の共通タグと合わせて使う |
| `platforms` | 投稿先。`note` `kakuyomu` `narou` `estar` から選ぶ |
| `links` | noteマガジン・各サイトの作品ページURL |
| `post_urls` | 各サイトの「新しい話を書く」画面のURL(自動予約用) |
| `auto_post` | 自動予約するサイト。空 `[]` の間は予約しない(`probe`/`dry-run` は可能) |

`publisher/works/sample/` が見本です。フォルダごとコピーして書き換えてください(見本は不要になったら削除してOK)。
