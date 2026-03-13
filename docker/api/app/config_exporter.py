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
            WITH member_pairs AS (
                SELECT DISTINCT
                    ugm.user_id,
                    (dg.group_name || CASE WHEN COALESCE(ugm.ro_rw, 0) = 1 THEN '_rw' ELSE '_ro' END) AS member_group
                FROM user_group_members ugm
                JOIN device_groups dg ON dg.group_id = ugm.group_id
            ),
            member_agg AS (
                SELECT
                    user_id,
                    STRING_AGG(member_group, ',' ORDER BY member_group) AS member_groups
                FROM member_pairs
                GROUP BY user_id
            ),
            profile_pairs AS (
                SELECT DISTINCT
                    upm.user_id,
                    pd.profile_name
                FROM user_profile_members upm
                JOIN profiles pd ON pd.profile_id = upm.profile_id
                WHERE pd.is_active = TRUE
            ),
            profile_agg AS (
                SELECT
                    user_id,
                    MIN(profile_name) AS user_profile
                FROM profile_pairs
                GROUP BY user_id
            )
            SELECT
                u.username,
                u.password_hash,
                u.is_active,
                COALESCE(ut.is_enabled, FALSE) AS totp_enabled,
                COALESCE(ma.member_groups, '') AS member_groups,
                COALESCE(pa.user_profile, '') AS user_profile
            FROM users u
            LEFT JOIN user_totp ut ON ut.user_id = u.user_id
            LEFT JOIN member_agg ma ON ma.user_id = u.user_id
            LEFT JOIN profile_agg pa ON pa.user_id = u.user_id
            ORDER BY u.username
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    for row in rows:
        if not row["is_active"]:
            login_password_line = "\tpassword login = deny"
        elif row["totp_enabled"]:
            login_password_line = "\tpassword login = mavis"
        else:
            login_password_line = f'\tpassword login = crypt {row["password_hash"]}'

        lines = [
            f'user {row["username"]} {{',
            login_password_line,
        ]
        if row["member_groups"]:
            lines.append(f'\tmember = {row["member_groups"]}')
        if row["user_profile"]:
            lines.append(f'\tprofile = {row["user_profile"]}')
        lines.append("}")
        blocks.append("\n".join(lines))

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "users", content)
    return {"file": "users", "records": len(rows)}


def _build_devices() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                d.ip_address,
                COALESCE(NULLIF(d.tacacs_key, ''), '') AS tacacs_key,
                COALESCE(NULLIF(d.hostname, ''), d.ip_address) AS effective_hostname,
                COALESCE(dg.group_name, '') AS device_group_name,
                COALESCE(dg.tacacs_key, '') AS device_group_key,
                COALESCE(NULLIF(v.vendor_name, ''), 'no_vendor') AS vendor_name
            FROM devices d
            LEFT JOIN device_group_members dgm ON dgm.device_id = d.device_id
            LEFT JOIN device_groups dg ON dg.group_id = dgm.group_id
            LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
            ORDER BY
                COALESCE(dg.group_name, ''),
                COALESCE(NULLIF(v.vendor_name, ''), 'no_vendor'),
                COALESCE(NULLIF(d.hostname, ''), d.ip_address),
                d.ip_address
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    group_keys: Dict[str, str] = {}
    ungrouped_rows: List[Dict[str, Any]] = []

    for row in rows:
        group_name = row["device_group_name"]
        if not group_name:
            ungrouped_rows.append(row)
            continue

        vendor_name = row["vendor_name"]
        grouped.setdefault(group_name, {}).setdefault(vendor_name, []).append(row)
        group_keys[group_name] = row["device_group_key"]

    blocks: List[str] = []

    # Grouped devices: device <group> -> device <vendor> -> device <hostname>
    for group_name in sorted(grouped.keys()):
        lines: List[str] = [f'device {group_name} {{']
        if group_keys.get(group_name):
            lines.append(f'\tkey = {group_keys[group_name]}')

        for vendor_name in sorted(grouped[group_name].keys()):
            vendor_node_name = f"{group_name}_{vendor_name}"
            lines.append(f'\tdevice {vendor_node_name} {{')
            for row in grouped[group_name][vendor_name]:
                lines.append(f'\t\tdevice {row["effective_hostname"]} {{')
                if row["tacacs_key"]:
                    lines.append(f'\t\t\tkey = {row["tacacs_key"]}')
                lines.append(f'\t\t\taddress = {row["ip_address"]}')
                lines.append('\t\t}')
            lines.append('\t}')

        lines.append('}')
        blocks.append("\n".join(lines))

    # Ungrouped devices: flat device blocks (without group/vendor nesting)
    for row in ungrouped_rows:
        lines = [
            f'device {row["effective_hostname"]} {{',
            f'\taddress = {row["ip_address"]}',
        ]
        if row["tacacs_key"]:
            lines.append(f'\tkey = {row["tacacs_key"]}')
        lines.append("}")
        blocks.append("\n".join(lines))

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "devices", content)
    return {"file": "devices", "records": len(rows)}


