import os
import json
import time
import argparse
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

import psycopg2
import psycopg2.extras
import pyotp

SCHEMA = "tacacs"

ALG_MAP = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}

# -------------------- DSN / Connection --------------------

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
    return psycopg2.connect(_dsn_from_env())


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_totp(secret: str, digits: int, period: int, algorithm: str) -> pyotp.TOTP:
    alg = algorithm.upper()
    digest = ALG_MAP.get(alg)
    if not digest:
        raise ValueError("Unsupported algorithm. Use SHA1/SHA256/SHA512.")
    return pyotp.TOTP(secret, digits=digits, interval=period, digest=digest)


# -------------------- Helpers for IDs --------------------

def _get_user(cur, username: str):
    cur.execute(
        f"SELECT id, username, enabled FROM {SCHEMA}.users WHERE username = %s",
        (username,),
    )
    return cur.fetchone()


def _get_group(cur, name: str):
    cur.execute(
        f"SELECT id, name, enabled FROM {SCHEMA}.groups WHERE name = %s",
        (name,),
    )
    return cur.fetchone()


def _get_device(cur, name: str):
    cur.execute(
        f"SELECT id, name, ip_address, enabled FROM {SCHEMA}.devices WHERE name = %s",
        (name,),
    )
    return cur.fetchone()


# ==========================================================
# USERS CRUD  (user-put / user-get / user-list / user-delete)
# ==========================================================

def user_put(
    username: str,
    password_hash: Optional[str] = None,   # без авто-шифрования
    password_type: str = "cleartext",
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """
    Создать нового пользователя или обновить существующего по username.
    password_hash записывается как есть (шифрование/хэширование пока не делаем).
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.users (username, password_hash, password_type, description, enabled)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET
              password_hash = COALESCE(EXCLUDED.password_hash, {SCHEMA}.users.password_hash),
              password_type = COALESCE(EXCLUDED.password_type, {SCHEMA}.users.password_type),
              description   = COALESCE(EXCLUDED.description, {SCHEMA}.users.description),
              enabled       = EXCLUDED.enabled,
              updated_at    = NOW()
            RETURNING *
            """,
            (username, password_hash, password_type, description, enabled),
        )
        row = cur.fetchone()
        return {"success": True, "user": row}


def user_get(username: str) -> Dict[str, Any]:
    """
    Получить пользователя по username.
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT * FROM {SCHEMA}.users WHERE username=%s",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"User '{username}' not found"}
        return {"success": True, "user": row}


def user_delete(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {SCHEMA}.users WHERE username=%s RETURNING id",
            (username,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def user_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {SCHEMA}.users ORDER BY username")
        return {"success": True, "data": cur.fetchall()}


# ==========================================================
# TOTP API (CLI: totp-*)
# ==========================================================

def totp_get(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute(
            f"SELECT * FROM {SCHEMA}.user_mfa_totp WHERE user_id = %s",
            (user["id"],),
        )
        mfa = cur.fetchone()

        return {
            "success": True,
            "user": {"id": user["id"], "username": user["username"], "enabled": user["enabled"]},
            "totp": mfa,
        }


def totp_put(
    username: str,
    issuer: str = "tacacs-plus",
    digits: int = 6,
    period: int = 30,
    algorithm: str = "SHA1",
) -> Dict[str, Any]:
    secret = pyotp.random_base32()
    totp = _make_totp(secret, digits, period, algorithm)
    otp_uri = totp.provisioning_uri(name=username, issuer_name=issuer)

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}
        if not user["enabled"]:
            return {"success": False, "error": f"User '{username}' is disabled"}

        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.user_mfa_totp
              (user_id, secret_base32, otp_uri, issuer, label, digits, period, algorithm,
               enabled, disabled_until, last_used_step, last_used_at)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s,
               TRUE, NULL, NULL, NULL)
            ON CONFLICT (user_id)
            DO UPDATE SET
              secret_base32 = EXCLUDED.secret_base32,
              otp_uri       = EXCLUDED.otp_uri,
              issuer        = EXCLUDED.issuer,
              label         = EXCLUDED.label,
              digits        = EXCLUDED.digits,
              period        = EXCLUDED.period,
              algorithm     = EXCLUDED.algorithm,
              enabled       = TRUE,
              disabled_until = NULL,
              last_used_step = NULL,
              last_used_at   = NULL,
              updated_at    = NOW()
            RETURNING *
            """,
            (user["id"], secret, otp_uri, issuer, username, digits, period, algorithm.upper()),
        )
        row = cur.fetchone()

        return {
            "success": True,
            "user": {"id": user["id"], "username": user["username"]},
            "totp": row,
            "secret_base32": secret,
            "otp_uri": otp_uri,
        }


