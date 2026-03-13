import os
import json
import argparse
import atexit
from contextlib import contextmanager
from typing import Optional, Dict, Any

from datetime import datetime

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
import pyotp

DEFAULT_SCHEMA = os.getenv("PGSCHEMA", "tacacs")
POOL_MIN_CONN = int(os.getenv("PGPOOL_MIN_CONN", "1"))
POOL_MAX_CONN = int(os.getenv("PGPOOL_MAX_CONN", "10"))

_DB_POOL: Optional[ThreadedConnectionPool] = None


# ----------------- CONNECT -----------------


def _dsn_from_env() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
        return dsn

    host = os.getenv("PGHOST", "localhost")
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE", "tacacs_db")
    user = os.getenv("PGUSER", "tacacs_pg")
    password = os.getenv("PGPASSWORD", "supersecret")

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _get_pool() -> ThreadedConnectionPool:
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = ThreadedConnectionPool(
            POOL_MIN_CONN,
            POOL_MAX_CONN,
            dsn=_dsn_from_env(),
            options=f"-c search_path={DEFAULT_SCHEMA},public",
        )
    return _DB_POOL


def _close_pool() -> None:
    global _DB_POOL
    if _DB_POOL is not None:
        _DB_POOL.closeall()
        _DB_POOL = None


atexit.register(_close_pool)


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ----------------- USERS -----------------


def user_put(
    username: str,
    password_hash: str,
    full_name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, full_name, description, is_active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              full_name     = EXCLUDED.full_name,
              description   = EXCLUDED.description,
              is_active     = EXCLUDED.is_active
            RETURNING *
            """,
            (username, password_hash, full_name, description, is_active),
        )
        row = cur.fetchone()
        return {"success": True, "user": row}


def user_get(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"User '{username}' not found"}
        return {"success": True, "user": row}


def user_delete(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s RETURNING user_id", (username,))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def user_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users ORDER BY username")
        return {"success": True, "data": cur.fetchall()}


# ----------------- USER_GROUP_MEMBERS -----------------


def usergroup_member_add(username: str, group_name: str, ro_rw: int = 0) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Device group '{group_name}' not found"}

        cur.execute(
            """
            INSERT INTO user_group_members (user_id, group_id, ro_rw)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, group_id)
            DO UPDATE SET ro_rw = EXCLUDED.ro_rw
            RETURNING *
            """,
            (u["user_id"], g["group_id"], ro_rw),
        )
        row = cur.fetchone()
        return {"success": True, "member": row}


def usergroup_member_remove(username: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Device group '{group_name}' not found"}

        user_id = u[0] if isinstance(u, tuple) else u["user_id"]
        group_id = g[0] if isinstance(g, tuple) else g["group_id"]

        cur.execute(
            "DELETE FROM user_group_members WHERE user_id = %s AND group_id = %s RETURNING user_id",
            (user_id, group_id),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def usergroup_member_list(username: Optional[str] = None, group_name: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if username:
            cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            u = cur.fetchone()
            if not u:
                return {"success": False, "error": f"User '{username}' not found"}
            cur.execute(
                """
                SELECT u.username, ug.group_name, m.ro_rw
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN device_groups ug ON ug.group_id = m.group_id
                WHERE m.user_id = %s
                ORDER BY ug.group_name
                """,
                (u["user_id"],),
            )
        elif group_name:
            cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
            g = cur.fetchone()
            if not g:
                return {"success": False, "error": f"Device group '{group_name}' not found"}
            cur.execute(
                """
                SELECT u.username, ug.group_name, m.ro_rw
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN device_groups ug ON ug.group_id = m.group_id
                WHERE m.group_id = %s
                ORDER BY u.username
                """,
                (g["group_id"],),
            )
        else:
            cur.execute(
                """
                SELECT u.username, ug.group_name, m.ro_rw
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN device_groups ug ON ug.group_id = m.group_id
                ORDER BY u.username, ug.group_name
                """
            )
        rows = cur.fetchall()

    normalized: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("group_name") or "")
        if name.lower().endswith("_ro"):
            base_name = name[:-3]
            mode = 0
        elif name.lower().endswith("_rw"):
            base_name = name[:-3]
            mode = 1
        else:
            base_name = name
            mode = int(row.get("ro_rw") or 0)

        normalized.append(
            {
                "username": row.get("username"),
                "group_name": base_name,
                "ro_rw": mode,
            }
        )

    return {"success": True, "data": normalized}


# ----------------- VENDORS -----------------


def vendor_put(vendor_name: str, description: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO vendors (vendor_name, description)
            VALUES (%s, %s)
            ON CONFLICT (vendor_name)
            DO UPDATE SET description = EXCLUDED.description
            RETURNING *
            """,
            (vendor_name, description),
        )
        return {"success": True, "vendor": cur.fetchone()}


