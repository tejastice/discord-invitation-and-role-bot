import os
import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
import time

logger = logging.getLogger(__name__)

# グローバル接続プール
_connection_pool = None
_pool_lock = False

def get_connection_pool():
    """接続プールを取得（存在しなければ作成）"""
    global _connection_pool, _pool_lock

    if _connection_pool is None:
        # 初期化中の二重実行を防ぐ
        if _pool_lock:
            time.sleep(0.1)
            return get_connection_pool()

        _pool_lock = True
        try:
            DATABASE_URL = os.getenv('DATABASE_URL')
            if not DATABASE_URL:
                raise ValueError("DATABASE_URL environment variable is not set")

            # 接続プールを作成（最小1接続、最大10接続）
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=DATABASE_URL,
                sslmode='prefer',
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            logger.info("Database connection pool created successfully")
            print("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            print(f"Failed to create connection pool: {e}")
            _connection_pool = None
            raise
        finally:
            _pool_lock = False

    return _connection_pool

@contextmanager
def get_db_cursor(max_retries=3):
    """データベースカーソルのコンテキストマネージャー（再接続機能付き）"""
    conn = None
    cursor = None
    retry_count = 0
    last_error = None

    while retry_count < max_retries:
        try:
            # 接続プールから接続を取得
            pool_obj = get_connection_pool()
            conn = pool_obj.getconn()

            # 接続が有効か確認
            conn.isolation_level

            conn.autocommit = True
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # カーソルを返す
            yield cursor

            # 正常終了したらループを抜ける
            break

        except (OperationalError, psycopg2.InterfaceError, AttributeError) as e:
            last_error = e
            retry_count += 1

            logger.warning(f"Database connection error (attempt {retry_count}/{max_retries}): {e}")
            print(f"Database connection error (attempt {retry_count}/{max_retries}): {e}")

            # 接続をクリーンアップ
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    pool_obj = get_connection_pool()
                    pool_obj.putconn(conn, close=True)
                except:
                    pass

            conn = None
            cursor = None

            # 接続プールをリセット
            if retry_count < max_retries:
                global _connection_pool
                if _connection_pool:
                    try:
                        _connection_pool.closeall()
                    except:
                        pass
                    _connection_pool = None

                # 少し待ってから再試行
                time.sleep(min(retry_count * 0.5, 2))
            else:
                # 最大リトライ回数に達した
                print(f"Database operation failed after {max_retries} retries: {last_error}")
                raise last_error

        except Exception as e:
            # その他のエラー
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            print(f"Database operation failed: {e}")
            raise

        finally:
            # クリーンアップ
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    pool_obj = get_connection_pool()
                    pool_obj.putconn(conn)
                except:
                    pass

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