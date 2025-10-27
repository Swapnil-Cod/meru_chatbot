import pymysql
from pymysql.cursors import DictCursor

_db_cfg = None

def init_db(config):
    """
    Initialize global DB config ONLY - don't create connection yet.
    CRITICAL: MariaDB VIRTUAL columns corrupt PyMySQL connections, so we create
    fresh connections on-demand rather than at startup.
    """
    global _db_cfg
    _db_cfg = config

def _connect():
    """Create a new database connection using stored config."""
    return pymysql.connect(
        host=_db_cfg["host"],
        user=_db_cfg["user"],
        password=_db_cfg["password"],
        database=_db_cfg["database"],
        port=_db_cfg["port"],
        charset=_db_cfg.get("charset", "utf8mb4"),
        cursorclass=DictCursor,
        autocommit=_db_cfg.get("autocommit", True),
    )

def get_db():
    """
    Return a BRAND NEW database connection EVERY TIME.
    CRITICAL: Do NOT reuse connections - MariaDB VIRTUAL columns cause PyMySQL corruption.
    Each query must use its own fresh connection.
    """
    return _connect()
