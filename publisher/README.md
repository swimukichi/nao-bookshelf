# 小説 投稿キット

原稿を1つ書くだけで、各サイトに貼るだけの状態の本文と、SNSの告知文を自動で作ります。
**投稿ボタンを押すのは自分**です。note・カクヨム・なろう・エブリスタには、外部から投稿する公式の仕組み(API)がありません。

## 流れ

1. `publisher/works/<作品名>/` に `work.json`(作品情報)と `episodes/01.md`(原稿)を置く
2. main ブランチに push する(GitHub 上で直接ファイルを追加してもOK)
3. GitHub Actions が `publisher/output/` に投稿キットを作る(1〜2分)
4. `publisher/output/README.md` の予定表から、その話の `checklist.md` を開き、上から順に貼り付けて投稿する
5. note に公開すると、6時間ごとのフィード更新で自動的に検知され、告知文のURLが埋まる

手元で作る場合：`python3 scripts/build_publish_kit.py`

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

`publisher/works/sample/` が見本です。フォルダごとコピーして書き換えてください(見本は不要になったら削除してOK)。
