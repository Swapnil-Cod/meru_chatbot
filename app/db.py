import pymysql
from pymysql.cursors import DictCursor
from sshtunnel import SSHTunnelForwarder

_db_cfg = None
_ssh_cfg = None
_ssh_tunnel = None

def init_db(config, ssh_config=None):
    """
    Initialize global DB config and SSH config ONLY - don't create connection yet.
    CRITICAL: MariaDB VIRTUAL columns corrupt PyMySQL connections, so we create
    fresh connections on-demand rather than at startup.
    """
    global _db_cfg, _ssh_cfg, _ssh_tunnel
    _db_cfg = config
    _ssh_cfg = ssh_config

    # Start SSH tunnel if SSH config is provided
    if _ssh_cfg and _ssh_cfg.get('ssh_host'):
        _start_ssh_tunnel()

def _start_ssh_tunnel():
    """Start SSH tunnel for remote MySQL connection."""
    global _ssh_tunnel

    if _ssh_tunnel and _ssh_tunnel.is_active:
        return  # Tunnel already active

    try:
        _ssh_tunnel = SSHTunnelForwarder(
            (_ssh_cfg['ssh_host'], _ssh_cfg['ssh_port']),
            ssh_username=_ssh_cfg['ssh_user'],
            ssh_pkey=_ssh_cfg['ssh_key_file'],
            remote_bind_address=(_db_cfg['host'], _db_cfg['port']),
        )
        _ssh_tunnel.start()
        print(f"✓ SSH Tunnel established: localhost:{_ssh_tunnel.local_bind_port} -> {_ssh_cfg['ssh_host']}:{_db_cfg['port']}")
    except Exception as e:
        print(f"✗ Failed to start SSH tunnel: {e}")
        raise

def _connect():
    """Create a new database connection using stored config."""
    # Use SSH tunnel's local port if tunnel is active
    if _ssh_tunnel and _ssh_tunnel.is_active:
        host = '127.0.0.1'
        port = _ssh_tunnel.local_bind_port
    else:
        host = _db_cfg["host"]
        port = _db_cfg["port"]

    return pymysql.connect(
        host=host,
        user=_db_cfg["user"],
        password=_db_cfg["password"],
        database=_db_cfg["database"],
        port=port,
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

def close_ssh_tunnel():
    """Close SSH tunnel if active."""
    global _ssh_tunnel
    if _ssh_tunnel and _ssh_tunnel.is_active:
        _ssh_tunnel.stop()
        print("SSH Tunnel closed")
