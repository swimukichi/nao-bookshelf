# note → 他サイト 自動転載

**note がメイン**です。note への投稿(予約投稿)は PC 側の仕組みがこれまでどおり行います。
ここでは、note に公開された話を自動で取り込み、**カクヨム・小説家になろう・エブリスタへ同じ話を投稿**します。
note には一切書き込みません。

## 流れ(1時間ごとに自動)

```
PC側の仕組み → note に予約投稿 → 公開
   ↓ GitHub Actions(毎時10分)
① note の公開済み記事を取り込み、作品ごとの原稿にする
     publisher/works/<作品>/episodes/10.md
② 各サイト用に変換する(ルビ・傍点・字下げ・場面転換)
     publisher/output/<作品>/10/kakuyomu.txt など
③ ブラウザを自動操作して、各サイトに投稿する
     note の公開時刻 + repost_delay_hours が未来 → 各サイトの予約機能で予約
     過ぎている → すぐ公開
④ 投稿済みを publisher/state.json に記録する(二重投稿しない)
```

- 話の順番は守ります。同じ作品で1話失敗したら、以降の話は次の回に回します。
- 実行結果は GitHub の Actions →「Repost note episodes to other sites」で見られます(結果の表と、画面のスクリーンショット)。

## 作品の設定(`publisher/works/<作品>/work.json`)

いま連載中の作品は設定済みです：`meibo`(名簿)、`yoyaku-toukou`(予約投稿は午前零時に開く)、
`asamade`(朝まで温かいもの)、`manin-densha`(満員電車の魔女)、`horror-shorts`(【ホラー短編】→エブリスタ短編集『わたしは正しかった』)。

| 項目 | 説明 |
|---|---|
| `note_match.contains` | note の記事タイトルにこの文字が入っていたら、この作品の話とみなす |
| `note_match.title_regex` | タイトルから話数(`num`)とサブタイトル(`subtitle`)を読む。`num` がない場合は公開順に1, 2, 3…と番号を振る |
| `note_match.since` | (任意)この日付(`2026-09-20` の形式)以降に公開された話だけを取り込む。すでに手で転載済みの話を飛ばすときに使う |
| `note_match.strip_lines` | (任意)他サイトに持っていかない行(正規表現)。冒頭の「━━━」作品紹介ブロック、マガジン案内、noteのURLは最初から外す |
| `platforms` | 転載先の候補。`kakuyomu` `narou` `estar` |
| `auto_post` | **実際に自動投稿するサイト**。空 `[]` の間は取り込み・変換だけ行い、投稿しない |
| `post_urls` | 各サイトの、その作品の「新しいエピソードを書く/次話投稿」画面のURL |
| `links` | 各サイトの作品ページURL(カクヨムはここから投稿画面のURLを自動で作る) |
| `repost_delay_hours` | (任意)note 公開から何時間後に他サイトで公開するか。既定は0(同時刻) |
| `episode_unit` | 話数の表記。`第{n}話` → 第7話、`第{kanji}章` → 第十章 |
| `r18` | `true` にすると、なろう本体への投稿に警告を出す(ノクターンノベルズを使う) |

新しい連載を始めるときは、作品フォルダをコピーして `title` と `note_match` を書き換えます。
**各サイトで先に作品ページ(作品の箱)を作っておく必要があります。** 自動で行うのは、話(エピソード)の追加だけです。

## 最初の設定(サイトごとに1回)

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

   ブラウザ拡張(Cookie-Editor など)でエクスポートした Cookie の JSON をそのまま登録しても動きます。
   ログインが切れると、実行結果に「ログイン画面に移動しました」と出ます。その時は保存し直してください。

2. **work.json に投稿画面のURLを書く**(`post_urls`)

3. **動作確認 → 本番**
   Actions →「Repost note episodes to other sites」→ Run workflow で、モードを選んで実行します。
   - `probe`：投稿画面の入力欄・ボタンの一覧をログに出すだけ(何も入力しない)
   - `dry-run`：タイトル・本文・日時の入力まで行い、最後のボタンは押さない。スクリーンショットが Artifacts に残る
   - `post`：実際に投稿・予約する

   問題がなければ、work.json の `auto_post` に投稿したいサイトを入れます(例：`["kakuyomu", "narou"]`)。
   以後は自動です。

## うまくいかないとき

サイトの画面が変わると、入力欄が見つからずに失敗します。実行結果の「詳細」とスクリーンショットを確認し、
`publisher/poster/selectors.json`(入力欄・ボタンの探し方)を直します。`probe` のログを渡してもらえれば、こちらで直します。

取り込んだ原稿(`publisher/works/<作品>/episodes/*.md`)は手で直しても上書きされません。
その話の投稿前なら、直した内容で投稿されます。

## 原稿の書き方(手で追加する場合)

note を経由せずに原稿を置くこともできます。

```
---
episode: 1
title: 表札
publish_at: 2026-09-25 12:00
---
本文。1行1段落。
|表札《ひょうさつ》 ← ルビ　《《一つ》》 ← 傍点　*** ← 場面転換
```

見本は `publisher/works/sample/` にあります。
