# Discord Bot

招待リンク管理用のDiscord Botです。

## 機能

- **基本コマンド**
  - `!ping` - Botの応答確認
  - `!info` - Bot情報表示
  - `!roles` - サーバーのロール一覧表示

- **イベント処理**
  - メンバー参加時の通知
  - メンバー退出時のログ
  - エラーハンドリング

- **自動設定**
  - Botステータス表示
  - ウェルカムメッセージ（オプション）

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数設定

`.env.example`をコピーして`.env`ファイルを作成：

```env
# Discord Bot Settings
DISCORD_TOKEN=your_bot_token_here
DISCORD_DEV_GUILD_ID=your_dev_guild_id_here

# Optional Settings
WELCOME_CHANNEL_ID=your_welcome_channel_id_here
```

### 3. Discord Application設定

1. [Discord Developer Portal](https://discord.com/developers/applications)でアプリケーションを作成
2. Bot設定でトークンを取得
3. Bot Permissions:
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
   - `Use Slash Commands`
   - `Manage Roles`（将来の機能用）

### 4. Bot招待

OAuth2 URL Generator で以下のスコープと権限を選択：
- Scopes: `bot`, `applications.commands`
- Bot Permissions: 上記の権限

## 使用方法

### Bot起動

```bash
python bot.py
```

### 基本コマンド

- `!ping` - Botが正常に動作しているか確認
- `!info` - Botの詳細情報を表示
- `!roles` - サーバーのロール一覧を表示

## 構成

```
discord_bot/
├── bot.py              # メインBotファイル
├── requirements.txt    # Python依存関係
├── .env.example       # 環境変数テンプレート
└── README.md          # このファイル
```

## 今後の拡張予定

- ロール招待リンク管理コマンド
- データベース連携
- 管理者専用コマンド
- ログ機能の強化