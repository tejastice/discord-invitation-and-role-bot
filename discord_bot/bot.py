import os
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
import string
import secrets
from datetime import datetime, timedelta, timezone
from shared.models import save_invite_link, get_guild_invite_links, get_user_invite_links, delete_invite_link
from shared.database import init_database

# 環境変数を読み込み
load_dotenv()

# タイムゾーン設定（日本時間）
JST = timezone(timedelta(hours=9))

# Bot設定
TOKEN = os.getenv('DISCORD_TOKEN')
DEV_GUILD_ID = int(os.getenv('DISCORD_DEV_GUILD_ID', 0))
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
PREMIUM_ROLE_ID = int(os.getenv('PREMIUM_ROLE_ID', 0))
FREE_USER_PERSONAL_LINK_LIMIT = int(os.getenv('FREE_USER_PERSONAL_LINK_LIMIT', 3))
FREE_USER_SERVER_LINK_LIMIT = int(os.getenv('FREE_USER_SERVER_LINK_LIMIT', 10))

# Intentsの設定
intents = discord.Intents.default()

# Botインスタンス作成
# スラッシュコマンドのみを使用するが、command_prefixは必須なので使わないプレフィックスを設定
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    """Bot起動時の処理"""
    print(f'{bot.user} がログインしました!')
    print(f'Bot ID: {bot.user.id}')
    
    # スラッシュコマンドをグローバルに同期
    try:
        synced = await bot.tree.sync()
        print(f'グローバルに {len(synced)} 個のスラッシュコマンドを同期しました')
        print('注意: グローバルコマンドの反映には最大1時間かかる場合があります')
    except Exception as e:
        print(f'スラッシュコマンドの同期に失敗しました: {e}')
    
    # アクティビティを設定
    activity = discord.Activity(type=discord.ActivityType.watching, name="招待リンク管理")
    await bot.change_presence(activity=activity)


#######################
# ユーザーがプレミアムロールを持っているかどうかをチェックする関数
# - has_premium_role(user: discord.User) -> bool:
# - この関数は、ユーザーがプレミアムロールを持っているかどうかを確認します。
# - プレミアムロールIDは環境変数から取得します。
# - 開発用のギルドIDは環境変数から取得します。
# - 開発用のギルドでプレミアムロールを持っているかどうかを判別します
# - ユーザー情報はfetchで取得します。
#######################

async def has_premium_role(user: discord.User) -> bool:
    """
    ユーザーがプレミアムロールを持っているかどうかをチェック
    
    Args:
        user: チェック対象のDiscordユーザー
        
    Returns:
        bool: プレミアムロールを持っている場合True、そうでなければFalse
    """
    try:
        # プレミアムロールIDが設定されていない場合は全員フリーユーザーとして扱う
        if not PREMIUM_ROLE_ID or not DEV_GUILD_ID:
            return False
        
        # 開発用ギルドを取得
        guild = bot.get_guild(DEV_GUILD_ID)
        if not guild:
            # ギルドが取得できない場合はfetchで試行
            try:
                guild = await bot.fetch_guild(DEV_GUILD_ID)
            except:
                return False
        
        # ユーザーのメンバー情報を取得
        try:
            member = await guild.fetch_member(user.id)
        except:
            # メンバーが見つからない場合はプレミアムではない
            return False
        
        # プレミアムロールを持っているかチェック
        premium_role = guild.get_role(PREMIUM_ROLE_ID)
        if premium_role and premium_role in member.roles:
            return True
        
        return False
        
    except Exception as e:
        print(f"プレミアムロールのチェック中にエラーが発生しました: {e}")
        return False

