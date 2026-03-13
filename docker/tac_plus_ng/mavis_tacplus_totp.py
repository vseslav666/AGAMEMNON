#!/usr/bin/env python3
"""
MAVIS backend for TACACS+ login authentication.
Behavior:
- Users with enabled TOTP in DB: password field is treated as 6-digit OTP.
- Users without TOTP: return NOTFOUND so tac_plus-ng falls back to local password hash.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import pyotp

if "/usr/local/lib/mavis" not in sys.path:
    sys.path.insert(0, "/usr/local/lib/mavis")

from mavis import (
    AV_A_PASSWORD,
    AV_A_RESULT,
    AV_A_TACTYPE,
    AV_A_TYPE,
    AV_A_USER,
    AV_A_USER_RESPONSE,
    AV_A_PASSWORD_ONESHOT,
    AV_V_RESULT_ERROR,
    AV_V_RESULT_FAIL,
    AV_V_RESULT_NOTFOUND,
    AV_V_RESULT_OK,
    AV_V_TACTYPE_AUTH,
    AV_V_TYPE_TACPLUS,
    MAVIS_DOWN,
    MAVIS_FINAL,
    Mavis,
)


OTP_RE = re.compile(r"^\d{6}$")


def _dsn_from_env() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")

    host = os.getenv("PGHOST", "database")
    port = int(os.getenv("PGPORT", "5432"))
    dbname = os.getenv("PGDATABASE", "tacacs_db")
    user = os.getenv("PGUSER", "admin_pg")
    password = os.getenv("PGPASSWORD", "supersecret")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _get_conn():
    schema = os.getenv("PGSCHEMA", "tacacs")
    return psycopg2.connect(_dsn_from_env(), options=f"-c search_path={schema},public")


def _fetch_user_totp_state(username: str):
    with _get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                u.user_id,
                u.is_active,
                ut.totp_secret,
                ut.is_enabled
            FROM users u
            LEFT JOIN user_totp ut ON ut.user_id = u.user_id
            WHERE u.username = %s
            """,
            (username,),
        )
        return cur.fetchone()


def _mark_last_used(user_id: int) -> None:
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE user_totp SET last_used_at = %s WHERE user_id = %s",
            (datetime.now(timezone.utc), user_id),
        )


def _write_response(mavis: Mavis, verdict: int, result: str, message: str | None = None, oneshot: bool = False):
    mavis.av_pairs[AV_A_RESULT] = result
    if message:
        mavis.av_pairs[AV_A_USER_RESPONSE] = message
    if oneshot:
        mavis.av_pairs[AV_A_PASSWORD_ONESHOT] = "1"

    for key in sorted(mavis.av_pairs):
        val = mavis.av_pairs.get(key)
        if val:
            print(f"{key} {str(val).replace(chr(10), chr(13))}")
    print(f"={verdict}")
    sys.stdout.flush()


def handle_request(mavis: Mavis) -> None:
    if mavis.av_pairs.get(AV_A_TYPE) != AV_V_TYPE_TACPLUS:
        _write_response(mavis, MAVIS_DOWN, AV_V_RESULT_NOTFOUND)
        return

    if mavis.av_pairs.get(AV_A_TACTYPE) != AV_V_TACTYPE_AUTH:
        _write_response(mavis, MAVIS_DOWN, AV_V_RESULT_NOTFOUND)
        return

    username = mavis.av_pairs.get(AV_A_USER)
    password = mavis.av_pairs.get(AV_A_PASSWORD)

    if not username:
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_ERROR, "User not set")
        return

    if password is None or password == "":
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_ERROR, "Password not set")
        return

    try:
        row = _fetch_user_totp_state(username)
    except Exception:
        # backend unavailable -> allow daemon fallback behavior
        _write_response(mavis, MAVIS_DOWN, AV_V_RESULT_NOTFOUND)
        return

    if not row:
        _write_response(mavis, MAVIS_DOWN, AV_V_RESULT_NOTFOUND)
        return

    # non-TOTP user -> let local crypt auth handle
    if not row.get("is_enabled") or not row.get("totp_secret"):
        _write_response(mavis, MAVIS_DOWN, AV_V_RESULT_NOTFOUND)
        return

    # TOTP user becomes OTP-only
    if not row.get("is_active"):
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_FAIL, "User inactive")
        return

    if not OTP_RE.fullmatch(password):
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_FAIL, "OTP must be 6 digits")
        return

    try:
        totp = pyotp.TOTP(row["totp_secret"], digits=6, interval=30)
        ok = totp.verify(password, valid_window=1)
    except Exception:
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_ERROR, "OTP verification error")
        return

    if not ok:
        _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_FAIL, "Invalid OTP")
        return

    try:
        _mark_last_used(int(row["user_id"]))
    except Exception:
        pass

    _write_response(mavis, MAVIS_FINAL, AV_V_RESULT_OK, oneshot=True)


def main() -> int:
    while True:
        mavis = Mavis()
        handle_request(mavis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