def _build_user_groups() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT dg.group_name, COALESCE(ugm.ro_rw, 0) AS ro_rw
            FROM user_group_members ugm
            JOIN device_groups dg ON dg.group_id = ugm.group_id
            ORDER BY dg.group_name, COALESCE(ugm.ro_rw, 0)
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    for row in rows:
        group_name = row["group_name"]
        mode = int(row.get("ro_rw") or 0)
        if mode == 1:
            blocks.append(f"group {group_name}_rw {{\n\tmember = rw\n}}")
        else:
            blocks.append(f"group {group_name}_ro {{\n\tmember = ro\n}}")

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "user_groups", content)
    return {"file": "user_groups", "records": len(blocks)}


def _build_profiles() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                profile_name,
                profile_body,
                is_active
            FROM profiles
            ORDER BY profile_name
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    blocks: List[str] = []
    active_count = 0
    for row in rows:
        if not row["is_active"]:
            continue
        active_count += 1

        body = str(row.get("profile_body") or "").strip("\n")
        lines = [f'profile {row["profile_name"]} {{']
        if body:
            lines.extend(body.splitlines())
        lines.append("}")
        blocks.append("\n".join(lines))

    content = "\n\n".join(blocks)
    _write_atomic(EXPORT_DIR / "profiles", content)
    return {"file": "profiles", "records": active_count}


def _build_ruleset() -> Dict[str, Any]:
    with tacacs_db.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            WITH device_vendor_pairs AS (
                SELECT DISTINCT
                    COALESCE(dg.group_name, '') AS device_group_name,
                    COALESCE(NULLIF(v.vendor_name, ''), 'no_vendor') AS vendor_name
                FROM devices d
                JOIN device_group_members dgm ON dgm.device_id = d.device_id
                JOIN device_groups dg ON dg.group_id = dgm.group_id
                LEFT JOIN vendors v ON v.vendor_id = d.vendor_id
                WHERE COALESCE(dg.group_name, '') <> ''
            ),
            group_modes AS (
                SELECT
                    dg.group_name,
                    ARRAY_AGG(DISTINCT COALESCE(ugm.ro_rw, 0)::smallint) AS modes
                FROM user_group_members ugm
                JOIN device_groups dg ON dg.group_id = ugm.group_id
                GROUP BY dg.group_name
            )
            SELECT
                dv.device_group_name,
                dv.vendor_name,
                gm.modes
            FROM device_vendor_pairs dv
            JOIN group_modes gm ON gm.group_name = dv.device_group_name
            ORDER BY dv.device_group_name, dv.vendor_name
            """
        )
        rows: List[Dict[str, Any]] = cur.fetchall()

    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        group_name = row["device_group_name"]
        by_group.setdefault(group_name, []).append(row)

    matched_groups = sorted(by_group.keys())

    lines: List[str] = [
        "ruleset {",
        "\trule assign_profiles {",
        "\t\tenabled = yes",
        "\t\tscript {",
    ]

    rule_count = 0
    for group_name in matched_groups:
        for row in by_group[group_name]:
            vendor_name = row["vendor_name"]
            vendor_node_name = f"{group_name}_{vendor_name}"
            modes = {int(mode) for mode in (row.get("modes") or [])}
            if 1 in modes:
                lines.extend(
                    [
                        f"\t\t\tif (device == {group_name} && device == {vendor_node_name} && member == {group_name}_rw) {{",
                        f"\t\t\t\tprofile = {vendor_name}_rw",
                        "\t\t\t\tpermit",
                        "\t\t\t}",
                    ]
                )
                rule_count += 1

            if 0 in modes:
                lines.extend(
                    [
                        f"\t\t\tif (device == {group_name} && device == {vendor_node_name} && member == {group_name}_ro) {{",
                        f"\t\t\t\tprofile = {vendor_name}_ro",
                        "\t\t\t\tpermit",
                        "\t\t\t}",
                    ]
                )
                rule_count += 1

    lines.extend(
        [
            "\t\t\tdeny",
            "\t\t}",
            "\t}",
            "}",
        ]
    )

    content = "\n".join(lines)
    _write_atomic(EXPORT_DIR / "ruleset", content)
    return {"file": "ruleset", "records": rule_count}


def export_tacacs_data() -> Dict[str, Any]:
    users_meta = _build_users()
    user_groups_meta = _build_user_groups()
    devices_meta = _build_devices()
    profiles_meta = _build_profiles()
    ruleset_meta = _build_ruleset()

    users_content = (EXPORT_DIR / "users").read_text(encoding="utf-8")
    user_groups_content = (EXPORT_DIR / "user_groups").read_text(encoding="utf-8")
    devices_content = (EXPORT_DIR / "devices").read_text(encoding="utf-8")
    profiles_content = (EXPORT_DIR / "profiles").read_text(encoding="utf-8")
    ruleset_content = (EXPORT_DIR / "ruleset").read_text(encoding="utf-8")

    return {
        "success": True,
        "path": str(EXPORT_DIR),
        "files": [users_meta, user_groups_meta, devices_meta, profiles_meta, ruleset_meta],
        "file_contents": {
            "users": users_content,
            "user_groups": user_groups_content,
            "devices": devices_content,
            "profiles": profiles_content,
            "ruleset": ruleset_content,
        },
    }
