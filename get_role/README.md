# Discord Role Invite Bot

URLにアクセスするとDiscordサーバーに参加してロールが付与されるWebアプリケーションです。

## 機能

- 特定のロール用の招待リンク生成
- OAuth2認証によるDiscordサーバー参加
- 自動ロール付与
- 通知チャンネルへの参加通知
- レート制限とセキュリティ対策

## セットアップ

### 1. 環境準備

```bash
# 仮想環境を作成（推奨）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# または
# venv\Scripts\activate  # Windows

# 依存関係をインストール
pip install -r requirements.txt
```

### 2. Discord Application設定

1. [Discord Developer Portal](https://discord.com/developers/applications)でアプリケーションを作成
2. Bot設定でトークンを取得
3. OAuth2設定で以下を設定：
   - Redirect URI: `http://localhost:5000/callback` (開発時)
   - Scopes: `identify`, `guilds.join`
   - Bot Permissions: `Manage Roles`

### 3. データベース設定

PostgreSQLデータベースを準備し、以下のテーブルが自動作成されます：

```sql
CREATE TABLE role_invite_links (
    id SERIAL PRIMARY KEY,
    role_id BIGINT NOT NULL,
    link_id VARCHAR(255) UNIQUE NOT NULL,
    created_by_user_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4. 環境変数設定

`.env.example`をコピーして`.env`ファイルを作成し、以下の値を設定：

```env
# Discord Bot Settings
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here
DISCORD_GUILD_ID=1234567890123456789
DISCORD_NOTIFICATION_CHANNEL_ID=1234567890123456789

# Web App Settings
REDIRECT_URI=http://localhost:5000/callback
SECRET_KEY=your_secret_key_here
PORT=5000

# Database Settings
DATABASE_URL=postgresql://user:password@host:port/database
```

## 使用方法

### アプリケーション起動

```bash
python app.py
```

### ロール招待リンクの作成

データベースに直接レコードを追加するか、管理用のスクリプトを作成して以下のような招待リンクを生成：

```python
from shared.models import create_role_invite_link
import secrets

# ユニークなリンクIDを生成
link_id = secrets.token_urlsafe(16)

# ロール招待リンクを作成
create_role_invite_link(
    role_id=1234567890123456789,  # DiscordロールID
    link_id=link_id,
    created_by_user_id=987654321098765432  # 作成者のユーザーID
)

print(f"招待リンク: http://localhost:5000/join/{link_id}")
```

### ユーザーの招待フロー

1. ユーザーが招待リンク（`/join/<link_id>`）にアクセス
2. Discord OAuth2認証画面にリダイレクト
3. ユーザーが認証を完了
4. サーバーに参加し、指定されたロールが付与される
5. 成功ページが表示される
6. 通知チャンネルに参加通知が送信される

## デプロイ

### Heroku

```bash
# Herokuアプリ作成
heroku create your-app-name

# PostgreSQLアドオン追加
heroku addons:create heroku-postgresql:mini

# 環境変数設定
heroku config:set DISCORD_TOKEN=your_token
heroku config:set DISCORD_CLIENT_ID=your_client_id
heroku config:set DISCORD_CLIENT_SECRET=your_client_secret
heroku config:set DISCORD_GUILD_ID=your_guild_id
heroku config:set DISCORD_NOTIFICATION_CHANNEL_ID=your_notification_channel_id
heroku config:set REDIRECT_URI=https://your-app-name.herokuapp.com/callback
heroku config:set SECRET_KEY=your_secret_key

# デプロイ
git push heroku main
```

## セキュリティ機能

- OAuth2 state パラメータによるCSRF対策
- セッションベースのリンク検証
- IPベースのレート制限（60秒間に20リクエスト）
- エラーハンドリングと適切なログ出力

## トラブルシューティング

### よくある問題

1. **Bot権限不足**: Botに`Manage Roles`権限があることを確認
2. **データベース接続エラー**: 環境変数とデータベース設定を確認
3. **OAuth2エラー**: Redirect URIが正確に設定されているか確認
4. **ロール付与失敗**: Botのロールがターゲットロールより上位にあることを確認

### ログ確認

アプリケーションはコンソールにログを出力します：

```bash
python app.py
```

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。