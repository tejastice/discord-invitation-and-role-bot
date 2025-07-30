from .database import get_db_cursor

def save_invite_link(guild_id: int, role_id: int, link_id: str, created_by_user_id: int, max_uses: int = None, expires_at: str = None, expires_at_unix: int = None, created_at: str = None, created_at_unix: int = None) -> bool:
    """招待リンクをデータベースに保存"""
    try:
        with get_db_cursor() as cursor:
            query = """
                INSERT INTO role_invite_links (guild_id, role_id, link_id, created_by_user_id, max_uses, current_uses, expires_at, expires_at_unix, created_at, created_at_unix)
                VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s)
            """
            cursor.execute(query, (guild_id, role_id, link_id, created_by_user_id, max_uses, expires_at, expires_at_unix, created_at, created_at_unix))
            return True
    except Exception as e:
        print(f"Failed to save invite link: {e}")
        return False

def increment_invite_usage(link_id: str) -> bool:
    """招待リンクの使用回数をインクリメント"""
    try:
        with get_db_cursor() as cursor:
            query = """
                UPDATE role_invite_links 
                SET current_uses = current_uses + 1
                WHERE link_id = %s
            """
            cursor.execute(query, (link_id,))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Failed to increment invite usage: {e}")
        return False

def get_invite_link_info(link_id: str) -> dict:
    """招待リンクの情報を取得"""
    try:
        with get_db_cursor() as cursor:
            query = """
                SELECT guild_id, role_id, link_id, created_by_user_id, max_uses, current_uses, expires_at, expires_at_unix, created_at, created_at_unix
                FROM role_invite_links
                WHERE link_id = %s
            """
            cursor.execute(query, (link_id,))
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            return None
    except Exception as e:
        print(f"Failed to get invite link info: {e}")
        return None

def get_guild_invite_links(guild_id: int) -> list:
    """指定サーバーの招待リンク一覧を取得"""
    try:
        with get_db_cursor() as cursor:
            query = """
                SELECT id, guild_id, role_id, link_id, created_by_user_id, max_uses, current_uses, expires_at, expires_at_unix, created_at, created_at_unix
                FROM role_invite_links
                WHERE guild_id = %s
                ORDER BY created_at_unix DESC
            """
            cursor.execute(query, (guild_id,))
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
    except Exception as e:
        print(f"Failed to get guild invite links: {e}")
        return []

def get_user_invite_links(user_id: int) -> list:
    """指定ユーザーが作成した招待リンク一覧を取得"""
    try:
        with get_db_cursor() as cursor:
            query = """
                SELECT id, guild_id, role_id, link_id, created_by_user_id, max_uses, current_uses, expires_at, expires_at_unix, created_at, created_at_unix
                FROM role_invite_links
                WHERE created_by_user_id = %s
                ORDER BY created_at_unix DESC
            """
            cursor.execute(query, (user_id,))
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
    except Exception as e:
        print(f"Failed to get user invite links: {e}")
        return []

def delete_invite_link(link_id: str) -> bool:
    """招待リンクをデータベースから削除"""
    try:
        with get_db_cursor() as cursor:
            query = "DELETE FROM role_invite_links WHERE link_id = %s"
            cursor.execute(query, (link_id,))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Failed to delete invite link: {e}")
        return False