# Discord Invitation & Role Bot

[![Website](https://img.shields.io/badge/Website-discord--invitation--and--role--bot.kei31.com-orange?style=flat-square)](https://discord-invitation-and-role-bot.kei31.com/)
[![Discord](https://img.shields.io/badge/Discord-Support%20Server-7289DA?style=flat-square)](https://discord.gg/your-support-server)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

**入った瞬間、ロールが手に入る。**

Discordサーバーへの招待リンクに自動ロール付与機能を追加するオープンソースBot。Discord.pyとFlaskを使用した、シンプルで拡張可能なアーキテクチャ。

## 🌟 公式サイト

**https://discord-invitation-and-role-bot.kei31.com/**

エンドユーザー向けの情報、デモ、FAQ は公式サイトをご覧ください。

## 📖 概要

このシステムは3つの主要コンポーネントから構成されています：

1. **Discord Bot** (`discord_bot/`) - スラッシュコマンドでロール招待リンクを生成・管理
2. **Web Application** (`get_role/`) - 招待リンクからDiscordサーバーに参加してロールを取得
3. **公式サイト** (`docs/`) - SEO最適化されたランディングページ

## ✨ 機能

### Discord Bot
- `/generate_invite_link` - ロール招待リンクを生成（管理者専用）
- `/list_server_invite_links` - サーバーの全招待リンクを一覧表示・削除（管理者専用）
- `/list_my_invite_links` - 自分が作成した招待リンクを一覧表示・削除
- 有効期限・使用回数制限の設定
- プレミアムプラン対応（無制限リンク作成）

### Web Application
- 招待リンクからの参加ページ表示
- Discord OAuth2認証
- サーバー参加とロール自動付与
- レート制限とセキュリティ対策
- レスポンシブデザイン

### 公式サイト
- プロジェクト紹介・機能説明
- FAQ・サポート情報
- SEO・LLMO最適化済み

## 🚀 クイックスタート

### 前提条件
- Python 3.8+
- PostgreSQL データベース
- Discord Bot トークン
- Discord OAuth2 アプリケーション

### インストール

1. **リポジトリをクローン**
   ```bash
   git clone https://github.com/tejastice/discord-invitation-and-role-bot.git
   cd discord-invitation-and-role-bot
   ```

2. **Discord Bot セットアップ**
   ```bash
   cd discord_bot
   pip install -r requirements.txt
   cp .env.example .env
   # .envファイルを編集して必要な設定を入力
   ```

3. **Web Application セットアップ**
   ```bash
   cd ../get_role
   pip install -r requirements.txt
   cp .env.example .env
   # .envファイルを編集して必要な設定を入力
   ```

4. **データベース初期化**
   
   PostgreSQLでデータベースを作成し、以下のテーブルを作成：
   ```sql
   CREATE TABLE role_invite_links (
       id SERIAL PRIMARY KEY,
       guild_id BIGINT NOT NULL,
       role_id BIGINT NOT NULL,
       link_id VARCHAR(255) UNIQUE NOT NULL,
       created_by_user_id BIGINT NOT NULL,
       max_uses INTEGER NULL DEFAULT NULL,
       current_uses INTEGER NOT NULL DEFAULT 0,
       expires_at VARCHAR(255) NULL DEFAULT NULL,
       expires_at_unix BIGINT NULL DEFAULT NULL,
       created_at VARCHAR(255) NOT NULL,
       created_at_unix BIGINT NOT NULL
   );

   -- インデックス作成
   CREATE INDEX idx_role_invite_links_guild_id ON role_invite_links(guild_id);
   CREATE INDEX idx_role_invite_links_role_id ON role_invite_links(role_id);
   CREATE INDEX idx_role_invite_links_link_id ON role_invite_links(link_id);
   CREATE INDEX idx_role_invite_links_created_by ON role_invite_links(created_by_user_id);
   ```

### 環境変数設定

#### Discord Bot (`.env`)
```env
# Discord Bot Settings
DISCORD_TOKEN=your_bot_token_here
DISCORD_DEV_GUILD_ID=your_dev_guild_id_here

# Premium Role Settings
PREMIUM_ROLE_ID=your_premium_role_id_here

# Free User Limits
FREE_USER_PERSONAL_LINK_LIMIT=3
FREE_USER_SERVER_LINK_LIMIT=10

# Web App Settings
BASE_URL=http://localhost:5000
DATABASE_URL=postgresql://user:password@host:port/database

# Official Website
OFFICIAL_WEBSITE_URL=https://discord-invitation-and-role-bot.kei31.com
```

詳細な設定方法は [公式サイト](https://discord-invitation-and-role-bot.kei31.com/) をご参照ください。

#### Web Application (`.env`)
```env
# Discord Bot Settings
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_oauth_client_id_here
DISCORD_CLIENT_SECRET=your_oauth_client_secret_here

# Web App Settings
REDIRECT_URI=http://localhost:5000/callback
DATABASE_URL=postgresql://user:password@host:port/database
SECRET_KEY=your_flask_secret_key_here
PORT=5000

# URLs
OFFICIAL_WEBSITE_URL=https://discord-invitation-and-role-bot.kei31.com
DISCORD_SUPPORT_SERVER_URL=https://discord.gg/your-support-server

# Request Settings
REQ_TIMEOUT=5
```

詳細な設定方法は [公式サイト](https://discord-invitation-and-role-bot.kei31.com/) をご参照ください。

### 実行

1. **Discord Botを起動**
   ```bash
   cd discord_bot
   python bot.py
   ```

2. **Web Applicationを起動**
   ```bash
   cd get_role
   python app.py
   ```

## 📋 使用方法

### 管理者側の操作

1. **Botをサーバーに追加**
   - Discord Developer Portalで OAuth2 URLを生成
   - 必要な権限：`Manage Server`, `Manage Roles`

2. **招待リンクを生成**
   ```
   /generate_invite_link role:@役職名 max_uses:10 expires_at:7d
   ```

3. **リンク管理**
   ```
   /list_server_invite_links  # サーバーの全リンクを表示
   /list_my_invite_links      # 自分のリンクを表示
   ```

### ユーザー側の体験

1. 管理者から招待リンクを受け取る
2. リンクをクリックして参加ページを開く
3. 「Discordサーバーに参加する」ボタンをクリック
4. Discord OAuth2認証を完了
5. 自動でサーバー参加 + ロール付与完了

## 🎯 制限管理機能

このBotはプレミアムロール機能により、ユーザーの招待リンク作成制限を制御できます。

### 制限設定の仕組み
- **プレミアムロール**: 特定のロールを持つユーザーは制限なしで利用可能
- **フリーユーザー制限**: プレミアムロールを持たないユーザーの制限を環境変数で設定

### 設定可能な制限項目
```env
# プレミアムロール設定
PREMIUM_ROLE_ID=your_premium_role_id_here

# フリーユーザー制限設定
FREE_USER_PERSONAL_LINK_LIMIT=3    # 個人が作成できる招待リンク数
FREE_USER_SERVER_LINK_LIMIT=10     # サーバー全体で作成できる招待リンク数
```

### 実装詳細
- `has_premium_role()` 関数でユーザーのプレミアム状態を判定
- `check_invite_link_limits()` 関数で制限チェックを実行
- データベースクエリでユーザー・サーバー別のリンク数をカウント

## 🛠️ 開発・デプロイメント

### ローカル開発
```bash
# 開発用データベース起動
docker run --name postgres-dev -e POSTGRES_PASSWORD=password -p 5432:5432 -d postgres

# Botとアプリを同時起動
# ターミナル1
cd discord_bot && python bot.py

# ターミナル2  
cd get_role && python app.py
```

### Herokuデプロイ

1. **Discord Bot用Herokuアプリ作成**
   ```bash
   heroku create your-bot-name
   heroku addons:create heroku-postgresql:hobby-dev
   heroku config:set DISCORD_TOKEN=your_token
   # 他の環境変数も設定
   git subtree push --prefix=discord_bot heroku main
   ```

2. **Web App用Herokuアプリ作成**
   ```bash
   heroku create your-webapp-name
   heroku addons:create heroku-postgresql:hobby-dev
   heroku config:set DISCORD_CLIENT_ID=your_client_id
   # 他の環境変数も設定
   git subtree push --prefix=get_role heroku main
   ```

## 🔒 セキュリティ機能

- **レート制限**: 60秒間に20リクエストまで
- **OAuth2 CSRF対策**: stateパラメータ検証
- **使用制限**: 回数・有効期限管理
- **セキュリティヘッダー**: XSS、フレーム保護
- **データベース**: 接続プールとトランザクション管理

## 🏗️ 技術仕様

- **言語**: Python 3.8+
- **Botライブラリ**: Discord.py 2.3.2
- **Webフレームワーク**: Flask 3.0.0
- **データベース**: PostgreSQL
- **認証**: Discord OAuth2
- **HTTP クライアント**: aiohttp 3.9.1
- **フロントエンド**: HTML5, CSS3, Vanilla JavaScript
- **デプロイ**: Heroku, Docker対応

## 📁 プロジェクト構造

```
invite_role_bot/
├── README.md
├── discord_bot/                 # Discord Bot
│   ├── bot.py                  # メインBotファイル
│   ├── requirements.txt
│   ├── Procfile               # Herokuデプロイ用
│   └── shared/                # 共通モジュール
│       ├── database.py        # DB接続管理
│       └── models.py          # データモデル
├── get_role/                   # Web Application
│   ├── app.py                 # Flask アプリケーション
│   ├── requirements.txt
│   ├── Procfile              # Herokuデプロイ用
│   ├── static/               # 静的ファイル
│   │   └── bot-icon.jpeg
│   └── shared/               # 共通モジュール
│       ├── database.py       # DB接続管理
│       └── models.py         # データモデル
└── docs/                      # 公式サイト
    ├── index.html            # メインページ
    ├── styles.css            # スタイルシート
    ├── script.js             # JavaScript
    ├── privacy.html          # プライバシーポリシー
    ├── terms.html            # 利用規約
    └── images/               # 画像ファイル
        ├── favicon.png
        └── header-image.jpg
```

## 🤝 コントリビューション

プルリクエストやイシューの報告を歓迎します！

1. このリポジトリをフォーク
2. フィーチャーブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📞 サポート

- **公式サイト**: https://discord-invitation-and-role-bot.kei31.com/
- **Discordサポートサーバー**: https://discord.gg/your-support-server

## 📜 ライセンス

このプロジェクトは [MIT License](LICENSE) の下で公開されています。

---

**Discord Invitation & Role Bot** - 入った瞬間、ロールが手に入る。