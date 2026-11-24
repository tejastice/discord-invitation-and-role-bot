import os
import psycopg2
from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
import time
import threading

logger = logging.getLogger(__name__)

# グローバル接続プール
_connection_pool = None
_pool_lock = threading.Lock()

def get_connection_pool():
    """接続プールを取得（存在しなければ作成）"""
    global _connection_pool

    if _connection_pool is not None:
        return _connection_pool

    with _pool_lock:
        # ダブルチェックロッキング: ロック取得中に別スレッドが初期化完了していないか確認
        if _connection_pool is not None:
            return _connection_pool

        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")

        try:
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=DATABASE_URL,
                sslmode='require',
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
            raise

    return _connection_pool

def _reset_connection_pool():
    """接続プールを安全にリセット"""
    global _connection_pool
    with _pool_lock:
        if _connection_pool is not None:
            try:
                _connection_pool.closeall()
            except Exception:
                pass
            _connection_pool = None
            logger.info("Connection pool reset")
            print("Connection pool reset")

def _check_connection(conn):
    """接続が実際に有効か SELECT 1 で確認する（PgBouncer対策）"""
    try:
        old_autocommit = conn.autocommit
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.autocommit = old_autocommit
        return True
    except Exception:
        return False

@contextmanager
def get_db_cursor(max_retries=3):
    """データベースカーソルのコンテキストマネージャー（再接続機能付き）"""
    conn = None
    cursor = None
    pool_obj = None
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            pool_obj = get_connection_pool()
            conn = pool_obj.getconn()

            # 接続の生存確認（PgBouncer対策の核心部分）
            if not _check_connection(conn):
                raise OperationalError("Connection health check failed")

            conn.autocommit = True
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            break  # 接続取得成功

        except (OperationalError, psycopg2.InterfaceError, AttributeError) as e:
            last_error = e
            logger.warning(f"Database connection error (attempt {attempt}/{max_retries}): {e}")
            print(f"Database connection error (attempt {attempt}/{max_retries}): {e}")

            # 取得した接続があれば破棄
            if conn and pool_obj:
                try:
                    pool_obj.putconn(conn, close=True)
                except Exception:
                    pass
            conn = None
            cursor = None

            # プール全体をリセット（古い接続が全て無効な可能性が高い）
            _reset_connection_pool()

            if attempt < max_retries:
                time.sleep(min(attempt * 0.5, 2))
            else:
                raise OperationalError(
                    f"Database connection failed after {max_retries} attempts"
                ) from last_error

    # ここに到達 = 接続取得成功
    try:
        yield cursor
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn and pool_obj:
            try:
                pool_obj.putconn(conn)
            except Exception:
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
                    role_id_2 BIGINT NULL DEFAULT NULL,
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

            # 既存のテーブルに、2つ目のロール用の列を追加（任意のロール。未設定はNULL）
            cursor.execute("""
                ALTER TABLE role_invite_links
                ADD COLUMN IF NOT EXISTS role_id_2 BIGINT NULL DEFAULT NULL
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