def totp_verify(username: str, token: str, valid_window: int = 1) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute(
            f"SELECT * FROM {SCHEMA}.user_mfa_totp WHERE user_id = %s",
            (user["id"],),
        )
        mfa = cur.fetchone()
        if not mfa or not mfa["enabled"]:
            return {"success": False, "error": "TOTP not enabled for this user"}

        now_naive_utc = now_utc_naive()
        if mfa["disabled_until"] and now_naive_utc < mfa["disabled_until"]:
            return {
                "success": False,
                "error": f"TOTP temporarily disabled until {mfa['disabled_until'].isoformat()}",
            }

        totp = _make_totp(
            mfa["secret_base32"],
            mfa["digits"],
            mfa["period"],
            mfa["algorithm"],
        )

        step = int(time.time() // mfa["period"])
        last = mfa["last_used_step"]
        if last is not None and step <= last:
            return {"success": False, "error": "Token for this time-step already used"}

        ok = totp.verify(token, valid_window=valid_window)
        if not ok:
            return {"success": True, "verified": False}

        cur.execute(
            f"""
            UPDATE {SCHEMA}.user_mfa_totp
            SET last_used_step = %s,
                last_used_at   = %s,
                updated_at     = NOW()
            WHERE user_id = %s
            """,
            (step, now_naive_utc, user["id"]),
        )

        return {"success": True, "verified": True}


def totp_delete(username: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}

        cur.execute(
            f"DELETE FROM {SCHEMA}.user_mfa_totp WHERE user_id = %s RETURNING user_id",
            (user["id"],),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def totp_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT u.username, u.enabled AS user_enabled,
                   COALESCE(m.enabled, FALSE) AS totp_enabled,
                   m.disabled_until
            FROM {SCHEMA}.users u
            LEFT JOIN {SCHEMA}.user_mfa_totp m ON m.user_id = u.id
            ORDER BY u.username
            """
        )
        rows = cur.fetchall()
        return {"success": True, "data": rows}


def totp_backup(path: Optional[str] = None) -> Dict[str, Any]:
    if not path:
        path = f"totp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT u.username, m.*
            FROM {SCHEMA}.user_mfa_totp m
            JOIN {SCHEMA}.users u ON u.id = m.user_id
            ORDER BY u.username
            """
        )
        rows = cur.fetchall()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)

    return {"success": True, "backup_path": path, "count": len(rows)}


# ==========================================================
# DEVICES CRUD
# ==========================================================

