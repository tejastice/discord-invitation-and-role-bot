import logging
from .database import get_db_cursor

logger = logging.getLogger(__name__)

class RoleInviteLinks:
    """ロール招待リンクを管理するモデル"""
    
    @staticmethod
    def create_role_invite_link(role_id: int, link_id: str, created_by_user_id: int) -> bool:
        """
        ロール招待リンクを作成
        
        Args:
            role_id: DiscordロールID
            link_id: ユニークなリンクID
            created_by_user_id: 作成者のユーザーID
            
        Returns:
            bool: 作成が成功した場合True、重複などで失敗した場合False
        """
        try:
            with get_db_cursor() as cursor:
                # 同じロールIDのリンクが既に存在するかチェック
                check_query = "SELECT id FROM role_invite_links WHERE role_id = %s"
                cursor.execute(check_query, (role_id,))
                existing = cursor.fetchone()
                
                if existing:
                    logger.warning(f"Role invite link already exists for role_id: {role_id}")
                    return False
                
                # 新しいリンクを作成
                insert_query = """
                    INSERT INTO role_invite_links (role_id, link_id, created_by_user_id, created_at)
                    VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(insert_query, (role_id, link_id, created_by_user_id))
                logger.info(f"Role invite link created: role_id={role_id}, link_id={link_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create role invite link: {e}")
            return False
    
    @staticmethod
    def get_all_role_invite_links() -> list:
        """
        すべてのロール招待リンクを取得
        
        Returns:
            list: ロール招待リンクのリスト
        """
        try:
            with get_db_cursor() as cursor:
                query = """
                    SELECT id, role_id, link_id, created_at, created_by_user_id
                    FROM role_invite_links
                    ORDER BY created_at DESC
                """
                cursor.execute(query)
                results = cursor.fetchall()
                
                return [dict(row) for row in results]
                
        except Exception as e:
            logger.error(f"Failed to get all role invite links: {e}")
            return []
    
    @staticmethod
    def get_link_data_by_link_id(link_id: str) -> dict:
        """
        リンクIDからロールリンクの全データを取得
        
        Args:
            link_id: リンクID
            
        Returns:
            dict: ロールリンクのデータ（id, role_id, link_id, created_at, created_by_user_id）
                  存在しない場合はNone
        """
        try:
            with get_db_cursor() as cursor:
                query = """
                    SELECT id, role_id, link_id, created_at, created_by_user_id
                    FROM role_invite_links
                    WHERE link_id = %s
                """
                cursor.execute(query, (link_id,))
                result = cursor.fetchone()
                
                if result:
                    return dict(result)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get link data by link_id: {e}")
            return None
    
    @staticmethod
    def delete_role_invite_link(link_id: str) -> bool:
        """
        ロール招待リンクを削除
        
        Args:
            link_id: 削除するリンクID
            
        Returns:
            bool: 削除が成功した場合True
        """
        try:
            with get_db_cursor() as cursor:
                query = "DELETE FROM role_invite_links WHERE link_id = %s"
                cursor.execute(query, (link_id,))
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Role invite link deleted: link_id={link_id}")
                    return True
                else:
                    logger.warning(f"No role invite link found to delete: link_id={link_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete role invite link: {e}")
            return False
    
    @staticmethod
    def get_role_id_by_link_id(link_id: str) -> int:
        """
        リンクIDからロールIDのみを取得
        
        Args:
            link_id: リンクID
            
        Returns:
            int: ロールID（存在しない場合はNone）
        """
        try:
            with get_db_cursor() as cursor:
                query = "SELECT role_id FROM role_invite_links WHERE link_id = %s"
                cursor.execute(query, (link_id,))
                result = cursor.fetchone()
                
                if result:
                    return result['role_id']
                return None
                
        except Exception as e:
            logger.error(f"Failed to get role_id by link_id: {e}")
            return None
    
    @staticmethod
    def delete_role_invite_link_by_id(record_id: int) -> bool:
        """
        IDでロール招待リンクを削除
        
        Args:
            record_id: 削除するレコードのID
            
        Returns:
            bool: 削除が成功した場合True
        """
        try:
            with get_db_cursor() as cursor:
                query = "DELETE FROM role_invite_links WHERE id = %s"
                cursor.execute(query, (record_id,))
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Role invite link deleted: id={record_id}")
                    return True
                else:
                    logger.warning(f"No role invite link found to delete: id={record_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete role invite link by id: {e}")
            return False

# ロール招待リンク関数のエイリアス
create_role_invite_link = RoleInviteLinks.create_role_invite_link
get_all_role_invite_links = RoleInviteLinks.get_all_role_invite_links
get_link_data_by_link_id = RoleInviteLinks.get_link_data_by_link_id
get_role_id_by_link_id = RoleInviteLinks.get_role_id_by_link_id
delete_role_invite_link = RoleInviteLinks.delete_role_invite_link
delete_role_invite_link_by_id = RoleInviteLinks.delete_role_invite_link_by_id

# 新しいデータベーススキーマ用の関数
def get_invite_link_full_info(link_id: str) -> dict:
    """新しいスキーマから招待リンクの詳細情報を取得"""
    try:
        with get_db_cursor() as cursor:
            query = """
                SELECT guild_id, role_id, link_id, created_by_user_id, max_uses, 
                       current_uses, expires_at, expires_at_unix, created_at, created_at_unix
                FROM role_invite_links
                WHERE link_id = %s
            """
            cursor.execute(query, (link_id,))
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            return None
            
    except Exception as e:
        logger.error(f"Failed to get invite link full info: {e}")
        return None

def increment_invite_link_usage(link_id: str) -> bool:
    """招待リンクの使用回数を+1する"""
    try:
        with get_db_cursor() as cursor:
            query = """
                UPDATE role_invite_links 
                SET current_uses = current_uses + 1
                WHERE link_id = %s
            """
            cursor.execute(query, (link_id,))
            
            updated_count = cursor.rowcount
            if updated_count > 0:
                logger.info(f"Invite link usage incremented: link_id={link_id}")
                return True
            else:
                logger.warning(f"No invite link found to increment: link_id={link_id}")
                return False
                
    except Exception as e:
        logger.error(f"Failed to increment invite link usage: {e}")
        return False