def vendor_get(vendor_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM vendors WHERE vendor_name = %s", (vendor_name,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Vendor '{vendor_name}' not found"}
        return {"success": True, "vendor": row}


def vendor_delete(vendor_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM vendors WHERE vendor_name = %s RETURNING vendor_id", (vendor_name,))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def vendor_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM vendors ORDER BY vendor_name")
        return {"success": True, "data": cur.fetchall()}


# ----------------- DEVICES -----------------


def _resolve_vendor_id(cur, vendor_name: Optional[str]) -> Optional[int]:
    name = (vendor_name or "").strip()
    if not name:
        return None

    cur.execute("SELECT vendor_id FROM vendors WHERE vendor_name = %s", (name,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Vendor '{name}' not found")
    return row["vendor_id"]


def device_put(
    ip_address: str,
    tacacs_key: str,
    hostname: Optional[str] = None,
    description: Optional[str] = None,
    vendor_name: Optional[str] = None,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            vendor_id = _resolve_vendor_id(cur, vendor_name)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        cur.execute(
            """
            INSERT INTO devices (hostname, ip_address, tacacs_key, description, vendor_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (ip_address)
            DO UPDATE SET
              hostname   = EXCLUDED.hostname,
              tacacs_key = EXCLUDED.tacacs_key,
              description= EXCLUDED.description,
              vendor_id  = EXCLUDED.vendor_id
            RETURNING *
            """,
            (hostname, ip_address, tacacs_key, description, vendor_id),
        )
        device = cur.fetchone()

        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            WHERE d.device_id = %s
            """,
            (device["device_id"],),
        )
        return {"success": True, "device": cur.fetchone()}


def device_create(
    ip_address: str,
    tacacs_key: str,
    hostname: Optional[str] = None,
    description: Optional[str] = None,
    vendor_name: Optional[str] = None,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            vendor_id = _resolve_vendor_id(cur, vendor_name)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        cur.execute(
            """
            INSERT INTO devices (hostname, ip_address, tacacs_key, description, vendor_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (ip_address) DO NOTHING
            RETURNING *
            """,
            (hostname, ip_address, tacacs_key, description, vendor_id),
        )
        device = cur.fetchone()
        if not device:
            return {"success": False, "error": f"Device with IP '{ip_address}' already exists"}

        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            WHERE d.device_id = %s
            """,
            (device["device_id"],),
        )
        return {"success": True, "device": cur.fetchone()}


def device_get_ip(ip_address: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            WHERE d.ip_address = %s
            """,
            (ip_address,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Device with IP '{ip_address}' not found"}
        return {"success": True, "device": row}


def device_get_name(hostname: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            WHERE d.hostname = %s
            """,
            (hostname,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Device '{hostname}' not found"}
        return {"success": True, "device": row}


def device_delete(ip_address: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM devices WHERE ip_address = %s RETURNING device_id",
            (ip_address,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def device_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            ORDER BY d.hostname NULLS LAST, d.ip_address
            """
        )
        return {"success": True, "data": cur.fetchall()}


def device_update(
    current_ip_address: str,
    new_ip_address: str,
    tacacs_key: str,
    hostname: Optional[str] = None,
    description: Optional[str] = None,
    vendor_name: Optional[str] = None,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT device_id FROM devices WHERE ip_address = %s", (current_ip_address,))
        existing = cur.fetchone()
        if not existing:
            return {"success": False, "error": f"Device with IP '{current_ip_address}' not found"}

        try:
            vendor_id = _resolve_vendor_id(cur, vendor_name)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        if new_ip_address != current_ip_address:
            cur.execute("SELECT device_id FROM devices WHERE ip_address = %s", (new_ip_address,))
            conflict = cur.fetchone()
            if conflict:
                return {"success": False, "error": f"Device with IP '{new_ip_address}' already exists"}

        cur.execute(
            """
            UPDATE devices
            SET ip_address = %s,
                tacacs_key = %s,
                hostname = %s,
                description = %s,
                vendor_id = %s
            WHERE device_id = %s
            RETURNING *
            """,
            (
                new_ip_address,
                tacacs_key,
                hostname,
                description,
                vendor_id,
                existing["device_id"],
            ),
        )
        updated = cur.fetchone()

        cur.execute(
            """
            SELECT d.*, v.vendor_name
            FROM devices d
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            WHERE d.device_id = %s
            """,
            (updated["device_id"],),
        )
        return {"success": True, "device": cur.fetchone()}


# ----------------- DEVICE GROUPS -----------------


def devicegroup_put(
    group_name: str,
    tacacs_key: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO device_groups (group_name, tacacs_key, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (group_name)
            DO UPDATE SET
              tacacs_key = EXCLUDED.tacacs_key,
              description = EXCLUDED.description
            RETURNING *
            """,
            (group_name, tacacs_key, description),
        )
        return {"success": True, "group": cur.fetchone()}


def devicegroup_get(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM device_groups WHERE group_name = %s", (group_name,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Device group '{group_name}' not found"}
        return {"success": True, "group": row}


def devicegroup_delete(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM device_groups WHERE group_name = %s RETURNING group_id",
            (group_name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def devicegroup_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM device_groups ORDER BY group_name")
        return {"success": True, "data": cur.fetchall()}


# ----------------- DEVICE_GROUP_MEMBERS -----------------


def devicegroup_member_add(ip_address: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT device_id FROM devices WHERE ip_address = %s", (ip_address,))
        d = cur.fetchone()
        if not d:
            return {"success": False, "error": f"Device with IP '{ip_address}' not found"}

        cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Device group '{group_name}' not found"}

        cur.execute(
            """
            INSERT INTO device_group_members (device_id, group_id)
            VALUES (%s, %s)
            ON CONFLICT (device_id, group_id) DO NOTHING
            RETURNING *
            """,
            (d["device_id"], g["group_id"]),
        )
        return {"success": True, "member": cur.fetchone()}


def devicegroup_member_remove(ip_address: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT device_id FROM devices WHERE ip_address = %s", (ip_address,))
        d = cur.fetchone()
        if not d:
            return {"success": False, "error": f"Device with IP '{ip_address}' not found"}

        cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Device group '{group_name}' not found"}

        device_id = d[0] if isinstance(d, tuple) else d["device_id"]
        group_id = g[0] if isinstance(g, tuple) else g["group_id"]

        cur.execute(
            "DELETE FROM device_group_members WHERE device_id = %s AND group_id = %s RETURNING device_id",
            (device_id, group_id),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def devicegroup_member_list(ip_address: Optional[str] = None, group_name: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if ip_address:
            cur.execute("SELECT device_id FROM devices WHERE ip_address = %s", (ip_address,))
            d = cur.fetchone()
            if not d:
                return {"success": False, "error": f"Device with IP '{ip_address}' not found"}
            cur.execute(
                """
                SELECT d.ip_address, dg.group_name
                FROM device_group_members m
                JOIN devices d ON d.device_id = m.device_id
                JOIN device_groups dg ON dg.group_id = m.group_id
                WHERE m.device_id = %s
                ORDER BY dg.group_name
                """,
                (d["device_id"],),
            )
        elif group_name:
            cur.execute("SELECT group_id FROM device_groups WHERE group_name = %s", (group_name,))
            g = cur.fetchone()
            if not g:
                return {"success": False, "error": f"Device group '{group_name}' not found"}
            cur.execute(
                """
                SELECT d.ip_address, dg.group_name
                FROM device_group_members m
                JOIN devices d ON d.device_id = m.device_id
                JOIN device_groups dg ON dg.group_id = m.group_id
                WHERE m.group_id = %s
                ORDER BY d.ip_address
                """,
                (g["group_id"],),
            )
        else:
            cur.execute(
                """
                SELECT d.ip_address, dg.group_name
                FROM device_group_members m
                JOIN devices d ON d.device_id = m.device_id
                JOIN device_groups dg ON dg.group_id = m.group_id
                ORDER BY d.ip_address, dg.group_name
                """
            )
        return {"success": True, "data": cur.fetchall()}


# ----------------- USER TOTP -----------------


def totp_put(
    username: str,
    issuer: str = "tacacs-plus",
    digits: int = 6,
    period: int = 30,
    is_enabled: bool = True,
) -> Dict[str, Any]:
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret, digits=digits, interval=period)
    otp_uri = totp.provisioning_uri(name=username, issuer_name=issuer)

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id, is_active FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}
        if not u["is_active"]:
            return {"success": False, "error": "user is inactive"}

        cur.execute(
            """
            INSERT INTO user_totp (user_id, totp_secret, is_enabled)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
              totp_secret = EXCLUDED.totp_secret,
              is_enabled  = EXCLUDED.is_enabled
            RETURNING *
            """,
            (u["user_id"], secret, is_enabled),
        )
        row = cur.fetchone()

    return {
        "success": True,
        "totp": row,
        "secret": secret,
        "otp_uri": otp_uri,
    }


def totp_get(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT * FROM user_totp WHERE user_id = %s", (u["user_id"],))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "TOTP profile not found"}
        return {"success": True, "totp": row}


def totp_disable(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute(
            """
            UPDATE user_totp
            SET is_enabled = FALSE
            WHERE user_id = %s
            RETURNING *
            """,
            (u["user_id"],),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "TOTP profile not found"}
        return {"success": True, "totp": row}


def totp_delete(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        user_id = u[0] if isinstance(u, tuple) else u["user_id"]
        cur.execute("DELETE FROM user_totp WHERE user_id = %s RETURNING user_id", (user_id,))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def verify_totp_for_user(
    username: str,
    token: str,
    digits: int = 6,
    period: int = 30,
    valid_window: int = 1,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id, is_active FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "verified": False, "reason": f"user '{username}' not found"}

        if not u["is_active"]:
            return {"success": False, "verified": False, "reason": "user is inactive"}

        cur.execute("SELECT * FROM user_totp WHERE user_id = %s", (u["user_id"],))
        tf = cur.fetchone()
        if not tf:
            return {"success": False, "verified": False, "reason": "TOTP profile not found"}

        if not tf["is_enabled"]:
            return {"success": False, "verified": False, "reason": "TOTP is disabled"}

        secret = tf["totp_secret"]
        if not secret:
            return {"success": False, "verified": False, "reason": "empty TOTP secret"}

        totp = pyotp.TOTP(secret, digits=digits, interval=period)
        ok = totp.verify(token, valid_window=valid_window)

        if not ok:
            return {"success": True, "verified": False, "reason": "invalid token"}

        cur.execute(
            "UPDATE user_totp SET last_used_at = %s WHERE user_id = %s",
            (datetime.utcnow(), u["user_id"]),
        )

        return {"success": True, "verified": True, "reason": "ok"}


# ----------------- PROFILES -----------------


def profile_put(
    profile_name: str,
    profile_body: str,
    description: Optional[str] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO profiles (profile_name, profile_body, description, is_active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (profile_name)
            DO UPDATE SET
              profile_body = EXCLUDED.profile_body,
              description  = EXCLUDED.description,
              is_active    = EXCLUDED.is_active
            RETURNING *
            """,
            (profile_name, profile_body, description, is_active),
        )
        return {"success": True, "profile": cur.fetchone()}


def profile_get(profile_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM profiles WHERE profile_name = %s", (profile_name,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Profile '{profile_name}' not found"}
        return {"success": True, "profile": row}


def profile_delete(profile_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM profiles WHERE profile_name = %s RETURNING profile_id",
            (profile_name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def profile_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM profiles ORDER BY profile_name")
        return {"success": True, "data": cur.fetchall()}


# ----------------- USER_PROFILE_MEMBERS -----------------


def userprofile_member_add(username: str, profile_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT profile_id FROM profiles WHERE profile_name = %s", (profile_name,))
        p = cur.fetchone()
        if not p:
            return {"success": False, "error": f"Profile '{profile_name}' not found"}

        cur.execute(
            """
            INSERT INTO user_profile_members (user_id, profile_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, profile_id) DO NOTHING
            RETURNING *
            """,
            (u["user_id"], p["profile_id"]),
        )
        return {"success": True, "member": cur.fetchone()}


def userprofile_member_remove(username: str, profile_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT profile_id FROM profiles WHERE profile_name = %s", (profile_name,))
        p = cur.fetchone()
        if not p:
            return {"success": False, "error": f"Profile '{profile_name}' not found"}

        user_id = u[0] if isinstance(u, tuple) else u["user_id"]
        profile_id = p[0] if isinstance(p, tuple) else p["profile_id"]

        cur.execute(
            "DELETE FROM user_profile_members WHERE user_id = %s AND profile_id = %s RETURNING user_id",
            (user_id, profile_id),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def userprofile_member_list(username: Optional[str] = None, profile_name: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if username:
            cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            u = cur.fetchone()
            if not u:
                return {"success": False, "error": f"User '{username}' not found"}
            cur.execute(
                """
                SELECT u.username, p.profile_name
                FROM user_profile_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN profiles p ON p.profile_id = m.profile_id
                WHERE m.user_id = %s
                ORDER BY p.profile_name
                """,
                (u["user_id"],),
            )
        elif profile_name:
            cur.execute("SELECT profile_id FROM profiles WHERE profile_name = %s", (profile_name,))
            p = cur.fetchone()
            if not p:
                return {"success": False, "error": f"Profile '{profile_name}' not found"}
            cur.execute(
                """
                SELECT u.username, p.profile_name
                FROM user_profile_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN profiles p ON p.profile_id = m.profile_id
                WHERE m.profile_id = %s
                ORDER BY u.username
                """,
                (p["profile_id"],),
            )
        else:
            cur.execute(
                """
                SELECT u.username, p.profile_name
                FROM user_profile_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN profiles p ON p.profile_id = m.profile_id
                ORDER BY u.username, p.profile_name
                """
            )
        return {"success": True, "data": cur.fetchall()}


# ----------------- CLI -----------------


def main():
    p = argparse.ArgumentParser(description="Tacacs DB helper (new schema)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # USERS
    ug = sub.add_parser("user-get")
    ug.add_argument("username")

    up = sub.add_parser("user-put")
    up.add_argument("username")
    up.add_argument("password_hash")
    up.add_argument("--full-name")
    up.add_argument("--description")
    up.add_argument("--is-active", type=lambda x: x.lower() == "true", default=True)

    ud = sub.add_parser("user-delete")
    ud.add_argument("username")

    sub.add_parser("user-list")

    # USER GROUP MEMBERS
    ugma = sub.add_parser("usergroup-member-add")
    ugma.add_argument("username")
    ugma.add_argument("group_name")
    ugma.add_argument("--ro-rw", type=int, choices=[0, 1], default=0)

    ugmr = sub.add_parser("usergroup-member-remove")
    ugmr.add_argument("username")
    ugmr.add_argument("group_name")

    ugml = sub.add_parser("usergroup-member-list")
    ugml.add_argument("--username")
    ugml.add_argument("--group_name")

    # VENDORS
    vg = sub.add_parser("vendor-get")
    vg.add_argument("vendor_name")

    vp = sub.add_parser("vendor-put")
    vp.add_argument("vendor_name")
    vp.add_argument("--description")

    vd = sub.add_parser("vendor-delete")
    vd.add_argument("vendor_name")

    sub.add_parser("vendor-list")

    # DEVICES
    dp = sub.add_parser("device-put")
    dp.add_argument("ip_address")
    dp.add_argument("tacacs_key")
    dp.add_argument("--hostname")
    dp.add_argument("--vendor-name")
    dp.add_argument("--description")

    dgi = sub.add_parser("device-get-ip")
    dgi.add_argument("ip_address")

    dgn = sub.add_parser("device-get-name")
    dgn.add_argument("hostname")

    dd = sub.add_parser("device-delete")
    dd.add_argument("ip_address")

    sub.add_parser("device-list")

    # DEVICE GROUPS
    dgg = sub.add_parser("devicegroup-get")
    dgg.add_argument("group_name")

    dgp = sub.add_parser("devicegroup-put")
    dgp.add_argument("group_name")
    dgp.add_argument("--tacacs-key")
    dgp.add_argument("--description")

    dgd = sub.add_parser("devicegroup-delete")
    dgd.add_argument("group_name")

    sub.add_parser("devicegroup-list")

    # DEVICE GROUP MEMBERS
    dgma = sub.add_parser("devicegroup-member-add")
    dgma.add_argument("ip_address")
    dgma.add_argument("group_name")

    dgmrem = sub.add_parser("devicegroup-member-remove")
    dgmrem.add_argument("ip_address")
    dgmrem.add_argument("group_name")

    dgml = sub.add_parser("devicegroup-member-list")
    dgml.add_argument("--ip_address")
    dgml.add_argument("--group_name")

    # TOTP
    tfp = sub.add_parser("totp-put")
    tfp.add_argument("username")
    tfp.add_argument("--issuer", default="tacacs-plus")
    tfp.add_argument("--digits", type=int, default=6)
    tfp.add_argument("--period", type=int, default=30)
    tfp.add_argument("--is-enabled", type=lambda x: x.lower() == "true", default=True)

    tfg = sub.add_parser("totp-get")
    tfg.add_argument("username")

    tfd = sub.add_parser("totp-disable")
    tfd.add_argument("username")

    tfr = sub.add_parser("totp-delete")
    tfr.add_argument("username")

    tfv = sub.add_parser("totp-verify")
    tfv.add_argument("username")
    tfv.add_argument("token")
    tfv.add_argument("--digits", type=int, default=6)
    tfv.add_argument("--period", type=int, default=30)
    tfv.add_argument("--window", type=int, default=1)

    # PROFILES
    prg = sub.add_parser("profile-get")
    prg.add_argument("profile_name")

    prp = sub.add_parser("profile-put")
    prp.add_argument("profile_name")
    prp.add_argument("profile_body")
    prp.add_argument("--description")
    prp.add_argument("--is-active", type=lambda x: x.lower() == "true", default=True)

    prd = sub.add_parser("profile-delete")
    prd.add_argument("profile_name")

    sub.add_parser("profile-list")

    # USER PROFILE MEMBERS
    upma = sub.add_parser("userprofile-member-add")
    upma.add_argument("username")
    upma.add_argument("profile_name")

    upmr = sub.add_parser("userprofile-member-remove")
    upmr.add_argument("username")
    upmr.add_argument("profile_name")

    upml = sub.add_parser("userprofile-member-list")
    upml.add_argument("--username")
    upml.add_argument("--profile_name")

    args = p.parse_args()

    if args.cmd == "user-get":
        out = user_get(args.username)
    elif args.cmd == "user-put":
        out = user_put(args.username, args.password_hash, args.full_name, args.description, args.is_active)
    elif args.cmd == "user-delete":
        out = user_delete(args.username)
    elif args.cmd == "user-list":
        out = user_list()

    elif args.cmd == "usergroup-member-add":
        out = usergroup_member_add(args.username, args.group_name, args.ro_rw)
    elif args.cmd == "usergroup-member-remove":
        out = usergroup_member_remove(args.username, args.group_name)
    elif args.cmd == "usergroup-member-list":
        out = usergroup_member_list(args.username, args.group_name)

    elif args.cmd == "vendor-get":
        out = vendor_get(args.vendor_name)
    elif args.cmd == "vendor-put":
        out = vendor_put(args.vendor_name, args.description)
    elif args.cmd == "vendor-delete":
        out = vendor_delete(args.vendor_name)
    elif args.cmd == "vendor-list":
        out = vendor_list()

    elif args.cmd == "device-put":
        out = device_put(args.ip_address, args.tacacs_key, args.hostname, args.description, args.vendor_name)
    elif args.cmd == "device-get-ip":
        out = device_get_ip(args.ip_address)
    elif args.cmd == "device-get-name":
        out = device_get_name(args.hostname)
    elif args.cmd == "device-delete":
        out = device_delete(args.ip_address)
    elif args.cmd == "device-list":
        out = device_list()

    elif args.cmd == "devicegroup-get":
        out = devicegroup_get(args.group_name)
    elif args.cmd == "devicegroup-put":
        out = devicegroup_put(args.group_name, args.tacacs_key, args.description)
    elif args.cmd == "devicegroup-delete":
        out = devicegroup_delete(args.group_name)
    elif args.cmd == "devicegroup-list":
        out = devicegroup_list()

    elif args.cmd == "devicegroup-member-add":
        out = devicegroup_member_add(args.ip_address, args.group_name)
    elif args.cmd == "devicegroup-member-remove":
        out = devicegroup_member_remove(args.ip_address, args.group_name)
    elif args.cmd == "devicegroup-member-list":
        out = devicegroup_member_list(args.ip_address, args.group_name)

    elif args.cmd == "totp-put":
        out = totp_put(
            args.username,
            issuer=args.issuer,
            digits=args.digits,
            period=args.period,
            is_enabled=args.is_enabled,
        )
    elif args.cmd == "totp-get":
        out = totp_get(args.username)
    elif args.cmd == "totp-disable":
        out = totp_disable(args.username)
    elif args.cmd == "totp-delete":
        out = totp_delete(args.username)
    elif args.cmd == "totp-verify":
        out = verify_totp_for_user(
            args.username,
            args.token,
            digits=args.digits,
            period=args.period,
            valid_window=args.window,
        )

    elif args.cmd == "profile-get":
        out = profile_get(args.profile_name)
    elif args.cmd == "profile-put":
        out = profile_put(
            args.profile_name,
            args.profile_body,
            description=args.description,
            is_active=args.is_active,
        )
    elif args.cmd == "profile-delete":
        out = profile_delete(args.profile_name)
    elif args.cmd == "profile-list":
        out = profile_list()

    elif args.cmd == "userprofile-member-add":
        out = userprofile_member_add(args.username, args.profile_name)
    elif args.cmd == "userprofile-member-remove":
        out = userprofile_member_remove(args.username, args.profile_name)
    elif args.cmd == "userprofile-member-list":
        out = userprofile_member_list(args.username, args.profile_name)

    else:
        out = {"success": False, "error": "unknown command"}

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
