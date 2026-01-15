import os
import json
import argparse
from typing import Optional, Dict, Any

from datetime import datetime

import psycopg2
import psycopg2.extras
import pyotp

DEFAULT_SCHEMA = os.getenv("PGSCHEMA", "tacacs")

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


def get_conn():
    return psycopg2.connect(
        _dsn_from_env(),
        options=f"-c search_path={DEFAULT_SCHEMA},public",
    )


# ----------------- USERS -----------------


def user_put(
    username: str,
    password_hash: str,
    full_name: Optional[str] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    """
    Создать/обновить пользователя.
    password_hash сюда приходит уже готовым (хэш/cleartext — решаешь снаружи).
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, full_name, is_active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET
              password_hash = EXCLUDED.password_hash,
              full_name     = EXCLUDED.full_name,
              is_active     = EXCLUDED.is_active
            RETURNING *
            """,
            (username, password_hash, full_name, is_active),
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


# ----------------- USER GROUPS -----------------


def usergroup_put(group_name: str, description: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_groups (group_name, description)
            VALUES (%s, %s)
            ON CONFLICT (group_name)
            DO UPDATE SET description = EXCLUDED.description
            RETURNING *
            """,
            (group_name, description),
        )
        return {"success": True, "group": cur.fetchone()}


def usergroup_get(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM user_groups WHERE group_name = %s", (group_name,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"User group '{group_name}' not found"}
        return {"success": True, "group": row}


def usergroup_delete(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_groups WHERE group_name = %s RETURNING group_id",
            (group_name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def usergroup_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM user_groups ORDER BY group_name")
        return {"success": True, "data": cur.fetchall()}


# ----------------- USER_GROUP_MEMBERS -----------------


def usergroup_member_add(username: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT group_id FROM user_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"User group '{group_name}' not found"}

        cur.execute(
            """
            INSERT INTO user_group_members (user_id, group_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, group_id) DO NOTHING
            RETURNING *
            """,
            (u["user_id"], g["group_id"]),
        )
        row = cur.fetchone()
        return {"success": True, "member": row}


def usergroup_member_remove(username: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute("SELECT group_id FROM user_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"User group '{group_name}' not found"}

        cur.execute(
            "DELETE FROM user_group_members WHERE user_id = %s AND group_id = %s RETURNING user_id",
            (u["user_id"], g["group_id"]),
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
                SELECT u.username, ug.group_name
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN user_groups ug ON ug.group_id = m.group_id
                WHERE m.user_id = %s
                ORDER BY ug.group_name
                """,
                (u["user_id"],),
            )
        elif group_name:
            cur.execute("SELECT group_id FROM user_groups WHERE group_name = %s", (group_name,))
            g = cur.fetchone()
            if not g:
                return {"success": False, "error": f"User group '{group_name}' not found"}
            cur.execute(
                """
                SELECT u.username, ug.group_name
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN user_groups ug ON ug.group_id = m.group_id
                WHERE m.group_id = %s
                ORDER BY u.username
                """,
                (g["group_id"],),
            )
        else:
            cur.execute(
                """
                SELECT u.username, ug.group_name
                FROM user_group_members m
                JOIN users u ON u.user_id = m.user_id
                JOIN user_groups ug ON ug.group_id = m.group_id
                ORDER BY u.username, ug.group_name
                """
            )
        return {"success": True, "data": cur.fetchall()}


# ----------------- HOSTS -----------------


def host_put(
    ip_address: str,
    tacacs_key: str,
    hostname: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создать/обновить хост по IP.
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO hosts (hostname, ip_address, tacacs_key, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ip_address)
            DO UPDATE SET
              hostname   = EXCLUDED.hostname,
              tacacs_key = EXCLUDED.tacacs_key,
              description= EXCLUDED.description
            RETURNING *
            """,
            (hostname, ip_address, tacacs_key, description),
        )
        return {"success": True, "host": cur.fetchone()}


def host_get_ip(ip_address: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM hosts WHERE ip_address = %s", (ip_address,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Host with IP '{ip_address}' not found"}
        return {"success": True, "host": row}


def host_get_name(hostname: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM hosts WHERE hostname = %s", (hostname,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Host '{hostname}' not found"}
        return {"success": True, "host": row}


def host_delete(ip_address: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM hosts WHERE ip_address = %s RETURNING host_id",
            (ip_address,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def host_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM hosts ORDER BY hostname NULLS LAST, ip_address")
        return {"success": True, "data": cur.fetchall()}


# ----------------- HOST GROUPS -----------------


def hostgroup_put(group_name: str, description: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO host_groups (group_name, description)
            VALUES (%s, %s)
            ON CONFLICT (group_name)
            DO UPDATE SET description = EXCLUDED.description
            RETURNING *
            """,
            (group_name, description),
        )
        return {"success": True, "group": cur.fetchone()}


def hostgroup_get(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM host_groups WHERE group_name = %s", (group_name,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Host group '{group_name}' not found"}
        return {"success": True, "group": row}


def hostgroup_delete(group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM host_groups WHERE group_name = %s RETURNING group_id",
            (group_name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def hostgroup_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM host_groups ORDER BY group_name")
        return {"success": True, "data": cur.fetchall()}


# ----------------- HOST_GROUP_MEMBERS -----------------


def hostgroup_member_add(ip_address: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT host_id FROM hosts WHERE ip_address = %s", (ip_address,))
        h = cur.fetchone()
        if not h:
            return {"success": False, "error": f"Host with IP '{ip_address}' not found"}

        cur.execute("SELECT group_id FROM host_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Host group '{group_name}' not found"}

        cur.execute(
            """
            INSERT INTO host_group_members (host_id, group_id)
            VALUES (%s, %s)
            ON CONFLICT (host_id, group_id) DO NOTHING
            RETURNING *
            """,
            (h["host_id"], g["group_id"]),
        )
        return {"success": True, "member": cur.fetchone()}


def hostgroup_member_remove(ip_address: str, group_name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT host_id FROM hosts WHERE ip_address = %s", (ip_address,))
        h = cur.fetchone()
        if not h:
            return {"success": False, "error": f"Host with IP '{ip_address}' not found"}

        cur.execute("SELECT group_id FROM host_groups WHERE group_name = %s", (group_name,))
        g = cur.fetchone()
        if not g:
            return {"success": False, "error": f"Host group '{group_name}' not found"}

        cur.execute(
            "DELETE FROM host_group_members WHERE host_id = %s AND group_id = %s RETURNING host_id",
            (h["host_id"], g["group_id"]),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def hostgroup_member_list(ip_address: Optional[str] = None, group_name: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if ip_address:
            cur.execute("SELECT host_id FROM hosts WHERE ip_address = %s", (ip_address,))
            h = cur.fetchone()
            if not h:
                return {"success": False, "error": f"Host with IP '{ip_address}' not found"}
            cur.execute(
                """
                SELECT h.ip_address, hg.group_name
                FROM host_group_members m
                JOIN hosts h ON h.host_id = m.host_id
                JOIN host_groups hg ON hg.group_id = m.group_id
                WHERE m.host_id = %s
                ORDER BY hg.group_name
                """,
                (h["host_id"],),
            )
        elif group_name:
            cur.execute("SELECT group_id FROM host_groups WHERE group_name = %s", (group_name,))
            g = cur.fetchone()
            if not g:
                return {"success": False, "error": f"Host group '{group_name}' not found"}
            cur.execute(
                """
                SELECT h.ip_address, hg.group_name
                FROM host_group_members m
                JOIN hosts h ON h.host_id = m.host_id
                JOIN host_groups hg ON hg.group_id = m.group_id
                WHERE m.group_id = %s
                ORDER BY h.ip_address
                """,
                (g["group_id"],),
            )
        else:
            cur.execute(
                """
                SELECT h.ip_address, hg.group_name
                FROM host_group_members m
                JOIN hosts h ON h.host_id = m.host_id
                JOIN host_groups hg ON hg.group_id = m.group_id
                ORDER BY h.ip_address, hg.group_name
                """
            )
        return {"success": True, "data": cur.fetchall()}


# ----------------- ACCESS POLICIES -----------------


def policy_put(
    user_group_name: str,
    host_group_name: str,
    priv_lvl: int = 1,
    allow_access: bool = True,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT group_id FROM user_groups WHERE group_name = %s", (user_group_name,))
        ug = cur.fetchone()
        if not ug:
            return {"success": False, "error": f"User group '{user_group_name}' not found"}

        cur.execute("SELECT group_id FROM host_groups WHERE group_name = %s", (host_group_name,))
        hg = cur.fetchone()
        if not hg:
            return {"success": False, "error": f"Host group '{host_group_name}' not found"}

        cur.execute(
            """
            INSERT INTO access_policies (user_group_id, host_group_id, priv_lvl, allow_access)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_group_id, host_group_id)
            DO UPDATE SET
              priv_lvl    = EXCLUDED.priv_lvl,
              allow_access= EXCLUDED.allow_access
            RETURNING *
            """,
            (ug["group_id"], hg["group_id"], priv_lvl, allow_access),
        )
        return {"success": True, "policy": cur.fetchone()}


def policy_get(policy_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM access_policies WHERE policy_id = %s", (policy_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Policy {policy_id} not found"}
        return {"success": True, "policy": row}


def policy_delete(policy_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM access_policies WHERE policy_id = %s RETURNING policy_id", (policy_id,))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def policy_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ap.*, ug.group_name AS user_group_name, hg.group_name AS host_group_name
            FROM access_policies ap
            JOIN user_groups ug ON ug.group_id = ap.user_group_id
            JOIN host_groups hg ON hg.group_id = ap.host_group_id
            ORDER BY ug.group_name, hg.group_name
            """
        )
        return {"success": True, "data": cur.fetchall()}


# ----------------- COMMAND RULES -----------------


def cmdrule_put(policy_id: int, command_pattern: str, action: str = "PERMIT") -> Dict[str, Any]:
    action = action.upper()
    if action not in ("PERMIT", "DENY"):
        return {"success": False, "error": "action must be PERMIT or DENY"}

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT policy_id FROM access_policies WHERE policy_id = %s", (policy_id,))
        if not cur.fetchone():
            return {"success": False, "error": f"Policy {policy_id} not found"}

        cur.execute(
            """
            INSERT INTO command_rules (policy_id, command_pattern, action)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (policy_id, command_pattern, action),
        )
        return {"success": True, "rule": cur.fetchone()}


def cmdrule_get(rule_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM command_rules WHERE rule_id = %s", (rule_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Rule {rule_id} not found"}
        return {"success": True, "rule": row}


def cmdrule_delete(rule_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM command_rules WHERE rule_id = %s RETURNING rule_id", (rule_id,))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def cmdrule_list(policy_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM command_rules WHERE policy_id = %s ORDER BY rule_id",
            (policy_id,),
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
    """
    Генерирует TOTP secret, пишет его в user_totp и возвращает secret + otp_uri.
    """
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

        cur.execute("DELETE FROM user_totp WHERE user_id = %s RETURNING user_id", (u["user_id"],))
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def verify_totp_for_user(
    username: str,
    token: str,
    digits: int = 6,
    period: int = 30,
    valid_window: int = 1,
) -> Dict[str, Any]:
    """
    Проверка TOTP-кода для пользователя.
    valid_window = 1 позволяет +/- один шаг времени.
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # user
        cur.execute("SELECT user_id, is_active FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "verified": False, "reason": f"user '{username}' not found"}

        if not u["is_active"]:
            return {"success": False, "verified": False, "reason": "user is inactive"}

        # TOTP profile
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

        # запишем время успешного использования
        cur.execute(
            "UPDATE user_totp SET last_used_at = %s WHERE user_id = %s",
            (datetime.utcnow(), u["user_id"]),
        )

        return {"success": True, "verified": True, "reason": "ok"}


# ----------------- HOSTS ACCESSIBLE BY USER -----------------


def user_hosts(username: str) -> Dict[str, Any]:
    """
    Вернуть список хостов, к которым пользователь имеет доступ:
      users -> user_group_members -> access_policies -> host_group_members -> hosts
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute(
            """
            SELECT DISTINCT h.*
            FROM user_group_members ugm
            JOIN access_policies ap
              ON ap.user_group_id = ugm.group_id
             AND ap.allow_access = TRUE
            JOIN host_group_members hgm
              ON hgm.group_id = ap.host_group_id
            JOIN hosts h
              ON h.host_id = hgm.host_id
            WHERE ugm.user_id = %s
            ORDER BY h.hostname NULLS LAST, h.ip_address
            """,
            (u["user_id"],),
        )
        return {"success": True, "data": cur.fetchall()}


# ----------------- CLI -----------------


def main():
    p = argparse.ArgumentParser(description="Tacacs DB helper (новая схема)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # USERS
    ug = sub.add_parser("user-get")
    ug.add_argument("username")

    up = sub.add_parser("user-put")
    up.add_argument("username")
    up.add_argument("password_hash")
    up.add_argument("--full-name")
    up.add_argument("--is-active", type=lambda x: x.lower() == "true", default=True)

    ud = sub.add_parser("user-delete")
    ud.add_argument("username")

    sub.add_parser("user-list")

    # USER GROUPS
    ugg = sub.add_parser("usergroup-get")
    ugg.add_argument("group_name")

    ugp = sub.add_parser("usergroup-put")
    ugp.add_argument("group_name")
    ugp.add_argument("--description")

    ugd = sub.add_parser("usergroup-delete")
    ugd.add_argument("group_name")

    sub.add_parser("usergroup-list")

    # USER GROUP MEMBERS
    ugma = sub.add_parser("usergroup-member-add")
    ugma.add_argument("username")
    ugma.add_argument("group_name")

    ugmr = sub.add_parser("usergroup-member-remove")
    ugmr.add_argument("username")
    ugmr.add_argument("group_name")

    ugml = sub.add_parser("usergroup-member-list")
    ugml.add_argument("--username")
    ugml.add_argument("--group_name")

    # HOSTS
    hp = sub.add_parser("host-put")
    hp.add_argument("ip_address")
    hp.add_argument("tacacs_key")
    hp.add_argument("--hostname")
    hp.add_argument("--description")

    hgi = sub.add_parser("host-get-ip")
    hgi.add_argument("ip_address")

    hgn = sub.add_parser("host-get-name")
    hgn.add_argument("hostname")

    hd = sub.add_parser("host-delete")
    hd.add_argument("ip_address")

    sub.add_parser("host-list")

    # HOST GROUPS
    hgg = sub.add_parser("hostgroup-get")
    hgg.add_argument("group_name")

    hgp = sub.add_parser("hostgroup-put")
    hgp.add_argument("group_name")
    hgp.add_argument("--description")

    hgd = sub.add_parser("hostgroup-delete")
    hgd.add_argument("group_name")

    sub.add_parser("hostgroup-list")

    # HOST GROUP MEMBERS
    hgma = sub.add_parser("hostgroup-member-add")
    hgma.add_argument("ip_address")
    hgma.add_argument("group_name")

    hgmrem = sub.add_parser("hostgroup-member-remove")
    hgmrem.add_argument("ip_address")
    hgmrem.add_argument("group_name")

    hgml = sub.add_parser("hostgroup-member-list")
    hgml.add_argument("--ip_address")
    hgml.add_argument("--group_name")

    # POLICIES
    pp = sub.add_parser("policy-put")
    pp.add_argument("user_group_name")
    pp.add_argument("host_group_name")
    pp.add_argument("--priv-lvl", type=int, default=1)
    pp.add_argument("--allow-access", type=lambda x: x.lower() == "true", default=True)

    pg = sub.add_parser("policy-get")
    pg.add_argument("policy_id", type=int)

    pd = sub.add_parser("policy-delete")
    pd.add_argument("policy_id", type=int)

    sub.add_parser("policy-list")

    # COMMAND RULES
    crp = sub.add_parser("cmdrule-put")
    crp.add_argument("policy_id", type=int)
    crp.add_argument("command_pattern")
    crp.add_argument("--action", default="PERMIT")

    crg = sub.add_parser("cmdrule-get")
    crg.add_argument("rule_id", type=int)

    crd = sub.add_parser("cmdrule-delete")
    crd.add_argument("rule_id", type=int)

    crl = sub.add_parser("cmdrule-list")
    crl.add_argument("policy_id", type=int)

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

    # USER-HOSTS
    uhp = sub.add_parser("user-hosts")
    uhp.add_argument("username")

    args = p.parse_args()

    # DISPATCH
    if args.cmd == "user-get":
        out = user_get(args.username)
    elif args.cmd == "user-put":
        out = user_put(args.username, args.password_hash, args.full_name, args.is_active)
    elif args.cmd == "user-delete":
        out = user_delete(args.username)
    elif args.cmd == "user-list":
        out = user_list()

    elif args.cmd == "usergroup-get":
        out = usergroup_get(args.group_name)
    elif args.cmd == "usergroup-put":
        out = usergroup_put(args.group_name, args.description)
    elif args.cmd == "usergroup-delete":
        out = usergroup_delete(args.group_name)
    elif args.cmd == "usergroup-list":
        out = usergroup_list()

    elif args.cmd == "usergroup-member-add":
        out = usergroup_member_add(args.username, args.group_name)
    elif args.cmd == "usergroup-member-remove":
        out = usergroup_member_remove(args.username, args.group_name)
    elif args.cmd == "usergroup-member-list":
        out = usergroup_member_list(args.username, args.group_name)

    elif args.cmd == "host-put":
        out = host_put(args.ip_address, args.tacacs_key, args.hostname, args.description)
    elif args.cmd == "host-get-ip":
        out = host_get_ip(args.ip_address)
    elif args.cmd == "host-get-name":
        out = host_get_name(args.hostname)
    elif args.cmd == "host-delete":
        out = host_delete(args.ip_address)
    elif args.cmd == "host-list":
        out = host_list()

    elif args.cmd == "hostgroup-get":
        out = hostgroup_get(args.group_name)
    elif args.cmd == "hostgroup-put":
        out = hostgroup_put(args.group_name, args.description)
    elif args.cmd == "hostgroup-delete":
        out = hostgroup_delete(args.group_name)
    elif args.cmd == "hostgroup-list":
        out = hostgroup_list()

    elif args.cmd == "hostgroup-member-add":
        out = hostgroup_member_add(args.ip_address, args.group_name)
    elif args.cmd == "hostgroup-member-remove":
        out = hostgroup_member_remove(args.ip_address, args.group_name)
    elif args.cmd == "hostgroup-member-list":
        out = hostgroup_member_list(args.ip_address, args.group_name)

    elif args.cmd == "policy-put":
        out = policy_put(args.user_group_name, args.host_group_name, args.priv_lvl, args.allow_access)
    elif args.cmd == "policy-get":
        out = policy_get(args.policy_id)
    elif args.cmd == "policy-delete":
        out = policy_delete(args.policy_id)
    elif args.cmd == "policy-list":
        out = policy_list()

    elif args.cmd == "cmdrule-put":
        out = cmdrule_put(args.policy_id, args.command_pattern, args.action)
    elif args.cmd == "cmdrule-get":
        out = cmdrule_get(args.rule_id)
    elif args.cmd == "cmdrule-delete":
        out = cmdrule_delete(args.rule_id)
    elif args.cmd == "cmdrule-list":
        out = cmdrule_list(args.policy_id)

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

    elif args.cmd == "user-hosts":
        out = user_hosts(args.username)
    else:
        out = {"success": False, "error": "unknown command"}

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
