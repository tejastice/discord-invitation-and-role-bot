import os
import asyncio
import threading
import discord
import requests
import time
import secrets
from collections import defaultdict, deque
from flask import Flask, request, redirect, session
from urllib.parse import quote
from html import escape
from dotenv import load_dotenv

load_dotenv()

# 同じディレクトリのsharedモジュールをインポート
from shared.models import get_role_id_by_link_id, get_invite_link_full_info, increment_invite_link_usage
from shared.database import init_database

# 環境変数から設定を読み込み
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))

# 設定
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:5000/callback')
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
OFFICIAL_WEBSITE_URL = os.getenv('OFFICIAL_WEBSITE_URL', 'https://discord-invitation-and-role.kei31.com')
DISCORD_SUPPORT_SERVER_URL = os.getenv('DISCORD_SUPPORT_SERVER_URL', 'https://discord.gg/7b5g3RbjYv')
DEFAULT_TIMEOUT = float(os.getenv("REQ_TIMEOUT", 5))

# 簡易レート制限（メモリベース）
ACCESS_LOG = defaultdict(deque)
RATE_WINDOW = 60  # 60秒
MAX_REQUESTS = 20  # 最大20リクエスト

# Discord Bot
bot = discord.Client(intents=discord.Intents.default())
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Bot用グローバル変数

def discord_api(method, url, **kwargs):
    """外部API呼び出しの共通ヘルパー（タイムアウトとエラーハンドリング）"""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    try:
        r = requests.request(method, url, **kwargs)
        if r.ok:
            return r
        else:
            # HTTPエラーの詳細をログに記録
            try:
                error_details = r.json()
                app.logger.error(f"Discord API HTTP {r.status_code} error: {error_details} url={url}")
            except:
                app.logger.error(f"Discord API HTTP {r.status_code} error: {r.text} url={url}")
            return None
    except requests.RequestException as e:
        app.logger.error(f"Discord API connection error: {e} url={url}")
        return None

@app.before_request
def rate_limit():
    """簡易レート制限（メモリベース）"""
    ip = request.remote_addr or 'unknown'
    now = time.time()
    q = ACCESS_LOG[ip]
    
    # 古いアクセスをクリア
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    
    # レート制限チェック
    if len(q) >= MAX_REQUESTS:
        app.logger.warning(f"Rate limit exceeded ip={ip} path={request.path}")
        return "Too many requests", 429
    
    # 現在のアクセスを記録
    q.append(now)

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')

@app.route('/')
def home():
    """ルートアクセス時は公式ページにリダイレクト"""
    try:
        return redirect(OFFICIAL_WEBSITE_URL)
    except:
        # リダイレクトが失敗した場合のフォールバックページ
        return f'''
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Discord Invitation and Role Bot</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 40px 20px;
                    background: linear-gradient(135deg, #E91E63 0%, #FF9800 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                }}
                .container {{
                    text-align: center;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                    max-width: 500px;
                }}
                h1 {{
                    font-size: 2.5rem;
                    margin-bottom: 20px;
                    font-weight: 700;
                }}
                p {{
                    font-size: 1.2rem;
                    margin-bottom: 30px;
                    line-height: 1.6;
                }}
                .btn {{
                    display: inline-block;
                    background: white;
                    color: #E91E63;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 50px;
                    font-weight: 600;
                    font-size: 1.1rem;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
                }}
                .footer {{
                    margin-top: 30px;
                    font-size: 0.9rem;
                    opacity: 0.8;
                }}
            </style>
            <script>
                // 3秒後に自動リダイレクト
                setTimeout(function() {{
                    window.location.href = '{OFFICIAL_WEBSITE_URL}';
                }}, 3000);
            </script>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Discord Bot</h1>
                <p>入った瞬間、ロールが手に入る。</p>
                <p>詳細については公式ページをご覧ください。</p>
                <a href="{OFFICIAL_WEBSITE_URL}" class="btn">公式ページを見る</a>
                <div class="footer">
                    <p>3秒後に自動的にリダイレクトします...</p>
                </div>
            </div>
        </body>
        </html>
        '''

#######################
# Discordにjoinしてロールを付与するためのページを表示する
# - link_idを指定してDBから、サーバーID、ロールID、使用回数、現在の使用回数、有効期限（UNIX時間）を取得
# - link_idの有効期限をチェック
# - そのサーバーにbotが参加しているかチェック
# - ロールIDが存在するかチェック
# - 使用回数が上限に達していないかチェック
# - 有効期限が切れていないかチェック
# - 何か一つでも引っかかった場合は、単に無効なリンクであることをしめす。エラーの原因は表示しない
# - すべて問題なければ、サーバーのアイコンを取得して、簡単な参加ページを表示する
# - 参加ページには、サーバーのアイコン、サーバー名、ロール名、参加ボタンを表示
#######################

