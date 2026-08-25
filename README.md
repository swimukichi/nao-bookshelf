# NAOの小説箱 — 紹介ホームページ

note マガジン「NAOの小説箱」(https://note.com/swi0801/m/me98fd692c5c2) を紹介する静的サイトです。
HTML / CSS / JS のみで作られており、外部ライブラリやビルドツールは使っていません。

## ファイル構成

- `index.html` — ページ本体
- `style.css` — デザイン
- `script.js` — ハンバーガーメニューなどの簡単な動き
- `images/` — 画像を追加したい場合はここに置く(現状プロフィール画像はnoteの画像を直接参照しています)

## 手元で見る

このフォルダで以下を実行してブラウザで `http://localhost:8000` を開くと確認できます。

```bash
python3 -m http.server 8000
```

(`index.html` をダブルクリックして直接開くこともできますが、その場合CSS/JSが正しく読み込まれないことがあります)

## 無料で公開する方法(おすすめ: GitHub Pages)

1. GitHubで新しいリポジトリを作成する
2. このフォルダの中身(`index.html`, `style.css`, `script.js`)をリポジトリにアップロードする
3. リポジトリの Settings → Pages で「Deploy from a branch」を選び、`main` ブランチを指定する
4. 数分後、`https://ユーザー名.github.io/リポジトリ名/` でサイトが公開されます(完全無料)

他にも Netlify や Cloudflare Pages の「フォルダをドラッグ&ドロップ」機能でも無料で公開できます。

## 内容を更新したいとき

- 新しい記事を追加したい → `index.html` 内の `#latest` セクション(更新情報)の `<li>` をコピーして追記
- 作品カードを追加・変更したい → `#works` セクションの `.work-card` をコピーして編集
- R18作品は `tag-r18` クラスのバッジと注意書きを付けて掲載しています。表現方法を変えたい場合はそのカード内の文章を調整してください

## 注意

- プロフィール画像は note.com にアップロードされている画像を直接参照しています。将来リンク切れした場合は `images/` フォルダに保存し直し、`index.html` の `src` を差し替えてください
- SNSリンク(X, Instagram, YouTube, TikTok)は note プロフィールに記載のものを使用しています