async def check_invite_link_limits(user: discord.User, guild_id: int) -> tuple[bool, str]:
    """
    招待リンク作成制限をチェック
    
    Args:
        user: チェック対象のDiscordユーザー
        guild_id: 対象のギルドID
        
    Returns:
        tuple[bool, str]: (制限内かどうか, エラーメッセージ)
    """
    try:
        # プレミアムユーザーは制限なし
        if await has_premium_role(user):
            return True, ""
        
        # フリーユーザーの制限チェック
        from shared.models import get_user_invite_links, get_guild_invite_links
        
        # 個人の招待リンク数をチェック
        user_links = get_user_invite_links(user.id)
        if len(user_links) >= FREE_USER_PERSONAL_LINK_LIMIT:
            return False, f"フリープランでは個人の招待リンクは最大{FREE_USER_PERSONAL_LINK_LIMIT}個までです。プレミアムプランへのアップグレードや既存リンクの削除方法については、こちらをご確認ください: {os.getenv('OFFICIAL_WEBSITE_URL', 'https://discord-invitation-and-rol-bote.kei31.com/')}"
        
        # サーバーの招待リンク数をチェック
        guild_links = get_guild_invite_links(guild_id)
        if len(guild_links) >= FREE_USER_SERVER_LINK_LIMIT:
            return False, f"フリープランでは1サーバーあたりの招待リンクは最大{FREE_USER_SERVER_LINK_LIMIT}個までです。プレミアムプランへのアップグレードや既存リンクの削除方法については、こちらをご確認ください: {os.getenv('OFFICIAL_WEBSITE_URL', 'https://discord-invitation-and-rol-bote.kei31.com/')}"
        
        return True, ""
        
    except Exception as e:
        print(f"招待リンク制限チェック中にエラーが発生しました: {e}")
        return False, "制限チェック中にエラーが発生しました。"






#######################
# 招待コマンドを作るスラッシュコマンド
# - /generate_invite_link
# - 引数: role, max_uses(optional), expires_at(optional)
# - このDiscordの管理権限がある場合に動く
# - ユーザーがプレミアムロールを持っていた場合、制限なく使える
# - ユーザーがプレミアムロールを持っていない場合、
#   - 個人用の招待リンクは最大FREE_USER_PERSONAL_LINK_LIMIT個以上は作成できない
#   - サーバー用の招待リンクは最大FREE_USER_SERVER_LINK_LIMIT個以上は作成できない
# - 10桁のランダムな半角小文字の英数字を生成してlink IDとする
# - これをデータベースに保存する
# - 生成した招待リンクを返す
#######################

def format_role_names(guild: discord.Guild, link: dict) -> str:
    """招待リンクのロール名を表示用の文字列にする（2つ目のロールがあれば「A + B」）"""
    if not guild:
        return "不明ロール"
    
    names = []
    for role_id in (link['role_id'], link.get('role_id_2')):
        if role_id:
            role = guild.get_role(role_id)
            names.append(role.name if role else "不明ロール")
    return " + ".join(names)

def generate_link_id() -> str:
    """10桁のランダムな半角小文字の英数字を生成"""
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(10))

def parse_expires_at(expires_str: str) -> tuple:
    """日付文字列をパースして(表示用JST文字列, Unixタイムスタンプ)のタプルを返す"""
    if not expires_str:
        return None, None
    
    # 現在の日本時間を取得
    now_jst = datetime.now(JST)
    
    # 相対時間の処理（例：1d, 2h, 30m）
    if expires_str.endswith('d'):
        days = int(expires_str[:-1])
        future_time = now_jst + timedelta(days=days)
    elif expires_str.endswith('h'):
        hours = int(expires_str[:-1])
        future_time = now_jst + timedelta(hours=hours)
    elif expires_str.endswith('m'):
        minutes = int(expires_str[:-1])
        future_time = now_jst + timedelta(minutes=minutes)
    else:
        # 絶対時間の処理（例：2024-12-31, 2024-12-31 23:59）
        # 日本時間として解釈
        try:
            # YYYY-MM-DD HH:MM 形式
            if len(expires_str) == 16:
                parsed_time = datetime.strptime(expires_str, '%Y-%m-%d %H:%M')
            # YYYY-MM-DD 形式（時刻は23:59に設定）
            elif len(expires_str) == 10:
                parsed_time = datetime.strptime(expires_str + ' 23:59', '%Y-%m-%d %H:%M')
            else:
                raise ValueError("Invalid date format")
            
            # JSTタイムゾーンを設定
            future_time = parsed_time.replace(tzinfo=JST)
        except ValueError:
            raise ValueError(f"無効な日付形式です: {expires_str}")
    
    # 表示用JST文字列
    display_str = future_time.strftime('%Y-%m-%d %H:%M JST')
    
    # Unixタイムスタンプ
    unix_timestamp = int(future_time.timestamp())
    
    return display_str, unix_timestamp