def device_get(name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        dev = _get_device(cur, name)
        if not dev:
            return {"success": False, "error": f"Device '{name}' not found"}
        cur.execute(f"SELECT * FROM {SCHEMA}.devices WHERE id=%s", (dev["id"],))
        row = cur.fetchone()
        return {"success": True, "device": row}


def device_put(
    name: str,
    ip_address: str,
    secret: str,
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.devices (name, ip_address, secret, description, enabled)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name)
            DO UPDATE SET
              ip_address = EXCLUDED.ip_address,
              secret     = EXCLUDED.secret,
              description= EXCLUDED.description,
              enabled    = EXCLUDED.enabled,
              updated_at = NOW()
            RETURNING *
            """,
            (name, ip_address, secret, description, enabled),
        )
        row = cur.fetchone()
        return {"success": True, "device": row}


def device_delete(name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {SCHEMA}.devices WHERE name=%s RETURNING id",
            (name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def device_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {SCHEMA}.devices ORDER BY name")
        return {"success": True, "data": cur.fetchall()}


# ==========================================================
# GROUPS CRUD
# ==========================================================

def group_get(name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        grp = _get_group(cur, name)
        if not grp:
            return {"success": False, "error": f"Group '{name}' not found"}
        cur.execute(f"SELECT * FROM {SCHEMA}.groups WHERE id=%s", (grp["id"],))
        return {"success": True, "group": cur.fetchone()}


def group_put(
    name: str,
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.groups (name, description, enabled)
            VALUES (%s, %s, %s)
            ON CONFLICT (name)
            DO UPDATE SET
              description = EXCLUDED.description,
              enabled = EXCLUDED.enabled,
              updated_at = NOW()
            RETURNING *
            """,
            (name, description, enabled),
        )
        return {"success": True, "group": cur.fetchone()}


def group_delete(name: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {SCHEMA}.groups WHERE name=%s RETURNING id",
            (name,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def group_list() -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {SCHEMA}.groups ORDER BY name")
        return {"success": True, "data": cur.fetchall()}


# ==========================================================
# USER <-> GROUP membership
# ==========================================================

def membership_add(username: str, groupname: str, priority: int = 10) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}
        grp = _get_group(cur, groupname)
        if not grp:
            return {"success": False, "error": f"Group '{groupname}' not found"}

        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.user_groups (user_id, group_id, priority)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, group_id)
            DO UPDATE SET priority = EXCLUDED.priority
            RETURNING *
            """,
            (user["id"], grp["id"], priority),
        )
        return {"success": True, "membership": cur.fetchone()}


def membership_remove(username: str, groupname: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user = _get_user(cur, username)
        if not user:
            return {"success": False, "error": f"User '{username}' not found"}
        grp = _get_group(cur, groupname)
        if not grp:
            return {"success": False, "error": f"Group '{groupname}' not found"}

        cur.execute(
            f"DELETE FROM {SCHEMA}.user_groups WHERE user_id=%s AND group_id=%s RETURNING user_id",
            (user["id"], grp["id"]),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def membership_list(username: Optional[str] = None, groupname: Optional[str] = None) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if username:
            user = _get_user(cur, username)
            if not user:
                return {"success": False, "error": f"User '{username}' not found"}
            cur.execute(
                f"""
                SELECT u.username, g.name as groupname, ug.priority
                FROM {SCHEMA}.user_groups ug
                JOIN {SCHEMA}.users u ON u.id=ug.user_id
                JOIN {SCHEMA}.groups g ON g.id=ug.group_id
                WHERE ug.user_id=%s
                ORDER BY ug.priority ASC, g.name
                """,
                (user["id"],),
            )
        elif groupname:
            grp = _get_group(cur, groupname)
            if not grp:
                return {"success": False, "error": f"Group '{groupname}' not found"}
            cur.execute(
                f"""
                SELECT u.username, g.name as groupname, ug.priority
                FROM {SCHEMA}.user_groups ug
                JOIN {SCHEMA}.users u ON u.id=ug.user_id
                JOIN {SCHEMA}.groups g ON g.id=ug.group_id
                WHERE ug.group_id=%s
                ORDER BY ug.priority ASC, u.username
                """,
                (grp["id"],),
            )
        else:
            cur.execute(
                f"""
                SELECT u.username, g.name as groupname, ug.priority
                FROM {SCHEMA}.user_groups ug
                JOIN {SCHEMA}.users u ON u.id=ug.user_id
                JOIN {SCHEMA}.groups g ON g.id=ug.group_id
                ORDER BY u.username, ug.priority ASC
                """
            )
        return {"success": True, "data": cur.fetchall()}


# ==========================================================
# AUTHORIZATION RULES CRUD
# ==========================================================

def rule_create(
    name: str,
    object_type: str,
    object_name: str,
    service: str = "shell",
    privilege_level: Optional[int] = None,
    permitted_commands: Optional[str] = None,
    denied_commands: Optional[str] = None,
    argument_filter: Optional[str] = None,
    enabled: bool = True,
    avpairs: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    object_type = object_type.lower()
    if object_type not in ("user", "group"):
        return {"success": False, "error": "object_type must be 'user' or 'group'"}

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        user_id = None
        group_id = None

        if object_type == "user":
            user = _get_user(cur, object_name)
            if not user:
                return {"success": False, "error": f"User '{object_name}' not found"}
            user_id = user["id"]
        else:
            grp = _get_group(cur, object_name)
            if not grp:
                return {"success": False, "error": f"Group '{object_name}' not found"}
            group_id = grp["id"]

        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.authorization_rules
              (name, object_type, user_id, group_id, service, privilege_level,
               permitted_commands, denied_commands, argument_filter, enabled)
            VALUES
              (%s, %s, %s, %s, %s, %s,
               %s, %s, %s, %s)
            RETURNING *
            """,
            (
                name, object_type, user_id, group_id, service, privilege_level,
                permitted_commands, denied_commands, argument_filter, enabled
            ),
        )
        rule = cur.fetchone()

        inserted_av = []
        if avpairs:
            for k, v in avpairs:
                cur.execute(
                    f"""
                    INSERT INTO {SCHEMA}.authorization_rule_avpairs
                      (rule_id, av_key, av_value, enabled)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (rule_id, av_key, av_value) DO NOTHING
                    RETURNING *
                    """,
                    (rule["id"], k, v),
                )
                row = cur.fetchone()
                if row:
                    inserted_av.append(row)

        return {"success": True, "rule": rule, "avpairs": inserted_av}


