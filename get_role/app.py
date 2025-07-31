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
from dotenv import load_dotenv

load_dotenv()

# 同じディレクトリのsharedモジュールをインポート
from shared.models import get_role_id_by_link_id, get_invite_link_full_info, increment_invite_link_usage

# 環境変数から設定を読み込み
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))

# 設定
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:5000/callback')
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
OFFICIAL_WEBSITE_URL = os.getenv('OFFICIAL_WEBSITE_URL', 'https://discord-invitation-and-role.kei31.com')
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
        return r if r.ok else None
    except requests.RequestException as e:
        app.logger.error(f"Discord API error: {e} url={url}")
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
    
    # セッションにlink_idを保存
    session['link_id'] = link_id
    
    # 参加ページを表示
    return render_join_page(guild, role)



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
    guild_id = request.args.get('guild_id')
    permissions = request.args.get('permissions')
    
    app.logger.info(f"Bot installed to guild {guild_id} with permissions {permissions}")
    
    return render_bot_install_success_page(guild_id, permissions)

@app.route('/callback')
def callback():
    # OAuth CSRF対策: stateパラメータ検証
    state = request.args.get('state')
    expected_state = session.pop('oauth_state', None)
    if not state or state != expected_state:
        app.logger.warning(f"OAuth state mismatch from {request.remote_addr}")
        return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
    # link_idを使い捨てにして取得
    link_id = session.pop('link_id', None)
    if not link_id:
        app.logger.warning(f"Invalid/expired link accessed from {request.remote_addr}")
        return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
    code = request.args.get('code')
    if not code:
        app.logger.warning(f"Authorization failed - no code from {request.remote_addr}")
        return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
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
        return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
    guild_id = invite_info['guild_id']
    role_id = invite_info['role_id']
    max_uses = invite_info['max_uses']
    current_uses = invite_info['current_uses']
    expires_at_unix = invite_info['expires_at_unix']
    
    # 使用回数が上限に達していないかチェック
    if max_uses and current_uses >= max_uses:
        app.logger.warning(f"Max uses exceeded for link_id={link_id} from {request.remote_addr}")
        return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
    # 有効期限が切れていないかチェック
    if expires_at_unix:
        now_unix = int(time.time())
        if now_unix > expires_at_unix:
            app.logger.warning(f"Link expired for link_id={link_id} from {request.remote_addr}")
            return render_error_page("リンクが無効/期限切れです。最初からやり直してください。", 400)
    
    # ユーザーをサーバーに参加させる
    join_resp = discord_api('PUT', f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}',
        headers={'Authorization': f'Bot {DISCORD_TOKEN}'},
        json={'access_token': token, 'roles': [str(role_id)]}
    )
    
    if not join_resp:
        app.logger.error(f"Guild join API failed for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
        
    if join_resp.status_code in [201, 204]:
        # Try adding role separately if needed
        discord_api('PUT', f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}',
            headers={'Authorization': f'Bot {DISCORD_TOKEN}'}
        )
        
        # データベースのcurrent_usesに+1する
        increment_invite_link_usage(link_id)
        
        # Get role name for display
        guild = bot.get_guild(guild_id)
        role_name = "指定されたロール"
        if guild:
            role = guild.get_role(role_id)
            if role:
                role_name = role.name
        
        return render_success_page(username, role_name, is_returning=False)
        
    elif join_resp.status_code == 200:
        # User already in server, just add role
        role_resp = discord_api('PUT', f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}',
            headers={'Authorization': f'Bot {DISCORD_TOKEN}'}
        )
        
        if role_resp and role_resp.status_code == 204:
            # データベースのcurrent_usesに+1する
            increment_invite_link_usage(link_id)
            
            # Get role name for display
            guild = bot.get_guild(guild_id)
            role_name = "指定されたロール"
            if guild:
                role = guild.get_role(role_id)
                if role:
                    role_name = role.name
            
            return render_success_page(username, role_name, is_returning=True)
        
        app.logger.error(f"Role assignment failed for {request.remote_addr}")
        return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)
    
    app.logger.error(f"Unexpected join response status for {request.remote_addr}: {join_resp.status_code}")
    return render_error_page("エラーが発生しました。時間をおいて再度お試しください。", 500)

