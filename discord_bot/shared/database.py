import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

@contextmanager
def get_db_cursor():
    """データベースカーソルのコンテキストマネージャー"""
    conn = None
    cursor = None
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        conn = psycopg2.connect(DATABASE_URL, sslmode='prefer')
        conn.autocommit = True
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Database operation failed: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_database():
    """データベーステーブルを初期化"""
    try:
        with get_db_cursor() as cursor:
            # role_invite_linksテーブル作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS role_invite_links (
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
                )
            """)
            
            # インデックス作成
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_guild_id 
                ON role_invite_links(guild_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_role_id 
                ON role_invite_links(role_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_link_id 
                ON role_invite_links(link_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_created_by 
                ON role_invite_links(created_by_user_id)
            """)
            
            logger.info("Database tables initialized successfully")
            print("Database tables initialized successfully")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"Failed to initialize database: {e}")
        raise

if __name__ == "__main__":
    # テスト用の初期化
    init_database()
    print("Database initialized successfully")