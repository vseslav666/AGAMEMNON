from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List

import psycopg2.extras

from app import tacacs_db


EXPORT_DIR = Path("/etc/tac_plus-ng")


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        Path(tmp.name).replace(path)


def _build_users() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                u.username,
                u.password_hash,
                COALESCE(
                    STRING_AGG(DISTINCT ug.group_name, ',' ORDER BY ug.group_name),
                    ''
                ) AS member_groups
            FROM users u
            LEFT JOIN user_group_members ugm ON ugm.user_id = u.user_id
            LEFT JOIN user_groups ug ON ug.group_id = ugm.group_id
            GROUP BY u.user_id, u.username, u.password_hash
            ORDER BY u.username
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    for row in rows:
        blocks.append(
            "\n".join(
                [
                    f'user {row["username"]} {{',
                    f'\tpassword login = crypt {row["password_hash"]}',
                    f'\tmember = {row["member_groups"]}',
                    "}",
                ]
            )
        )

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "users", content)
    return {"file": "users", "records": len(rows)}


def _build_hosts() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                h.ip_address,
                COALESCE(NULLIF(h.hostname, ''), h.ip_address) AS effective_hostname,
                COALESCE(MIN(hg.group_name), '') AS host_group_name
            FROM hosts h
            LEFT JOIN host_group_members hgm ON hgm.host_id = h.host_id
            LEFT JOIN host_groups hg ON hg.group_id = hgm.group_id
            GROUP BY h.host_id, h.ip_address, h.hostname
            ORDER BY effective_hostname, h.ip_address
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    for row in rows:
        blocks.append(
            "\n".join(
                [
                    f'host {row["effective_hostname"]} {{',
                    f'\taddress = {row["ip_address"]}',
                    f'\ttemplate = {row["host_group_name"]}',
                    "}",
                ]
            )
        )

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "hosts", content)
    return {"file": "hosts", "records": len(rows)}


def _build_host_groups() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                group_name,
                COALESCE(tacacs_key, '') AS tacacs_key
            FROM host_groups
            ORDER BY group_name
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    for row in rows:
        blocks.append(
            "\n".join(
                [
                    f'hostgroup {row["group_name"]} {{',
                    f'\tkey = {row["tacacs_key"]}',
                    "}",
                ]
            )
        )

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "host_groups", content)
    return {"file": "host_groups", "records": len(rows)}


def export_tacacs_data() -> Dict[str, Any]:
    users_meta = _build_users()
    hosts_meta = _build_hosts()
    host_groups_meta = _build_host_groups()

    users_content = (EXPORT_DIR / "users").read_text(encoding="utf-8")
    hosts_content = (EXPORT_DIR / "hosts").read_text(encoding="utf-8")
    host_groups_content = (EXPORT_DIR / "host_groups").read_text(encoding="utf-8")

    return {
        "success": True,
        "path": str(EXPORT_DIR),
        "files": [users_meta, hosts_meta, host_groups_meta],
        "file_contents": {
            "users": users_content,
            "hosts": hosts_content,
            "host_groups": host_groups_content,
        },
    }