def render_error_page(message: str, status: int = 500):
    """エラーページをレンダリング"""
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: #f9fafb;
                color: #374151;
            }}
            .error-container {{
                text-align: center;
                padding: 48px 32px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
                max-width: 400px;
                border: 1px solid #e5e7eb;
            }}
            h1 {{
                color: #dc2626;
                margin-bottom: 16px;
                font-size: 24px;
            }}
            p {{
                line-height: 1.6;
                margin-bottom: 24px;
            }}
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>エラー</h1>
            <p>{message}</p>
        </div>
    </body>
    </html>
    ''', status


def render_join_page(guild, role):
    """参加ページをレンダリング"""
    # サーバーアイコンのURL取得
    guild_icon_url = guild.icon.url if guild.icon else None
    
    # OAuth認証URL生成
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={quote(REDIRECT_URI)}&response_type=code&scope=identify%20guilds.join&state={state}"
    
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Discordサーバー参加 - Discord Invitation & Role Bot</title>
        <meta name="description" content="招待リンクからDiscordサーバーに参加してロールを自動取得">
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
                --warning: #f59e0b;
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
                max-width: 500px;
                width: 100%;
                text-align: center;
                border: 1px solid var(--gray-200);
            }}
            
            .bot-branding {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                margin-bottom: var(--space-8);
                padding: var(--space-4);
                background: linear-gradient(135deg, var(--gray-50) 0%, var(--warm-50) 100%);
                border-radius: var(--radius-lg);
                border: 1px solid var(--gray-200);
            }}
            
            .bot-icon {{
                width: 48px;
                height: 48px;
                border-radius: 50%;
                box-shadow: var(--shadow-md);
            }}
            
            .bot-info {{
                text-align: left;
            }}
            
            .bot-name {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-2);
            }}
            
            .bot-subtitle {{
                font-size: 0.875rem;
                color: var(--gray-600);
            }}
            
            .server-info {{
                margin-bottom: var(--space-8);
            }}
            
            .server-icon {{
                width: 96px;
                height: 96px;
                border-radius: 50%;
                margin: 0 auto var(--space-4) auto;
                box-shadow: var(--shadow-lg);
                display: block;
            }}
            
            .server-icon-fallback {{
                width: 96px;
                height: 96px;
                background: linear-gradient(135deg, var(--secondary-purple) 0%, var(--primary-pink) 100%);
                border-radius: 50%;
                margin: 0 auto var(--space-4) auto;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--white);
                font-size: 2.5rem;
                font-weight: var(--font-weight-semibold);
                box-shadow: var(--shadow-lg);
            }}
            
            .server-name {{
                font-size: 1.875rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-3);
            }}
            
            .role-info {{
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                color: var(--white);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-8);
            }}
            
            .role-label {{
                font-size: 0.875rem;
                font-weight: var(--font-weight-medium);
                opacity: 0.9;
                margin-bottom: var(--space-2);
            }}
            
            .role-name {{
                font-size: 1.25rem;
                font-weight: var(--font-weight-semibold);
            }}
            
            .join-button {{
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                color: var(--white);
                border: none;
                border-radius: var(--radius-lg);
                padding: var(--space-4) var(--space-8);
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                cursor: pointer;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: var(--space-3);
                transition: all var(--transition-fast);
                box-shadow: var(--shadow-md);
                width: 100%;
                justify-content: center;
            }}
            
            .join-button:hover {{
                transform: translateY(-2px);
                box-shadow: var(--shadow-lg);
                background: linear-gradient(135deg, var(--primary-pink-dark) 0%, var(--primary-orange) 100%);
            }}
            
            .join-button:active {{
                transform: translateY(0);
            }}
            
            .security-notice {{
                background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
                border: 1px solid #ffc107;
                border-radius: var(--radius-md);
                padding: var(--space-4);
                margin-top: var(--space-6);
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                text-align: left;
            }}
            
            .notice-icon {{
                font-size: 1.25rem;
                flex-shrink: 0;
                margin-top: 2px;
            }}
            
            .notice-text {{
                font-size: 0.875rem;
                line-height: 1.5;
                color: #856404;
            }}
            
            @media (max-width: 640px) {{
                .container {{
                    padding: var(--space-8);
                    margin: var(--space-4);
                }}
                
                .server-name {{
                    font-size: 1.5rem;
                }}
                
                .bot-branding {{
                    flex-direction: column;
                    text-align: center;
                }}
                
                .bot-info {{
                    text-align: center;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Bot Branding -->
            <div class="bot-branding">
                <img src="/static/bot-icon.jpeg" alt="Discord Invitation & Role Bot" class="bot-icon">
                <div class="bot-info">
                    <div class="bot-name">Discord Invitation & Role Bot</div>
                    <div class="bot-subtitle">このBotで承認されたリンクです</div>
                </div>
            </div>
            
            <!-- Server Information -->
            <div class="server-info">
                {f'<img src="{guild_icon_url}" alt="Server Icon" class="server-icon">' if guild_icon_url else f'<div class="server-icon-fallback">{guild.name[0] if guild.name else "?"}</div>'}
                <div class="server-name">{guild.name}</div>
            </div>
            
            <!-- Role Information -->
            <div class="role-info">
                <div class="role-label">参加時に自動で獲得できるロール</div>
                <div class="role-name">🏷️ {role.name}</div>
            </div>
            
            <!-- Join Button -->
            <a href="{auth_url}" class="join-button">
                <span>🚀</span>
                Discordサーバーに参加する
            </a>
            
            <!-- Security Notice -->
            <div class="security-notice">
                <span class="notice-icon">🔒</span>
                <div class="notice-text">
                    安全な参加のため、Discordアカウントでの認証が必要です。参加後、指定されたロールが自動で付与されます。
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

def render_bot_install_success_page(guild_id, permissions):
    """Bot招待成功ページをレンダリング"""
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bot Installation Success</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                min-height: 100vh;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                color: #333;
            }}
            .container {{
                background: #ffffff;
                border-radius: 12px;
                padding: 48px 40px;
                box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
                text-align: center;
                max-width: 600px;
                border: 1px solid #e5e7eb;
            }}
            h1 {{
                color: #111827;
                margin-bottom: 16px;
                font-size: 28px;
                font-weight: 600;
                letter-spacing: -0.025em;
            }}
            .success-info {{
                background: #f0fdf4;
                color: #166534;
                padding: 20px;
                border-radius: 8px;
                margin: 24px 0;
                border: 1px solid #bbf7d0;
            }}
            .setup-steps {{
                background: #f9fafb;
                border-radius: 8px;
                padding: 24px;
                margin: 24px 0;
                text-align: left;
                border: 1px solid #e5e7eb;
            }}
            .step {{
                margin: 16px 0;
                padding: 12px 0;
            }}
            .step h3 {{
                color: #374151;
                margin-bottom: 8px;
                font-size: 16px;
            }}
            .step p {{
                color: #6b7280;
                margin: 0;
                line-height: 1.5;
            }}
            .command {{
                background: #f3f4f6;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #374151;
                margin: 8px 0;
            }}
            @media (max-width: 768px) {{
                .container {{
                    margin: 16px;
                    padding: 32px 24px;
                }}
                h1 {{
                    font-size: 24px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎉 Bot導入完了！</h1>
            <div class="success-info">
                Discord Role Botがサーバーに正常に追加されました
            </div>
            
            <div class="setup-steps">
                <h2 style="color: #111827; margin-bottom: 20px; font-size: 20px;">次のステップ</h2>
                
                <div class="step">
                    <h3>1. スラッシュコマンドを使用</h3>
                    <p>以下のコマンドでロール招待リンクを作成できます：</p>
                    <div class="command">/generate_invite_link</div>
                </div>
                
                <div class="step">
                    <h3>2. 招待リンクの管理</h3>
                    <p>作成したリンクの確認・削除：</p>
                    <div class="command">/list_server_invite_links</div>
                    <div class="command">/list_my_invite_links</div>
                </div>
                
                <div class="step">
                    <h3>3. 権限の確認</h3>
                    <p>Botが正常に動作するために、以下の権限が必要です：</p>
                    <ul style="margin: 8px 0; padding-left: 20px; color: #6b7280;">
                        <li>メンバーを管理</li>
                        <li>ロールを管理</li>
                        <li>スラッシュコマンドを使用</li>
                    </ul>
                </div>
                
                <div class="step">
                    <h3>4. 使い方</h3>
                    <p>詳細な使い方は<a href="/docs/" style="color: #5865F2;">ドキュメント</a>をご確認ください。</p>
                </div>
            </div>
            
            <div style="background: #f9fafb; padding: 24px; border-radius: 8px; margin: 24px 0; color: #374151; font-weight: 400; border: 1px solid #e5e7eb;">
                <strong style="color: #111827;">サポート</strong><br>
                問題が発生した場合は、<a href="https://github.com/tejastice/invite-and-role-bot/issues" target="_blank" style="color: #5865F2;">GitHub Issues</a>でお気軽にご相談ください。
            </div>
        </div>
    </body>
    </html>
    '''