@bot.tree.command(name="generate_invite_link", description="ロール招待リンクを生成します")
@discord.app_commands.describe(
    role="招待リンクを生成するロール", 
    role2="追加で付与する2つ目のロール（任意）", 
    max_uses="最大使用回数（例：5）", 
    expires_at="有効期限・日本時間（例：7d, 24h, 2024-12-31, 2024-12-31 23:59）"
)
async def generate_invite_link(interaction: discord.Interaction, role: discord.Role, role2: discord.Role = None, max_uses: int = None, expires_at: str = None):
    """ロール招待リンクを生成するスラッシュコマンド"""
    
    # 管理権限チェック
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ このコマンドを使用するには「サーバー管理」権限が必要です。", ephemeral=True)
        return
    
    # 2つ目のロールは1つ目と別のロールにする
    if role2 and role2.id == role.id:
        await interaction.response.send_message("❌ 2つ目のロールには、1つ目とは別のロールを指定してください。", ephemeral=True)
        return
    
    # 招待リンク制限チェック
    can_create, error_message = await check_invite_link_limits(interaction.user, interaction.guild.id)
    if not can_create:
        await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
        return
    
    # 日付文字列をパース
    try:
        if expires_at:
            expires_display, expires_unix = parse_expires_at(expires_at)
        else:
            expires_display, expires_unix = None, None
    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        return
    
    # 10桁のランダムなlink IDを生成
    link_id = generate_link_id()
    
    # 作成日時を生成（JST）
    now_jst = datetime.now(JST)
    created_at_display = now_jst.strftime('%Y-%m-%d %H:%M:%S JST')
    created_at_unix = int(now_jst.timestamp())
    
    # データベースに保存
    if not save_invite_link(
        guild_id=interaction.guild.id, 
        role_id=role.id, 
        link_id=link_id, 
        created_by_user_id=interaction.user.id, 
        max_uses=max_uses, 
        expires_at=expires_display, 
        expires_at_unix=expires_unix,
        created_at=created_at_display,
        created_at_unix=created_at_unix,
        role_id_2=role2.id if role2 else None
    ):
        await interaction.response.send_message("❌ データベースへの保存に失敗しました。", ephemeral=True)
        return
    
    # 招待リンクURL生成
    invite_url = f"{BASE_URL}/join/{link_id}"
    
    # 結果を返す
    embed = discord.Embed(
        title="🎉 招待リンクが生成されました",
        color=0x00ff00
    )
    embed.add_field(name="サーバー", value=interaction.guild.name, inline=True)
    embed.add_field(name="対象ロール", value=f"{role.mention} + {role2.mention}" if role2 else role.mention, inline=True)
    embed.add_field(name="リンクID", value=link_id, inline=True)
    embed.add_field(name="作成者", value=interaction.user.mention, inline=True)
    embed.add_field(name="招待リンク", value=f"[こちらをクリック]({invite_url})", inline=False)
    embed.add_field(name="直接URL", value=f"`{invite_url}`", inline=False)
    
    if max_uses:
        embed.add_field(name="最大使用回数", value=str(max_uses), inline=True)
    if expires_display:
        embed.add_field(name="有効期限（日本時間）", value=expires_display, inline=True)
    
    # セキュリティ注意書きを追加
    embed.add_field(
        name="⚠️ 重要な注意事項", 
        value="**このリンクを知っている人は誰でもサーバーに参加してロールを取得できます。リンクの管理を厳重に行い、信頼できる人にのみ共有してください。**", 
        inline=False
    )
    
    # 生成日時を表示
    embed.set_footer(text=f"生成日時: {created_at_display}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


#################
# そのサーバー内でロールを付与するためのリンクを一覧表示して削除するスラッシュコマンド
# - /list_server_invite_links
# - 管理者のみ実行できる
# - 引数は無し
# - データベースから、このサーバーのロール招待リンク一覧を取得する
# - ロールIDからロール名を取得する
# - ロールがすでに削除されていた場合は、不明ロールと表記する
# - 全ての[リンクID、ロール名、実際のリンク、現在の使用回数、max使用回数、有効期限、作った人]を表示する
# - 有効期限は、データベースのunixtimeといまのunixtimeを比較して判定する
# - 今の日本時刻も取得して表示する
# - 有効期限が切れている場合は、❌アイコンを表示する
# - 使用回数がmax使用回数を超えている場合も❌アイコンを表示する
# - 有効なリンクは、✅アイコンを表示する
# - プルダウンメニューにロール名とリンクID一覧を表示する
# - プルダウンメニューから選んでdeleteボタンを押すと、その行をデータベースから削除する
#################

class InviteLinkSelectView(discord.ui.View):
    def __init__(self, invite_links: list, guild: discord.Guild = None, is_user_view: bool = False):
        super().__init__(timeout=300)
        self.invite_links = invite_links
        self.guild = guild
        self.is_user_view = is_user_view
        
        # プルダウンメニュー作成
        if invite_links:
            select_options = []
            for link in invite_links[:25]:  # Discordの制限で最大25個
                if self.is_user_view:
                    # ユーザー用：ギルド名とロール名を取得
                    guild = bot.get_guild(link['guild_id'])
                    guild_name = guild.name if guild else f"不明サーバー({link['guild_id']})"
                    
                    role_name = format_role_names(guild, link)
                    
                    label_text = f"{guild_name} - {role_name} ({link['link_id']})"
                else:
                    # 管理者用：ロール名のみ取得
                    role_name = format_role_names(self.guild, link)
                    label_text = f"{role_name} ({link['link_id']})"
                
                # 使用可能かどうかをチェック
                is_expired = False
                is_usage_exceeded = False
                
                # 有効期限チェック（Unixタイムスタンプで比較）
                if link['expires_at_unix']:
                    now_unix = int(time.time())
                    if now_unix > link['expires_at_unix']:
                        is_expired = True
                
                # 使用回数チェック
                if link['max_uses'] and link['current_uses'] >= link['max_uses']:
                    is_usage_exceeded = True
                
                # アイコン決定
                if is_expired or is_usage_exceeded:
                    icon = "❌"
                else:
                    icon = "✅"
                
                select_options.append(discord.SelectOption(
                    label=f"{icon} {label_text}"[:100],  # Discordの制限で最大100文字
                    value=link['link_id'],
                    description=f"使用: {link['current_uses']}/{link['max_uses'] or '無制限'}"
                ))
            
            self.select_menu = discord.ui.Select(
                placeholder="削除する招待リンクを選択してください",
                options=select_options
            )
            self.select_menu.callback = self.select_callback
            self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        """プルダウンメニューの選択時のコールバック"""
        selected_link_id = interaction.data['values'][0]
        
        # 選択されたリンクの情報を取得
        selected_link = next((link for link in self.invite_links if link['link_id'] == selected_link_id), None)
        if not selected_link:
            await interaction.response.send_message("❌ 選択されたリンクが見つかりません。", ephemeral=True)
            return
        
        if self.is_user_view:
            # ユーザー用：ギルド名とロール名を取得
            guild = bot.get_guild(selected_link['guild_id'])
            guild_name = guild.name if guild else f"不明サーバー({selected_link['guild_id']})"
            
            role_name = format_role_names(guild, selected_link)
            
            # 確認メッセージ
            embed = discord.Embed(
                title="🗑️ 招待リンクの削除確認",
                description=f"以下の招待リンクを削除しますか？",
                color=0xff0000
            )
            embed.add_field(name="サーバー", value=guild_name, inline=True)
            embed.add_field(name="ロール", value=role_name, inline=True)
            embed.add_field(name="リンクID", value=selected_link_id, inline=True)
            embed.add_field(name="使用回数", value=f"{selected_link['current_uses']}/{selected_link['max_uses'] or '無制限'}", inline=True)
            
            confirm_view = ConfirmDeleteView(selected_link_id, f"{guild_name} - {role_name}")
        else:
            # 管理者用：ロール名のみ取得
            role_name = format_role_names(self.guild, selected_link)
            
            # 確認メッセージ
            embed = discord.Embed(
                title="🗑️ 招待リンクの削除確認",
                description=f"以下の招待リンクを削除しますか？",
                color=0xff0000
            )
            embed.add_field(name="ロール", value=role_name, inline=True)
            embed.add_field(name="リンクID", value=selected_link_id, inline=True)
            embed.add_field(name="使用回数", value=f"{selected_link['current_uses']}/{selected_link['max_uses'] or '無制限'}", inline=True)
            
            confirm_view = ConfirmDeleteView(selected_link_id, role_name)
        
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, link_id: str, role_name: str):
        super().__init__(timeout=60)
        self.link_id = link_id
        self.role_name = role_name

    @discord.ui.button(label="削除する", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """削除確認ボタンの処理"""
        if delete_invite_link(self.link_id):
            embed = discord.Embed(
                title="✅ 削除完了",
                description=f"招待リンク `{self.link_id}` ({self.role_name})を削除しました。",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message("❌ 削除に失敗しました。", ephemeral=True)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """削除キャンセルボタンの処理"""
        await interaction.response.edit_message(content="削除をキャンセルしました。", embed=None, view=None)

@bot.tree.command(name="list_server_invite_links", description="サーバーのロール招待リンクの一覧表示と削除")
async def list_server_invite_links(interaction: discord.Interaction):
    """ロール招待リンクの一覧表示と削除管理"""
    
    # 管理権限チェック
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ このコマンドを使用するには「サーバー管理」権限が必要です。", ephemeral=True)
        return
    
    # 処理時間がかかる可能性があるため、先にdeferする
    await interaction.response.defer(ephemeral=True)
    
    # データベースから招待リンク一覧を取得
    invite_links = get_guild_invite_links(interaction.guild.id)
    
    if not invite_links:
        await interaction.followup.send("📝 このサーバーには招待リンクがありません.", ephemeral=True)
        return
    
    # 結果を表示
    embed = discord.Embed(
        title="📋 サーバーのロール招待リンク一覧",
        description=f"{interaction.guild.name} の招待リンク一覧",
        color=0x0099ff
    )
    
    for i, link in enumerate(invite_links[:10], 1):  # 最大10個まで表示
        # ロール名を取得
        role_name = format_role_names(interaction.guild, link)
        
        # 作成者を取得
        try:
            creator = await bot.fetch_user(link['created_by_user_id'])
            creator_name = creator.display_name
        except:
            creator_name = "不明ユーザー"
        
        # 有効期限の表示（UTCから日本時間に変換して表示）
        if link['expires_at']:
            try:
                expires_utc = datetime.strptime(link['expires_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                expires_jst = expires_utc.astimezone(JST)
                expires_text = expires_jst.strftime('%Y-%m-%d %H:%M JST')
            except:
                expires_text = link['expires_at']
        else:
            expires_text = "無期限"
        
        # 使用可能かどうかをチェック
        is_expired = False
        is_usage_exceeded = False
        
        # 有効期限チェック（Unixタイムスタンプで比較）
        if link['expires_at_unix']:
            now_unix = int(time.time())
            if now_unix > link['expires_at_unix']:
                is_expired = True
        
        # 使用回数チェック
        if link['max_uses'] and link['current_uses'] >= link['max_uses']:
            is_usage_exceeded = True
        
        # アイコンと状態メッセージ決定
        if is_expired or is_usage_exceeded:
            icon = "❌"
            # 理由を作成
            reasons = []
            if is_expired:
                reasons.append("有効期限切れ")
            if is_usage_exceeded:
                reasons.append("使用回数上限")
            status_message = f"**状態:** {'/'.join(reasons)}"
        else:
            icon = "✅"
            status_message = "**状態:** 有効"
        
        field_value = (
            f"**リンクID:** `{link['link_id']}`\n"
            f"**URL:** {BASE_URL}/join/{link['link_id']}\n"
            f"**使用回数:** {link['current_uses']}/{link['max_uses'] or '無制限'}\n"
            f"**有効期限:** {expires_text}\n"
            f"**作成者:** {creator_name}\n"
            f"{status_message}"
        )
        
        embed.add_field(
            name=f"{icon} {i}. {role_name}",
            value=field_value,
            inline=False
        )
    
    if len(invite_links) > 10:
        embed.set_footer(text=f"他に {len(invite_links) - 10} 個の招待リンクがあります")
    
    # プルダウンメニュー付きビューを作成（管理者用）
    view = InviteLinkSelectView(invite_links, guild=interaction.guild, is_user_view=False)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)



#################
# 自分が作った招待リンクの一覧を表示して削除するスラッシュコマンド
# - /list_my_invite_links
# - だれでも実行できる
# - 引数は無し
# - データベースから、自分が作成したロール招待リンク一覧を取得する
# - ギルドIDからギルド名を取得する
# - ギルド名が取得できない場合は、ギルドIDを表示
# - ロールIDからロール名を取得する
# - ロール名が取得できない場合は、「不明ロール」と表示
# - ロールがすでに削除されていた場合は、不明ロールと表記する
# - 全ての[リンクID、サーバー名、ロール名、実際のリンク、現在の使用回数、max使用回数、有効期限、作った人]を表示する
# - 有効期限は、データベースのunixtimeといまのunixtimeを比較して判定する
# - 今の日本時刻も取得して表示する
# - 有効期限が切れている場合は、❌アイコンを表示する
# - 使用回数がmax使用回数を超えている場合も❌アイコンを表示する
# - 有効なリンクは、✅アイコンを表示する
# - プルダウンメニューにロール名とリンクID一覧を表示する
# - プルダウンメニューから選んでdeleteボタンを押すと、その行をデータベースから削除する
#################


@bot.tree.command(name="list_my_invite_links", description="自分が作成した招待リンクの一覧表示と削除")
async def list_my_invite_links(interaction: discord.Interaction):
    """自分が作成した招待リンクの一覧表示と削除管理"""
    
    # 処理時間がかかる可能性があるため、先にdeferする
    await interaction.response.defer(ephemeral=True)
    
    # データベースから自分の招待リンク一覧を取得
    invite_links = get_user_invite_links(interaction.user.id)
    
    if not invite_links:
        await interaction.followup.send("📝 あなたが作成した招待リンクはありません。", ephemeral=True)
        return
    
    # 結果を表示
    embed = discord.Embed(
        title="📋 あなたの招待リンク一覧",
        description=f"作成者: {interaction.user.display_name}",
        color=0x0099ff
    )
    
    for i, link in enumerate(invite_links[:10], 1):  # 最大10個まで表示
        # ギルド名を取得
        guild = bot.get_guild(link['guild_id'])
        guild_name = guild.name if guild else f"不明サーバー({link['guild_id']})"
        
        # ロール名を取得
        role_name = format_role_names(guild, link)
        
        # 有効期限の表示（データベースから取得した文字列をそのまま表示）
        expires_text = link['expires_at'] if link['expires_at'] else "無期限"
        
        # 使用可能かどうかをチェック
        is_expired = False
        is_usage_exceeded = False
        
        # 有効期限チェック（Unixタイムスタンプで比較）
        if link['expires_at_unix']:
            now_unix = int(time.time())
            if now_unix > link['expires_at_unix']:
                is_expired = True
        
        # 使用回数チェック
        if link['max_uses'] and link['current_uses'] >= link['max_uses']:
            is_usage_exceeded = True
        
        # アイコンと状態メッセージ決定
        if is_expired or is_usage_exceeded:
            icon = "❌"
            # 理由を作成
            reasons = []
            if is_expired:
                reasons.append("有効期限切れ")
            if is_usage_exceeded:
                reasons.append("使用回数上限")
            status_message = f"**状態:** {'/'.join(reasons)}"
        else:
            icon = "✅"
            status_message = "**状態:** 有効"
        
        field_value = (
            f"**サーバー:** {guild_name}\n"
            f"**リンクID:** `{link['link_id']}`\n"
            f"**URL:** {BASE_URL}/join/{link['link_id']}\n"
            f"**使用回数:** {link['current_uses']}/{link['max_uses'] or '無制限'}\n"
            f"**有効期限:** {expires_text}\n"
            f"**作成日時:** {link['created_at']}\n"
            f"{status_message}"
        )
        
        embed.add_field(
            name=f"{icon} {i}. {role_name}",
            value=field_value,
            inline=False
        )
    
    if len(invite_links) > 10:
        embed.set_footer(text=f"他に {len(invite_links) - 10} 個の招待リンクがあります")
    
    # プルダウンメニュー付きビューを作成（ユーザー用）
    view = InviteLinkSelectView(invite_links, guild=None, is_user_view=True)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)




if __name__ == "__main__":
    if not TOKEN:
        print("エラー: DISCORD_TOKENが設定されていません")
        exit(1)
    
    # データベースを初期化
    try:
        print("データベースを初期化しています...")
        init_database()
    except Exception as e:
        print(f"データベース初期化エラー: {e}")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("エラー: 無効なトークンです")
    except Exception as e:
        print(f"予期しないエラー: {e}")