def rule_get(rule_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT * FROM {SCHEMA}.authorization_rules WHERE id=%s",
            (rule_id,),
        )
        rule = cur.fetchone()
        if not rule:
            return {"success": False, "error": f"Rule id={rule_id} not found"}

        cur.execute(
            f"SELECT * FROM {SCHEMA}.authorization_rule_avpairs WHERE rule_id=%s ORDER BY id",
            (rule_id,),
        )
        av = cur.fetchall()

        return {"success": True, "rule": rule, "avpairs": av}


def rule_list(
    object_type: Optional[str] = None,
    object_name: Optional[str] = None,
    service: Optional[str] = None,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        where = []
        params = []

        if object_type:
            where.append("object_type = %s")
            params.append(object_type.lower())

        if service:
            where.append("service = %s")
            params.append(service)

        if object_name and object_type:
            if object_type.lower() == "user":
                user = _get_user(cur, object_name)
                if not user:
                    return {"success": False, "error": f"User '{object_name}' not found"}
                where.append("user_id = %s")
                params.append(user["id"])
            elif object_type.lower() == "group":
                grp = _get_group(cur, object_name)
                if not grp:
                    return {"success": False, "error": f"Group '{object_name}' not found"}
                where.append("group_id = %s")
                params.append(grp["id"])

        sql = f"SELECT * FROM {SCHEMA}.authorization_rules"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"

        cur.execute(sql, tuple(params))
        return {"success": True, "data": cur.fetchall()}


def rule_delete(rule_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {SCHEMA}.authorization_rules WHERE id=%s RETURNING id",
            (rule_id,),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


# ==========================================================
# RULE AVPAIRS CRUD
# ==========================================================

def rule_av_add(rule_id: int, key: str, value: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT id FROM {SCHEMA}.authorization_rules WHERE id=%s",
            (rule_id,),
        )
        if not cur.fetchone():
            return {"success": False, "error": f"Rule id={rule_id} not found"}

        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.authorization_rule_avpairs (rule_id, av_key, av_value, enabled)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (rule_id, av_key, av_value)
            DO UPDATE SET enabled=TRUE
            RETURNING *
            """,
            (rule_id, key, value),
        )
        return {"success": True, "avpair": cur.fetchone()}


def rule_av_remove(rule_id: int, key: str, value: str) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            DELETE FROM {SCHEMA}.authorization_rule_avpairs
            WHERE rule_id=%s AND av_key=%s AND av_value=%s
            RETURNING id
            """,
            (rule_id, key, value),
        )
        deleted = cur.fetchone() is not None
        return {"success": True, "deleted": deleted}


def rule_av_list(rule_id: int) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT * FROM {SCHEMA}.authorization_rule_avpairs WHERE rule_id=%s ORDER BY id",
            (rule_id,),
        )
        return {"success": True, "data": cur.fetchall()}


