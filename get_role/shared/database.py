import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# データベース接続設定
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """データベース接続を取得"""
    try:
        if DATABASE_URL:
            # Heroku等のクラウド環境用
            conn = psycopg2.connect(DATABASE_URL, sslmode='prefer')
        else:
            # ローカル開発環境用
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                database=os.getenv('DB_NAME', 'discord_bot'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', ''),
                port=os.getenv('DB_PORT', '5432')
            )
        
        conn.autocommit = True
        return conn
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

@contextmanager
def get_db_cursor():
    """データベースカーソルのコンテキストマネージャー"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database operation failed: {e}")
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
                    role_id BIGINT NOT NULL,
                    link_id VARCHAR(255) UNIQUE NOT NULL,
                    created_by_user_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # インデックス作成
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_role_id 
                ON role_invite_links(role_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_invite_links_link_id 
                ON role_invite_links(link_id)
            """)
            
            logger.info("Database tables initialized successfully")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

if __name__ == "__main__":
    # テスト用の初期化
    init_database()
    print("Database initialized successfully")