"""
集中式数据库连接管理 — 消除硬编码凭据，提供连接池复用
"""
import os
import pymysql
from contextlib import contextmanager
from app.config import DATABASE_URL


def _parse_db_url(url: str) -> dict:
    """从 DATABASE_URL 解析连接参数"""
    # mysql+pymysql://user:pass@host:port/db?charset=utf8mb4
    import re
    m = re.match(r'mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)', url)
    if not m:
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', '123456'),
            'database': os.getenv('DB_NAME', 'football_predict'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'charset': 'utf8mb4',
        }
    return {
        'user': m.group(1),
        'password': m.group(2),
        'host': m.group(3),
        'port': int(m.group(4)),
        'database': m.group(5),
        'charset': 'utf8mb4',
    }


_DB_PARAMS = _parse_db_url(DATABASE_URL)


def get_connection() -> pymysql.Connection:
    """获取数据库连接（调用方需自行 close）"""
    return pymysql.connect(**_DB_PARAMS)


@contextmanager
def db_cursor():
    """上下文管理器：自动关闭 cursor 和 connection"""
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()


@contextmanager
def db_connection():
    """上下文管理器：仅自动关闭 connection"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