# ==========================================================
# CLI
# ==========================================================

def main():
    p = argparse.ArgumentParser(description="Tacacs DB helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- USERS ----
    ug = sub.add_parser("user-get", help="Get user by username")
    ug.add_argument("username")

    up = sub.add_parser("user-put", help="Create/update user")
    up.add_argument("username")
    up.add_argument("--password-hash")
    up.add_argument("--password-type", default="cleartext")
    up.add_argument("--description")
    up.add_argument("--enabled", type=lambda x: x.lower() == "true", default=True)

    ud = sub.add_parser("user-delete")
    ud.add_argument("username")

    sub.add_parser("user-list")

    # ---- TOTP ----
    tg = sub.add_parser("totp-get")
    tg.add_argument("username")

    tp = sub.add_parser("totp-put")
    tp.add_argument("username")
    tp.add_argument("--issuer", default="tacacs-plus")
    tp.add_argument("--digits", type=int, default=6)
    tp.add_argument("--period", type=int, default=30)
    tp.add_argument("--algorithm", default="SHA1")

    tv = sub.add_parser("totp-verify")
    tv.add_argument("username")
    tv.add_argument("token")
    tv.add_argument("--window", type=int, default=1)

    td = sub.add_parser("totp-delete")
    td.add_argument("username")

    sub.add_parser("totp-list")

    tb = sub.add_parser("totp-backup")
    tb.add_argument("--path")

    # ---- Devices ----
    dg = sub.add_parser("device-get")
    dg.add_argument("name")

    dp = sub.add_parser("device-put")
    dp.add_argument("name")
    dp.add_argument("ip_address")
    dp.add_argument("secret")
    dp.add_argument("--description")
    dp.add_argument("--enabled", type=lambda x: x.lower() == "true", default=True)

    dd = sub.add_parser("device-delete")
    dd.add_argument("name")

    sub.add_parser("device-list")

    # ---- Groups ----
    gg = sub.add_parser("group-get")
    gg.add_argument("name")

    gp = sub.add_parser("group-put")
    gp.add_argument("name")
    gp.add_argument("--description")
    gp.add_argument("--enabled", type=lambda x: x.lower() == "true", default=True)

    gd = sub.add_parser("group-delete")
    gd.add_argument("name")

    sub.add_parser("group-list")

    # ---- Membership ----
    ma = sub.add_parser("member-add")
    ma.add_argument("username")
    ma.add_argument("groupname")
    ma.add_argument("--priority", type=int, default=10)

    mr = sub.add_parser("member-remove")
    mr.add_argument("username")
    mr.add_argument("groupname")

    ml = sub.add_parser("member-list")
    ml.add_argument("--username")
    ml.add_argument("--groupname")

    # ---- Rules ----
    rc = sub.add_parser("rule-create")
    rc.add_argument("name")
    rc.add_argument("object_type", choices=["user", "group"])
    rc.add_argument("object_name")
    rc.add_argument("--service", default="shell")
    rc.add_argument("--priv", type=int)
    rc.add_argument("--permit")
    rc.add_argument("--deny")
    rc.add_argument("--argfilter")
    rc.add_argument("--enabled", type=lambda x: x.lower() == "true", default=True)
    rc.add_argument("--av", action="append", help="AV-pair as key=value (repeatable)")

    rgp = sub.add_parser("rule-get")
    rgp.add_argument("id", type=int)

    rlp = sub.add_parser("rule-list")
    rlp.add_argument("--object-type", choices=["user", "group"])
    rlp.add_argument("--object-name")
    rlp.add_argument("--service")

    rdp = sub.add_parser("rule-delete")
    rdp.add_argument("id", type=int)

    # ---- Rule AVPairs ----
    raa = sub.add_parser("rule-av-add")
    raa.add_argument("id", type=int)
    raa.add_argument("key")
    raa.add_argument("value")

    rar = sub.add_parser("rule-av-remove")
    rar.add_argument("id", type=int)
    rar.add_argument("key")
    rar.add_argument("value")

    ral = sub.add_parser("rule-av-list")
    ral.add_argument("id", type=int)

    args = p.parse_args()

    # dispatch
    if args.cmd == "user-get":
        out = user_get(args.username)
    elif args.cmd == "user-put":
        out = user_put(
            args.username,
            password_hash=args.password_hash,
            password_type=args.password_type,
            description=args.description,
            enabled=args.enabled,
        )
    elif args.cmd == "user-delete":
        out = user_delete(args.username)
    elif args.cmd == "user-list":
        out = user_list()

    elif args.cmd == "totp-get":
        out = totp_get(args.username)
    elif args.cmd == "totp-put":
        out = totp_put(args.username, args.issuer, args.digits, args.period, args.algorithm)
    elif args.cmd == "totp-verify":
        out = totp_verify(args.username, args.token, args.window)
    elif args.cmd == "totp-delete":
        out = totp_delete(args.username)
    elif args.cmd == "totp-list":
        out = totp_list()
    elif args.cmd == "totp-backup":
        out = totp_backup(args.path)

    elif args.cmd == "device-get":
        out = device_get(args.name)
    elif args.cmd == "device-put":
        out = device_put(args.name, args.ip_address, args.secret, args.description, args.enabled)
    elif args.cmd == "device-delete":
        out = device_delete(args.name)
    elif args.cmd == "device-list":
        out = device_list()

    elif args.cmd == "group-get":
        out = group_get(args.name)
    elif args.cmd == "group-put":
        out = group_put(args.name, args.description, args.enabled)
    elif args.cmd == "group-delete":
        out = group_delete(args.name)
    elif args.cmd == "group-list":
        out = group_list()

    elif args.cmd == "member-add":
        out = membership_add(args.username, args.groupname, args.priority)
    elif args.cmd == "member-remove":
        out = membership_remove(args.username, args.groupname)
    elif args.cmd == "member-list":
        out = membership_list(args.username, args.groupname)

    elif args.cmd == "rule-create":
        avpairs = []
        if args.av:
            for item in args.av:
                if "=" not in item:
                    out = {"success": False, "error": f"Bad av format '{item}', use key=value"}
                    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
                    return
                k, v = item.split("=", 1)
                avpairs.append((k, v))

        out = rule_create(
            name=args.name,
            object_type=args.object_type,
            object_name=args.object_name,
            service=args.service,
            privilege_level=args.priv,
            permitted_commands=args.permit,
            denied_commands=args.deny,
            argument_filter=args.argfilter,
            enabled=args.enabled,
            avpairs=avpairs or None,
        )
    elif args.cmd == "rule-get":
        out = rule_get(args.id)
    elif args.cmd == "rule-list":
        out = rule_list(args.object_type, args.object_name, args.service)
    elif args.cmd == "rule-delete":
        out = rule_delete(args.id)

    elif args.cmd == "rule-av-add":
        out = rule_av_add(args.id, args.key, args.value)
    elif args.cmd == "rule-av-remove":
        out = rule_av_remove(args.id, args.key, args.value)
    elif args.cmd == "rule-av-list":
        out = rule_av_list(args.id)

    else:
        out = {"success": False, "error": "unknown command"}

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
