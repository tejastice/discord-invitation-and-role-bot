# Discord Role Invitation Bot

Discord サーバーでロール付与のための招待リンクを生成・管理するシステムです。

## 概要

このシステムは2つの主要コンポーネントから構成されています：

1. **Discord Bot** (`discord_bot/`) - スラッシュコマンドでロール招待リンクを生成・管理
2. **Web Application** (`get_role/`) - 招待リンクからDiscordサーバーに参加してロールを取得

## 機能

### Discord Bot
- `/generate_invite_link` - ロール招待リンクを生成（管理者専用）
- `/list_server_invite_links` - サーバーの全招待リンクを一覧表示・削除（管理者専用）
- `/list_my_invite_links` - 自分が作成した招待リンクを一覧表示・削除

### Web Application
- 招待リンクからの参加ページ表示
- Discord OAuth2認証
- サーバー参加とロール自動付与
- 使用回数・有効期限の管理

## セットアップ

### 前提条件
- Python 3.8+
- PostgreSQL データベース
- Discord Bot トークン
- Discord OAuth2 アプリケーション

### 環境変数

各ディレクトリに `.env` ファイルを作成してください：

#### Discord Bot (.env)
```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_DEV_GUILD_ID=your_dev_guild_id_here
BASE_URL=http://localhost:5000
DATABASE_URL=postgresql://user:password@host:port/database
```

#### Web App (.env)
```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_oauth_client_id_here
DISCORD_CLIENT_SECRET=your_oauth_client_secret_here
DISCORD_GUILD_ID=your_guild_id_here
BASE_URL=http://localhost:5000
DATABASE_URL=postgresql://user:password@host:port/database
SECRET_KEY=your_flask_secret_key_here
```

### インストールと実行

#### Discord Bot
```bash
cd discord_bot
pip install -r requirements.txt
python bot.py
```

#### Web Application
```bash
cd get_role
pip install -r requirements.txt
python app.py
```

## データベース

PostgreSQLテーブル構造：

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
```

## 使用方法

1. Discord Botを起動
2. Web アプリケーションを起動
3. Discordサーバーで `/generate_invite_link` コマンドを使用してロール招待リンクを生成
4. 生成されたリンクをユーザーに共有
5. ユーザーがリンクをクリックしてサーバー参加・ロール取得

## ライセンス

MIT License

## 開発者

Created with Claude Code