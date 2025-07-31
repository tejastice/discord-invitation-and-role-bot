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
        <title>エラー - Discord Invitation & Role Bot</title>
        <meta name="description" content="処理中にエラーが発生しました">
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
                --error: #dc2626;
                --error-light: #fee2e2;
                --error-dark: #991b1b;
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
            
            .error-header {{
                margin-bottom: var(--space-8);
            }}
            
            .error-icon {{
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, var(--error) 0%, var(--primary-pink) 100%);
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
                background: linear-gradient(135deg, var(--error) 0%, var(--primary-pink) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .error-message {{
                background: linear-gradient(135deg, var(--error-light) 0%, var(--warm-50) 100%);
                color: var(--error-dark);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-8);
                border: 2px solid var(--error);
                font-weight: var(--font-weight-medium);
                box-shadow: var(--shadow-md);
                line-height: 1.7;
            }}
            
            .help-section {{
                background: var(--gray-50);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                margin-bottom: var(--space-8);
                border: 1px solid var(--gray-200);
                box-shadow: var(--shadow-md);
            }}
            
            .help-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-4);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }}
            
            .help-list {{
                text-align: left;
                color: var(--gray-700);
                font-size: 0.875rem;
                line-height: 1.6;
            }}
            
            .help-list li {{
                margin-bottom: var(--space-2);
                padding-left: var(--space-2);
            }}
            
            .retry-section {{
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
            
            .retry-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--primary-pink-dark);
                margin-bottom: var(--space-3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }}
            
            .bot-branding {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
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
                
                .help-list {{
                    font-size: 0.8125rem;
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
            <!-- Error Header -->
            <div class="error-header">
                <div class="error-icon">❌</div>
                <h1 class="page-title">エラーが発生しました</h1>
            </div>
            
            <!-- Error Message -->
            <div class="error-message">
                {message}
            </div>
            
            <!-- Help Section -->
            <div class="help-section">
                <h2 class="help-title">
                    <span>💡</span>
                    対処方法
                </h2>
                <ul class="help-list">
                    <li>ページを再読み込みして再度お試しください</li>
                    <li>しばらく時間をおいてから再度アクセスしてください</li>
                    <li>問題が継続する場合は、サポートサーバーまでお問い合わせください</li>
                </ul>
            </div>
            
            <!-- Retry Section -->
            <div class="retry-section">
                <div class="retry-title">
                    <span>🔄</span>
                    再試行してください
                </div>
                ブラウザの戻るボタンで前のページに戻り、もう一度操作をお試しください。
            </div>
            
            <!-- Bot Branding -->
            <div class="bot-branding">
                <img src="/static/bot-icon.jpeg" alt="Discord Invitation & Role Bot" class="bot-icon">
                <span class="bot-text">Discord Invitation & Role Bot</span>
            </div>
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
                background: var(--white);
                color: var(--gray-900);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                margin-bottom: var(--space-8);
                border: 2px solid var(--primary-pink);
                box-shadow: var(--shadow-md);
            }}
            
            .role-label {{
                font-size: 0.875rem;
                font-weight: var(--font-weight-medium);
                color: var(--gray-600);
                margin-bottom: var(--space-2);
            }}
            
            .role-name {{
                font-size: 1.25rem;
                font-weight: var(--font-weight-semibold);
                color: var(--primary-pink);
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
                    <div class="bot-subtitle">このBotでサーバー参加とロール付与が行われます</div>
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
    # Botからサーバー情報を取得
    try:
        import asyncio
        from discord_bot.bot import bot
        
        app.logger.info(f"Bot instance: {bot}")
        app.logger.info(f"Bot is ready: {bot.is_ready()}")
        app.logger.info(f"Bot guilds count: {len(bot.guilds)}")
        app.logger.info(f"Trying to get guild: {guild_id}")
        
        # fetch_guildを直接使用してギルド情報を取得
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            guild = loop.run_until_complete(bot.fetch_guild(int(guild_id)))
            app.logger.info(f"Guild fetched: {guild}")
            loop.close()
        except Exception as fetch_error:
            app.logger.error(f"Failed to fetch guild: {fetch_error}")
            guild = None
        
        if guild:
            guild_name = guild.name
            guild_icon_url = guild.icon.url if guild.icon else None
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
        <title>ロール付与完了 - Discord Invitation & Role Bot</title>
        <meta name="description" content="Discordサーバーへの参加とロール付与が正常に完了しました">
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
                max-width: 600px;
                width: 100%;
                text-align: center;
                border: 1px solid var(--gray-200);
            }}
            
            .success-header {{
                margin-bottom: var(--space-8);
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
            
            .welcome-message {{
                font-size: 1.25rem;
                color: var(--gray-700);
                font-weight: var(--font-weight-medium);
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
            
            .role-details {{
                background: var(--gray-50);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                margin-bottom: var(--space-8);
                text-align: left;
                border: 1px solid var(--gray-200);
                box-shadow: var(--shadow-md);
            }}
            
            .details-title {{
                font-size: 1.125rem;
                font-weight: var(--font-weight-semibold);
                color: var(--gray-900);
                margin-bottom: var(--space-4);
                text-align: center;
            }}
            
            .detail-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-4);
                margin-bottom: var(--space-2);
                background: var(--white);
                border-radius: var(--radius-md);
                border: 1px solid var(--gray-200);
            }}
            
            .detail-row:last-child {{
                margin-bottom: 0;
            }}
            
            .detail-label {{
                font-weight: var(--font-weight-medium);
                color: var(--gray-600);
                font-size: 0.875rem;
            }}
            
            .detail-value {{
                color: var(--gray-900);
                font-weight: var(--font-weight-semibold);
                background: linear-gradient(135deg, var(--primary-pink) 0%, var(--primary-orange) 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .celebration-message {{
                background: linear-gradient(135deg, var(--warm-50) 0%, var(--primary-pink-light) 20%, var(--primary-orange-light) 100%);
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                border: 2px solid var(--primary-pink);
                box-shadow: var(--shadow-md);
                color: var(--gray-900);
                font-weight: var(--font-weight-medium);
                line-height: 1.7;
            }}
            
            .celebration-title {{
                font-size: 1.25rem;
                font-weight: var(--font-weight-semibold);
                color: var(--primary-pink-dark);
                margin-bottom: var(--space-3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }}
            
            .bot-branding {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                margin-top: var(--space-8);
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
                
                .welcome-message {{
                    font-size: 1.125rem;
                }}
                
                .detail-row {{
                    flex-direction: column;
                    align-items: flex-start;
                    gap: var(--space-2);
                }}
                
                .detail-value {{
                    align-self: flex-end;
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
                <div class="success-icon">🎉</div>
                <h1 class="page-title">参加完了！</h1>
                <p class="welcome-message">{welcome_text}</p>
            </div>
            
            <!-- Success Info -->
            <div class="success-info">
                ✅ ロール付与が正常に完了しました
            </div>
            
            <!-- Role Details -->
            <div class="role-details">
                <h2 class="details-title">📋 詳細情報</h2>
                <div class="detail-row">
                    <span class="detail-label">👤 ユーザー名</span>
                    <span class="detail-value">{username}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">🏷️ 付与されたロール</span>
                    <span class="detail-value">{role_name}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">📊 ステータス</span>
                    <span class="detail-value">{"参加完了" if not is_returning else "ロール追加完了"}</span>
                </div>
            </div>
            
            <!-- Celebration Message -->
            <div class="celebration-message">
                <div class="celebration-title">
                    <span>🎊</span>
                    おめでとうございます！
                    <span>🎊</span>
                </div>
                あなたは{action_text}、<strong>{role_name}</strong>ロールを獲得しました。<br>
                このページを閉じて、Discordに戻ってお楽しみください。
            </div>
            
            <!-- Bot Branding -->
            <div class="bot-branding">
                <img src="/static/bot-icon.jpeg" alt="Discord Invitation & Role Bot" class="bot-icon">
                <span class="bot-text">Discord Invitation & Role Bot で処理されました</span>
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