def render_success_page(username, role_name, is_returning=False):
    """成功ページをレンダリング"""
    action_text = "サーバーに参加して" if not is_returning else "ロールを獲得しました"
    welcome_text = f"Welcome{' back' if is_returning else ''} {username}!"
    
    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Role Assignment Success</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                min-height: 100vh;
                background: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                color: #333;
            }}
            .container {{
                background: #ffffff;
                border-radius: 12px;
                padding: 48px 40px;
                box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
                text-align: center;
                max-width: 600px;
                border: 1px solid #e5e7eb;
            }}
            h1 {{
                color: #111827;
                margin-bottom: 16px;
                font-size: 28px;
                font-weight: 600;
                letter-spacing: -0.025em;
            }}
            .success-info {{
                background: #f0fdf4;
                color: #166534;
                padding: 20px;
                border-radius: 8px;
                margin: 24px 0;
                border: 1px solid #bbf7d0;
            }}
            .role-details {{
                background: #f9fafb;
                border-radius: 8px;
                padding: 24px;
                margin: 24px 0;
                text-align: left;
                border: 1px solid #e5e7eb;
            }}
            .detail-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin: 16px 0;
                padding: 12px 0;
                border-bottom: 1px solid #e5e7eb;
            }}
            .detail-row:last-child {{
                border-bottom: none;
            }}
            .detail-label {{
                font-weight: 500;
                color: #374151;
            }}
            .detail-value {{
                color: #111827;
                font-weight: 500;
            }}
            @media (max-width: 768px) {{
                .container {{
                    margin: 16px;
                    padding: 32px 24px;
                }}
                h1 {{
                    font-size: 24px;
                }}
                .detail-row {{
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{welcome_text}</h1>
            <div class="success-info">
                ロール付与が正常に完了しました
            </div>
            <div class="role-details">
                <div class="detail-row">
                    <span class="detail-label">ユーザー名:</span>
                    <span class="detail-value">{username}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">付与されたロール:</span>
                    <span class="detail-value">{role_name}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">ステータス:</span>
                    <span class="detail-value">{"参加完了" if not is_returning else "ロール追加完了"}</span>
                </div>
            </div>
            <div style="background: #f9fafb; padding: 24px; border-radius: 8px; margin: 24px 0; color: #374151; font-weight: 400; border: 1px solid #e5e7eb;">
                <strong style="color: #111827;">おめでとうございます！</strong><br>
                あなたは{action_text}、<strong>{role_name}</strong>ロールを獲得しました。<br>
                このページを閉じて、Discordに戻ってください。
            </div>
        </div>
    </body>
    </html>
    '''


def start_bot():
    asyncio.run(bot.start(DISCORD_TOKEN))

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))