@app.route('/join/<link_id>')
def join_with_link(link_id):
    """特定のロール招待リンクからの参加ページを表示"""
    # link_idからデータベースの詳細情報を取得
    invite_info = get_invite_link_full_info(link_id)
    
    if not invite_info:
        return render_error_page("無効な招待リンクです。", 404)
    
    guild_id = invite_info['guild_id']
    role_id = invite_info['role_id']
    role_id_2 = invite_info.get('role_id_2')
    max_uses = invite_info['max_uses']
    current_uses = invite_info['current_uses']
    expires_at_unix = invite_info['expires_at_unix']
    
    # 有効期限チェック
    if expires_at_unix:
        now_unix = int(time.time())
        if now_unix > expires_at_unix:
            return render_error_page("無効な招待リンクです。", 404)
    
    # 使用回数チェック
    if max_uses and current_uses >= max_uses:
        return render_error_page("無効な招待リンクです。", 404)
    
    # Botがサーバーに参加しているかチェック
    guild = bot.get_guild(guild_id)
    if not guild:
        return render_error_page("無効な招待リンクです。", 404)
    
    # ロールが存在するかチェック
    role = guild.get_role(role_id)
    if not role:
        return render_error_page("無効な招待リンクです。", 404)
    
    # 2つ目のロール（任意）。削除されている場合は1つ目のロールだけで続行する
    roles = [role]
    if role_id_2:
        role_2 = guild.get_role(role_id_2)
        if role_2:
            roles.append(role_2)
    
    # セッションにlink_idを保存
    session['link_id'] = link_id
    
    # 参加ページを表示
    return render_join_page(guild, roles)



#######################
# callbackエンドポイント
# - OAuth認証のコールバックを処理
# - stateパラメータを検証してCSRF対策
# - リンクIDをセッションから取得
# - 認証コードを取得
# - アクセストークンを取得
# - ユーザー情報を取得
# - link_idからrole_idとその他の情報を取得
# - 使用回数が上限に達していないかチェック
# - 有効期限が切れていないかチェック
# - 何か一つでも引っかかった場合はエラーとする
# - ユーザーをサーバーに参加させる
# - データベースのcurrent_usesに+1する
# - 参加に成功した場合は、ロールを付与して成功ページを表示
# - 参加に失敗した場合は、エラーページを表示
# - 参加に成功した場合は、ユーザー名とロール名を表示
# - 参加に失敗した場合は、エラーメッセージを表示
#######################

@app.route('/bot-install')
def bot_install_callback():
    """Bot招待完了時のcallback"""
    # エラーチェック（キャンセルされた場合）
    error = request.args.get('error')
    if error:
        app.logger.warning(f"Bot installation failed/cancelled: {error}")
        return render_bot_install_error_page(error)
    
    guild_id = request.args.get('guild_id')
    permissions = request.args.get('permissions')
    
    if not guild_id:
        app.logger.error("Bot installation callback missing guild_id")
        return render_bot_install_error_page("missing_guild_id")
    
    app.logger.info(f"Bot installed to guild {guild_id} with permissions {permissions}")
    
    return render_bot_install_success_page(guild_id, permissions)

@app.route('/callback')
def callback():
    # OAuth CSRF対策: stateパラメータ検証
    state = request.args.get('state')
    expected_state = session.pop('oauth_state', None)
    if not state or state != expected_state:
        app.logger.warning(f"OAuth state mismatch from {request.remote_addr}")
        return render_error_page("無効な招待リンクです。", 400)
    
    # link_idを使い捨てにして取得
    link_id = session.pop('link_id', None)
    if not link_id:
        app.logger.warning(f"Invalid/expired link accessed from {request.remote_addr}")
        return render_error_page("無効な招待リンクです。", 400)
    
    code = request.args.get('code')
    if not code:
        app.logger.warning(f"Authorization failed - no code from {request.remote_addr}")
        return render_error_page("無効な招待リンクです。", 400)
    
    # Get token
    token_resp = discord_api('POST', 'https://discord.com/api/oauth2/token', data={
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    })
    
    if not token_resp:
        app.logger.error(f"Token exchange failed for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
    
    token = token_resp.json()['access_token']
    
    # Get user
    user_resp = discord_api('GET', 'https://discord.com/api/v10/users/@me', 
                           headers={'Authorization': f'Bearer {token}'})
    
    if not user_resp:
        app.logger.error(f"Failed to get user info for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
    
    user_data = user_resp.json()
    user_id = int(user_data['id'])
    username = user_data.get('username', 'Unknown')
    

    # link_idからrole_idとその他の情報を取得
    invite_info = get_invite_link_full_info(link_id)
    if not invite_info:
        app.logger.warning(f"Invalid role link_id={link_id} from {request.remote_addr}")
        return render_error_page("無効な招待リンクです。", 400)
    
    guild_id = invite_info['guild_id']
    role_id = invite_info['role_id']
    role_id_2 = invite_info.get('role_id_2')
    max_uses = invite_info['max_uses']
    current_uses = invite_info['current_uses']
    expires_at_unix = invite_info['expires_at_unix']
    
    # 使用回数が上限に達していないかチェック
    if max_uses and current_uses >= max_uses:
        app.logger.warning(f"Max uses exceeded for link_id={link_id} from {request.remote_addr}")
        return render_error_page("無効な招待リンクです。", 400)
    
    # 有効期限が切れていないかチェック
    if expires_at_unix:
        now_unix = int(time.time())
        if now_unix > expires_at_unix:
            app.logger.warning(f"Link expired for link_id={link_id} from {request.remote_addr}")
            return render_error_page("無効な招待リンクです。", 400)
    
    # 付与するロールID（1つ目は必須、2つ目は任意）
    # 2つ目のロールが削除されている場合は、1つ目のロールだけを付与する
    guild = bot.get_guild(guild_id)
    role_ids = [role_id]
    if role_id_2 and (not guild or guild.get_role(role_id_2)):
        role_ids.append(role_id_2)
    
    bot_headers = {'Authorization': f'Bot {DISCORD_TOKEN}'}
    
    def add_role(target_role_id) -> bool:
        """ユーザーにロールを付与する。成功した場合True"""
        resp = discord_api('PUT', f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{target_role_id}',
            headers=bot_headers
        )
        return bool(resp) and resp.status_code == 204
    
    def role_display(target_role_id) -> tuple:
        """表示用の (ロール名, 色) を取得する"""
        role = guild.get_role(target_role_id) if guild else None
        if role:
            return role.name, role.color.value
        return "指定されたロール", 0
    
    # ユーザーをサーバーに参加させる
    join_resp = discord_api('PUT', f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}',
        headers=bot_headers,
        json={'access_token': token, 'roles': [str(rid) for rid in role_ids]}
    )
    
    if not join_resp:
        app.logger.error(f"Guild join API failed for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
        
    if join_resp.status_code in [201, 204]:
        # Try adding roles separately if needed
        for rid in role_ids:
            add_role(rid)
        
        # データベースのcurrent_usesに+1する
        increment_invite_link_usage(link_id)
        
        return render_success_page(username, [role_display(rid) for rid in role_ids], is_returning=False, guild_id=guild_id)
        
    elif join_resp.status_code == 200:
        # User already in server, just add roles
        if add_role(role_id):
            granted_role_ids = [role_id]
            
            # 2つ目のロールは付与できた場合だけ表示する
            if len(role_ids) > 1:
                if add_role(role_ids[1]):
                    granted_role_ids.append(role_ids[1])
                else:
                    app.logger.error(f"Second role assignment failed link_id={link_id} role_id={role_ids[1]}")
            
            # データベースのcurrent_usesに+1する
            increment_invite_link_usage(link_id)
            
            return render_success_page(username, [role_display(rid) for rid in granted_role_ids], is_returning=True, guild_id=guild_id)
        
        app.logger.error(f"Role assignment failed for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
    
    app.logger.error(f"Unexpected join response status for {request.remote_addr}: {join_resp.status_code}")
    return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)

#######################
# 参加フロー用ページ（参加ページ・完了ページ・無効リンクページ）
# - 3ページ共通のCSSとHTMLの枠を使う
# - サーバー名・ロール名・ユーザー名などは必ず escape() してから埋め込む
#######################

PAGE_CSS = '''
:root {
    --pink: #e91e63;
    --orange: #ff6b35;
    --ink: #1f1a1c;
    --ink-soft: #6b6266;
    --ink-faint: #978e92;
    --line: #ece6e8;
    --surface: #ffffff;
    --surface-soft: #f8f5f6;
    --page: #f6f2f3;
    --success: #1f9d61;
    --success-soft: #e6f6ee;
    --neutral-soft: #f1edee;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Yu Gothic UI', 'Noto Sans JP', Meiryo, sans-serif;
    line-height: 1.7;
    color: var(--ink);
    background:
        radial-gradient(900px 480px at 50% -120px, #ffe1ea 0%, rgba(255, 225, 234, 0) 70%),
        var(--page);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
    -webkit-font-smoothing: antialiased;
}

.card {
    position: relative;
    overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 44px 32px 24px;
    width: 100%;
    max-width: 420px;
    text-align: center;
    box-shadow: 0 1px 2px rgba(31, 26, 28, 0.04), 0 16px 40px rgba(31, 26, 28, 0.08);
}

.card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--pink), var(--orange));
}

.eyebrow {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--ink-faint);
    margin-bottom: 20px;
}

.avatar {
    width: 88px;
    height: 88px;
    border-radius: 50%;
    margin: 0 auto 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    object-fit: cover;
    box-shadow: 0 0 0 4px var(--surface), 0 0 0 5px var(--line);
}

.avatar-fallback {
    background: linear-gradient(135deg, var(--pink), var(--orange));
    color: #ffffff;
    font-size: 36px;
    font-weight: 700;
}

.status-icon {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    margin: 0 auto 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.status-icon svg {
    width: 30px;
    height: 30px;
}

.status-success {
    background: var(--success-soft);
    color: var(--success);
}

.status-neutral {
    background: var(--neutral-soft);
    color: var(--ink-soft);
}

.title {
    font-size: 24px;
    font-weight: 700;
    line-height: 1.4;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
    text-wrap: balance;
}

.lead {
    margin-top: 8px;
    font-size: 15px;
    color: var(--ink-soft);
    overflow-wrap: anywhere;
    text-wrap: pretty;
}

.roles {
    margin-top: 28px;
    padding: 16px;
    background: var(--surface-soft);
    border-radius: 16px;
}

.roles-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-soft);
    margin-bottom: 10px;
}

.role-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
}

.role-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 100%;
    padding: 6px 14px 6px 10px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 999px;
    font-size: 14px;
    font-weight: 600;
    line-height: 1.5;
}

.role-dot {
    flex-shrink: 0;
    width: 10px;
    height: 10px;
    border-radius: 50%;
}

.role-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.button {
    margin-top: 24px;
    width: 100%;
    min-height: 52px;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    border-radius: 14px;
    background: linear-gradient(120deg, var(--pink) 0%, var(--orange) 100%);
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    line-height: 1.4;
    text-decoration: none;
    box-shadow: 0 6px 16px rgba(233, 30, 99, 0.26);
    transition: transform 0.15s ease-out, box-shadow 0.15s ease-out, filter 0.15s ease-out;
}

.button svg {
    flex-shrink: 0;
    width: 22px;
    height: 22px;
}

.button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 22px rgba(233, 30, 99, 0.3);
    filter: saturate(1.08);
}

.button:active {
    transform: translateY(0);
    box-shadow: 0 4px 10px rgba(233, 30, 99, 0.24);
}

.button:focus-visible {
    outline: 3px solid rgba(233, 30, 99, 0.4);
    outline-offset: 3px;
}

.note {
    margin-top: 16px;
    font-size: 12.5px;
    line-height: 1.7;
    color: var(--ink-faint);
    text-wrap: pretty;
}

.footer {
    margin-top: 28px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
}

.footer a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 500;
    color: var(--ink-faint);
    text-decoration: none;
}

.footer a:hover {
    color: var(--ink-soft);
}

.footer img {
    width: 20px;
    height: 20px;
    border-radius: 50%;
}

@media (max-width: 480px) {
    .card {
        padding: 36px 22px 20px;
        border-radius: 20px;
    }

    .title {
        font-size: 22px;
    }
}

@media (prefers-reduced-motion: reduce) {
    .button {
        transition: none;
    }
}
'''

DISCORD_LOGO_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"/></svg>'

CHECK_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'

BROKEN_LINK_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 17H7a5 5 0 010-10h2"/><path d="M15 7h2a5 5 0 014 8"/><path d="M8 12h4"/><path d="M3 3l18 18"/></svg>'

# ロールに色が設定されていない場合のドットの色（Discordの既定ロール色）
DEFAULT_ROLE_COLOR = '#99aab5'


def render_page(title: str, description: str, body: str) -> str:
    """参加フロー用ページ共通のHTMLの枠"""
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} - Discord Invitation &amp; Role Bot</title>
    <meta name="description" content="{escape(description)}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>{PAGE_CSS}</style>
</head>
<body>
    <main class="card">
{body}
        <footer class="footer">
            <a href="{escape(OFFICIAL_WEBSITE_URL)}" target="_blank" rel="noopener">
                <img src="/static/bot-icon.jpeg" alt="">
                <span>Discord Invitation &amp; Role Bot</span>
            </a>
        </footer>
    </main>
</body>
</html>
'''


def render_role_chips(roles: list) -> str:
    """ロールの一覧をチップ表示のHTMLにする。roles は (ロール名, 色の整数値) のリスト"""
    chips = []
    for name, color in roles:
        dot_color = f'#{color:06x}' if color else DEFAULT_ROLE_COLOR
        chips.append(
            f'<span class="role-chip">'
            f'<span class="role-dot" style="background: {dot_color}"></span>'
            f'<span class="role-name">{escape(name)}</span>'
            f'</span>'
        )
    return ''.join(chips)


def render_error_page(message: str, status: int = 500):
    """エラーページをレンダリング"""
    if status >= 500:
        title = "エラーが発生しました"
        lead = escape(message)
    else:
        # 無効なリンクの場合、具体的な原因は表示しない
        title = "この招待リンクは無効です"
        lead = "有効期限が切れているか、使用回数の上限に達している可能性があります。招待してくれた方に、新しいリンクをご確認ください。"

    body = f'''
        <div class="status-icon status-neutral">{BROKEN_LINK_ICON_SVG}</div>
        <h1 class="title">{title}</h1>
        <p class="lead">{lead}</p>
    '''
    return render_page(title, title, body), status


def render_join_page(guild, roles: list):
    """参加ページをレンダリング。roles は付与するロール（discord.Role）のリスト"""
    # サーバーアイコンのURL取得
    guild_icon_url = guild.icon.url if guild.icon else None

    # OAuth認証URL生成
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state

    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={quote(REDIRECT_URI)}&response_type=code&scope=identify%20guilds.join&state={state}"

    if guild_icon_url:
        avatar_html = f'<img src="{escape(guild_icon_url)}" alt="" class="avatar">'
    else:
        initial = guild.name[0] if guild.name else "?"
        avatar_html = f'<div class="avatar avatar-fallback">{escape(initial)}</div>'

    role_chips = render_role_chips([(role.name, role.color.value) for role in roles])

    body = f'''
        <p class="eyebrow">サーバーへの招待</p>
        {avatar_html}
        <h1 class="title">{escape(guild.name)}</h1>
        <div class="roles">
            <p class="roles-label">参加すると付与されるロール</p>
            <div class="role-list">{role_chips}</div>
        </div>
        <a href="{escape(auth_url)}" class="button">
            {DISCORD_LOGO_SVG}
            <span>Discordで認証して参加する</span>
        </a>
        <p class="note">Discordアカウントで認証すると、サーバーへの参加とロールの付与が自動で行われます。</p>
    '''
    return render_page(
        f"{guild.name} に参加",
        "招待リンクからDiscordサーバーに参加してロールを自動取得",
        body
    )


def render_success_page(username: str, roles: list, is_returning: bool = False, guild_id: int = None):
    """成功ページをレンダリング。roles は (ロール名, 色の整数値) のリスト"""
    if is_returning:
        title = "ロールを付与しました"
        lead = f"{escape(username)} さんは、すでにサーバーに参加しています。"
    else:
        title = "参加が完了しました"
        lead = f"{escape(username)} さん、ようこそ。"

    button_html = ""
    if guild_id:
        button_html = f'''
        <a href="https://discord.com/channels/{int(guild_id)}" class="button">
            {DISCORD_LOGO_SVG}
            <span>Discordを開く</span>
        </a>'''

    body = f'''
        <div class="status-icon status-success">{CHECK_ICON_SVG}</div>
        <h1 class="title">{title}</h1>
        <p class="lead">{lead}</p>
        <div class="roles">
            <p class="roles-label">付与されたロール</p>
            <div class="role-list">{render_role_chips(roles)}</div>
        </div>{button_html}
        <p class="note">このページは閉じて構いません。</p>
    '''
    return render_page(title, "Discordサーバーへの参加とロール付与が完了しました", body)


def render_bot_install_error_page(error_type):
    """Bot招待エラーページをレンダリング"""
    
    # エラータイプに応じてメッセージを設定
    if error_type == "access_denied":
        error_title = "Bot招待がキャンセルされました"
        error_message = "Botの招待がキャンセルされました。もう一度招待リンクからお試しください。"
        error_icon = "❌"
    elif error_type == "missing_guild_id":
        error_title = "招待情報が不完全です"
        error_message = "Botの招待処理で必要な情報が不足しています。もう一度招待リンクからお試しください。"
        error_icon = "⚠️"
    else:
        error_title = "招待処理でエラーが発生しました"
        error_message = f"予期しないエラーが発生しました（{error_type}）。時間をおいて再度お試しください。"
        error_icon = "❌"
    
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bot招待エラー - Discord Invitation & Role Bot</title>
        <style>
            :root {{
                --primary-pink: #F97316;
                --primary-orange: #FB923C;
                --secondary-pink: #FED7D7;
                --gray-50: #F9FAFB;
                --gray-100: #F3F4F6;
                --gray-200: #E5E7EB;
                --gray-700: #374151;
                --gray-900: #111827;
                --white: #FFFFFF;
                --error: #EF4444;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --radius-lg: 0.5rem;
                --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
                --font-weight-semibold: 600;
                --transition-fast: 0.15s ease-in-out;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: linear-gradient(135deg, var(--gray-50) 0%, var(--secondary-pink) 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }}
            
            .container {{
                background: var(--white);
                border-radius: var(--radius-lg);
                box-shadow: var(--shadow-lg);
                padding: var(--space-8);
                max-width: 600px;
                width: 100%;
                text-align: center;
            }}
            
            .error-icon {{
                font-size: 4rem;
                margin-bottom: var(--space-4);
            }}
            
            .error-title {{
                font-size: 1.5rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-4);
            }}
            
            .error-message {{
                color: var(--gray-700);
                margin-bottom: var(--space-6);
                line-height: 1.6;
            }}
            
            .action-buttons {{
                display: flex;
                gap: var(--space-3);
                justify-content: center;
                flex-wrap: wrap;
            }}
            
            .btn {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-3) var(--space-6);
                border-radius: var(--radius-lg);
                text-decoration: none;
                font-weight: var(--font-weight-semibold);
                transition: all var(--transition-fast);
                border: none;
                cursor: pointer;
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                color: var(--white);
            }}
            
            .btn-primary:hover {{
                transform: translateY(-1px);
                box-shadow: var(--shadow-lg);
            }}
            
            .btn-secondary {{
                background: var(--gray-100);
                color: var(--gray-700);
            }}
            
            .btn-secondary:hover {{
                background: var(--gray-200);
            }}
            
            @media (max-width: 768px) {{
                .container {{
                    padding: var(--space-6);
                    margin: var(--space-4);
                }}
                
                .action-buttons {{
                    flex-direction: column;
                }}
                
                .btn {{
                    width: 100%;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-icon">{error_icon}</div>
            <h1 class="error-title">{error_title}</h1>
            <p class="error-message">{error_message}</p>
            
            <div class="action-buttons">
                <a href="{os.getenv('OFFICIAL_WEBSITE_URL', 'https://discord-invitation-and-role-bot.kei31.com')}" class="btn btn-primary">
                    公式サイトに戻る
                </a>
                <a href="{os.getenv('DISCORD_SUPPORT_SERVER_URL', '#')}" class="btn btn-secondary">
                    サポートに問い合わせ
                </a>
            </div>
        </div>
    </body>
    </html>
    '''

def render_bot_install_success_page(guild_id, permissions):
    """Bot招待成功ページをレンダリング"""
    # Discord APIを直接呼び出してサーバー情報を取得
    try:
        import aiohttp
        import asyncio
        
        bot_token = os.getenv('DISCORD_TOKEN')
        app.logger.info(f"Trying to get guild: {guild_id}")
        
        async def fetch_guild_info():
            headers = {'Authorization': f'Bot {bot_token}'}
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://discord.com/api/v10/guilds/{guild_id}', headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        app.logger.error(f"Discord API error: {resp.status}")
                        return None
        
        # 非同期関数を実行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        guild_data = loop.run_until_complete(fetch_guild_info())
        loop.close()
        
        if guild_data:
            guild_name = guild_data.get('name', 'サーバー')
            icon_hash = guild_data.get('icon')
            guild_icon_url = f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png" if icon_hash else None
            app.logger.info(f"Guild info - Name: {guild_name}, Icon: {guild_icon_url}")
        else:
            guild_name = "サーバー"
            guild_icon_url = None
            app.logger.warning(f"Could not get guild info for guild_id: {guild_id}")
            
    except Exception as e:
        app.logger.error(f"Error getting guild info: {e}")
        guild_name = "サーバー"
        guild_icon_url = None
    
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bot導入完了 - Discord Invitation & Role Bot</title>
        <meta name="description" content="Discord Invitation & Role Bot の導入が正常に完了しました">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary-pink: #e91e63;
                --primary-pink-light: #f48fb1;
                --primary-pink-dark: #ad1457;
                --primary-orange: #ff6b35;
                --primary-orange-light: #ff9068;
                --secondary-purple: #6366f1;
                --warm-50: #fefbf3;
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                --white: #ffffff;
                --success: #22c55e;
                --success-light: #dcfce7;
                --success-dark: #166534;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-12: 3rem;
                --space-16: 4rem;
                --radius-md: 0.375rem;
                --radius-lg: 0.5rem;
                --radius-xl: 0.75rem;
                --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
                --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                --transition-fast: 0.15s ease-out;
                --font-weight-medium: 500;
                --font-weight-semibold: 600;
            }}
            
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: var(--gray-900);
                background: linear-gradient(135deg, var(--primary-pink-light) 0%, var(--primary-orange-light) 50%, var(--warm-50) 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
            }}
            
            .container {{
                background: var(--white);
                border-radius: var(--radius-xl);
                padding: var(--space-12);
                box-shadow: var(--shadow-xl);
                max-width: 700px;
                width: 100%;
                text-align: center;
                border: 1px solid var(--gray-200);
            }}
            
            .success-header {{
                margin-bottom: var(--space-8);
            }}
            
            .installation-visual {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-6);
                margin-bottom: var(--space-8);
                padding: var(--space-6);
                background: linear-gradient(135deg, var(--warm-50) 0%, var(--success-light) 100%);
                border-radius: var(--radius-xl);
                border: 2px solid var(--success);
                box-shadow: var(--shadow-lg);
            }}
            
            .installation-bot-icon {{
                width: 64px;
                height: 64px;
                border-radius: 50%;
                box-shadow: var(--shadow-lg);
                border: 3px solid var(--primary-pink);
            }}
            
            .connection-arrow {{
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
            }}
            
            .arrow-text {{
                font-size: 0.75rem;
                font-weight: var(--font-weight-semibold);
                color: var(--success-dark);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            
            .arrow {{
                font-size: 1.5rem;
                color: var(--primary-pink);
                font-weight: bold;
                animation: pulse 2s infinite;
            }}
            
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: 0.7; transform: scale(1.1); }}
            }}
            
            .server-placeholder {{
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                text-align: center;
            }}
            
            .server-icon-placeholder {{
                width: 64px;
                height: 64px;
                background: linear-gradient(135deg, var(--secondary-purple) 0%, var(--primary-orange) 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2rem;
                box-shadow: var(--shadow-lg);
                border: 3px solid var(--primary-orange);
            }}
            
            .installation-server-icon {{
                width: 64px;
                height: 64px;
                border-radius: 50%;
                box-shadow: var(--shadow-lg);
                border: 3px solid var(--primary-orange);
            }}
            
            .server-text {{
                font-size: 0.875rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-700);
                text-align: center;
            }}
            
            .bot-name {{
                font-size: 0.875rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-700);
                text-align: center;
            }}
            
            .success-icon {{
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, var(--success) 0%, var(--primary-pink) 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto var(--space-6) auto;
                box-shadow: var(--shadow-lg);
                font-size: 2.5rem;
            }}
            
            .page-title {{
                font-size: 2rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-4);
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .success-info {{
                background: linear-gradient(135deg, var(--success-light) 0%, var(--warm-50) 100%);
                color: var(--success-dark);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-8);
                border: 2px solid var(--success);
                font-weight: var(--font-weight-medium);
                box-shadow: var(--shadow-md);
            }}
            
            .setup-steps {{
                background: var(--gray-50);
                border-radius: var(--radius-lg);
                padding: var(--space-8);
                margin-bottom: var(--space-8);
                text-align: left;
                border: 1px solid var(--gray-200);
                box-shadow: var(--shadow-md);
            }}
            
            .steps-title {{
                font-size: 1.5rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-6);
                text-align: center;
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .step {{
                background: var(--white);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                margin-bottom: var(--space-4);
                border: 1px solid var(--gray-200);
                box-shadow: var(--shadow-md);
                transition: transform var(--transition-fast);
            }}
            
            .step:hover {{
                transform: translateY(-2px);
                box-shadow: var(--shadow-lg);
            }}
            
            .step:last-child {{
                margin-bottom: 0;
            }}
            
            .step-header {{
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-3);
            }}
            
            .step-number {{
                width: 32px;
                height: 32px;
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                color: var(--white);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: var(--font-weight-semibold);
                font-size: 0.875rem;
            }}
            
            .step-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
            }}
            
            .step-description {{
                color: var(--gray-700);
                margin-bottom: var(--space-4);
                line-height: 1.6;
            }}
            
            .command {{
                background: var(--gray-900);
                color: var(--white);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-md);
                font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
                font-size: 0.875rem;
                margin: var(--space-2) 0;
                display: inline-block;
                box-shadow: var(--shadow-md);
            }}
            
            .permissions-list {{
                background: var(--warm-50);
                border-radius: var(--radius-md);
                padding: var(--space-4);
                margin: var(--space-3) 0;
                border: 1px solid var(--primary-orange);
            }}
            
            .permissions-list ul {{
                list-style: none;
                margin: 0;
                padding: 0;
            }}
            
            .permissions-list li {{
                color: var(--gray-700);
                margin-bottom: var(--space-2);
                padding-left: var(--space-6);
                position: relative;
            }}
            
            .permissions-list li:before {{
                content: "✓";
                position: absolute;
                left: 0;
                color: var(--success);
                font-weight: var(--font-weight-semibold);
            }}
            
            .permissions-list li:last-child {{
                margin-bottom: 0;
            }}
            
            .additional-info {{
                background: var(--warm-50);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                margin-bottom: var(--space-8);
                border: 1px solid var(--primary-orange);
                box-shadow: var(--shadow-md);
                text-align: center;
            }}
            
            .info-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--primary-orange);
                margin-bottom: var(--space-3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }}
            
            .additional-info p {{
                color: var(--gray-700);
                margin: 0;
                line-height: 1.6;
            }}
            
            .support-section {{
                background: linear-gradient(135deg, var(--warm-50) 0%, var(--primary-pink-light) 20%, var(--primary-orange-light) 100%);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                border: 2px solid var(--primary-pink);
                box-shadow: var(--shadow-md);
                color: var(--gray-900);
                font-weight: var(--font-weight-medium);
                line-height: 1.7;
                margin-bottom: var(--space-8);
            }}
            
            .support-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--primary-pink-dark);
                margin-bottom: var(--space-3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }}
            
            .support-link {{
                color: var(--primary-pink);
                text-decoration: none;
                font-weight: var(--font-weight-semibold);
                transition: color var(--transition-fast);
            }}
            
            .support-link:hover {{
                color: var(--primary-pink-dark);
                text-decoration: underline;
            }}
            
            .bot-branding {{
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-4);
                background: linear-gradient(135deg, var(--gray-50) 0%, var(--warm-50) 100%);
                border-radius: var(--radius-lg);
                border: 1px solid var(--gray-200);
            }}
            
            .bot-icon {{
                width: 32px;
                height: 32px;
                border-radius: 50%;
                box-shadow: var(--shadow-md);
            }}
            
            .bot-text {{
                font-size: 0.875rem;
                color: var(--gray-600);
                font-weight: var(--font-weight-medium);
            }}
            
            @media (max-width: 640px) {{
                .container {{
                    padding: var(--space-8);
                    margin: var(--space-4);
                }}
                
                .page-title {{
                    font-size: 1.75rem;
                }}
                
                .step {{
                    padding: var(--space-4);
                }}
                
                .step-header {{
                    flex-direction: column;
                    text-align: center;
                    gap: var(--space-2);
                }}
                
                .installation-visual {{
                    flex-direction: column;
                    gap: var(--space-4);
                    margin: 0 var(--space-4) var(--space-6);
                }}
                
                .connection-arrow {{
                    transform: rotate(90deg);
                }}
                
                .arrow {{
                    font-size: 1.25rem;
                }}
                
                .bot-branding {{
                    flex-direction: column;
                    text-align: center;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Success Header -->
            <div class="success-header">
                <div class="installation-visual">
                    <div class="bot-branding">
                        <img src="/static/bot-icon.jpeg" alt="Discord Invitation & Role Bot" class="installation-bot-icon">
                        <span class="bot-name">Invitation & Role Bot</span>
                    </div>
                    <div class="connection-arrow">
                        <span class="arrow-text">導入完了</span>
                        <div class="arrow">→</div>
                    </div>
                    <div class="server-placeholder">
                        {f'<img src="{guild_icon_url}" alt="Server Icon" class="installation-server-icon">' if guild_icon_url else '<div class="server-icon-placeholder">🖥️</div>'}
                        <span class="server-text">{guild_name}</span>
                    </div>
                </div>
                <h1 class="page-title">Bot導入完了！</h1>
            </div>
            
            <!-- Success Info -->
            <div class="success-info">
                ✅ Discord Invitation & Role Bot がサーバーに正常に追加されました
            </div>
            
            <!-- Setup Steps -->
            <div class="setup-steps">
                <h2 class="steps-title">🚀 次のステップ</h2>
                
                <div class="step">
                    <div class="step-header">
                        <div class="step-number">1</div>
                        <h3 class="step-title">スラッシュコマンドを使用</h3>
                    </div>
                    <p class="step-description">以下のコマンドでロール招待リンクを作成できます：</p>
                    <div class="command">/generate_invite_link</div>
                </div>
                
                <div class="step">
                    <div class="step-header">
                        <div class="step-number">2</div>
                        <h3 class="step-title">招待リンクの管理</h3>
                    </div>
                    <p class="step-description">作成したリンクの確認・削除：</p>
                    <div class="command">/list_server_invite_links</div>
                    <div class="command">/list_my_invite_links</div>
                </div>
            </div>
            
            <!-- Additional Info -->
            <div class="additional-info">
                <div class="info-title">
                    <span>📖</span>
                    使い方の詳細
                </div>
                <p>より詳しい使い方やFAQについては、<a href="{OFFICIAL_WEBSITE_URL}" class="support-link">公式サイト</a>をご確認ください。</p>
            </div>
            
            <!-- Support Section -->
            <div class="support-section">
                <div class="support-title">
                    <span>💬</span>
                    サポート
                </div>
                問題が発生した場合は、<a href="{DISCORD_SUPPORT_SERVER_URL}" target="_blank" class="support-link">Discordサポートサーバー</a>でお気軽にご相談ください。
            </div>
            
            <!-- Bot Branding -->
            <div class="bot-branding">
                <img src="/static/bot-icon.jpeg" alt="Discord Invitation & Role Bot" class="bot-icon">
                <span class="bot-text">Discord Invitation & Role Bot</span>
            </div>
        </div>
    </body>
    </html>
    '''

def start_bot():
    asyncio.run(bot.start(DISCORD_TOKEN))

if __name__ == "__main__":
    # テーブルと列の追加（role_id_2など）を反映する。Bot側と同じ処理で、何度実行しても安全
    try:
        init_database()
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")
    
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))