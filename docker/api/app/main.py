from typing import Optional, List, Dict, Any
from pathlib import Path
from collections import deque
from datetime import datetime, timezone
import logging
import os
import re
from urllib.parse import quote
from app import tacacs_db
from app.config_exporter import export_tacacs_data
import requests_unixsocket

import bcrypt

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="TACACS Management API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("tacacs.api.logs")
RELOADER_SOCKET_PATH = os.getenv("RELOADER_SOCKET_PATH", "/run/tacacs-reloader/reloader.sock")
RELOADER_APPLY_TIMEOUT = float(os.getenv("RELOADER_APPLY_TIMEOUT", "30"))


def _trim(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip()


def _empty_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _ensure_no_spaces(field_name: str, value: Optional[str]) -> None:
    if value is not None and any(ch.isspace() for ch in value):
        raise HTTPException(status_code=400, detail=f"{field_name} must not contain spaces")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def handle_result(result: dict):
    if result.get("success"):
        return result

    detail = result.get("error") or result.get("reason") or "Unknown error"
    lower = str(detail).lower()
    code = 404 if "not found" in lower else 400
    raise HTTPException(status_code=code, detail=detail)


def _apply_via_reloader() -> dict:
    reloader_sock = Path(RELOADER_SOCKET_PATH)
    logger.info(
        "reloader_apply_prepare socket_exists=%s reloader_socket=%s",
        reloader_sock.exists(),
        RELOADER_SOCKET_PATH,
    )
    if not reloader_sock.exists():
        raise HTTPException(
            status_code=502,
            detail=f"Reloader socket is not available in API container: {RELOADER_SOCKET_PATH}",
        )

    session = requests_unixsocket.Session()
    encoded_socket = quote(RELOADER_SOCKET_PATH, safe="")
    base = f"http+unix://{encoded_socket}"

    try:
        response = session.post(
            f"{base}/apply",
            json={},
            timeout=max(5.0, RELOADER_APPLY_TIMEOUT),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to call reloader apply endpoint over unix socket: {exc}",
        )

    if response.status_code != 200:
        detail = response.text
        try:
            body = response.json()
            detail = str(body.get("detail") or body)
        except Exception:
            pass
        status_code = response.status_code if 400 <= response.status_code < 500 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"Reloader apply failed: {detail}",
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Reloader apply returned non-JSON response: {exc}",
        )

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Reloader apply response has invalid format")
    return payload


TACACS_LOG_FILE = Path("/var/log/tac_plus-ng/tac_plus-ng.log")
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
TACACS_LINE_RE = re.compile(
    r"^\s*(?P<debug>\d+):\s+(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+(?P<session>[^\s:]+):\s+(?P<host>[^\s]+)\s*(?P<message>.*)$"
)
ALT_TACACS_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+(?P<tz>[+-]\d{4}|Z)\s+(?P<host>\S+)\s+(?P<message>.*)$"
)
KV_RE = re.compile(r"\b([a-zA-Z][\w\-]*)=([\"'][^\"']*[\"']|[^\s,]+)")


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value)


def _detect_log_level(message: str) -> str:
    upper = message.upper()
    if any(token in upper for token in ("ERROR", "FAIL", "DENY", "ILLEGAL", "EXCEPTION", "CRITICAL")):
        return "error"
    if "WARN" in upper:
        return "warn"
    if "DEBUG" in upper:
        return "debug"
    if any(token in upper for token in ("PASS", "SUCCESS", "STARTED", "CONNECTED", "HEALTHY")):
        return "info"
    return "unknown"


def _tail_log_lines(path: Path, limit: int) -> tuple[List[str], int]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    total_lines = 0
    tail = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            total_lines += 1
            tail.append(line.rstrip("\n"))

    return list(tail), total_lines


def _parse_tacacs_line(raw_line: str, idx: int) -> dict:
    cleaned = _strip_ansi(raw_line).strip()
    match = TACACS_LINE_RE.match(cleaned)

    if match:
        message = (match.group("message") or "").strip()
        return {
            "id": idx,
            "raw": cleaned,
            "message": message,
            "timestamp": match.group("time"),
            "session": match.group("session"),
            "host": match.group("host"),
            "level": _detect_log_level(message),
        }

    alt_match = ALT_TACACS_LINE_RE.match(cleaned)
    if alt_match:
        alt_message = (alt_match.group("message") or "").strip()
        return {
            "id": idx,
            "raw": cleaned,
            "message": alt_message,
            "timestamp": alt_match.group("time"),
            "session": None,
            "host": alt_match.group("host"),
            "level": _detect_log_level(alt_message),
        }

    return {
        "id": idx,
        "raw": cleaned,
        "message": cleaned,
        "timestamp": None,
        "session": None,
        "host": None,
        "level": _detect_log_level(cleaned),
    }


def _extract_session_id(session_token: Optional[str]) -> Optional[str]:
    if not session_token:
        return None
    if "/" not in session_token:
        return session_token
    _, session_id = session_token.split("/", 1)
    return session_id or None


def _event_kind_from_message(message: str) -> Optional[str]:
    lower = message.lower()

    if "authen" in lower or "shell login" in lower:
        return "authentication"
    if "author" in lower or "authorization" in lower:
        return "authorization"
    if "acct" in lower or "accounting" in lower:
        return "accounting"

    if "version:" in lower and "type:" in lower:
        if "type: 1" in lower:
            return "authentication"
        if "type: 2" in lower:
            return "authorization"
        if "type: 3" in lower:
            return "accounting"

    return None


def _event_result_from_message(message: str) -> str:
    lower = message.lower()
    if any(token in lower for token in ("succeeded", "success", "pass", "permit", "pass_add")):
        return "success"
    if any(token in lower for token in ("failed", "fail", "deny", "error", "invalid")):
        return "failure"
    return "unknown"


def _extract_attrs_from_message(message: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for key, value in KV_RE.findall(message):
        attrs[key] = value.strip('"')
    return attrs


def _extract_aaa_events(lines: List[dict]) -> List[dict]:
    session_kind: Dict[str, str] = {}
    session_ctx: Dict[str, Dict[str, Any]] = {}
    events: List[dict] = []

    for line in lines:
        message = str(line.get("message") or "")
        session = line.get("session")
        session_id = _extract_session_id(session)
        kind = _event_kind_from_message(message)
        attrs = _extract_attrs_from_message(message)

        if session_id:
            ctx = session_ctx.setdefault(session_id, {})
            if kind:
                session_kind[session_id] = kind

            user_match = re.search(r"\buser\s*\(len:\s*\d+\):\s*(\S+)", message, re.IGNORECASE)
            if user_match:
                ctx["username"] = user_match.group(1)

            rem_addr_match = re.search(r"\brem_addr\s*\(len:\s*\d+\):\s*(\S+)", message, re.IGNORECASE)
            if rem_addr_match:
                ctx["remote_addr"] = rem_addr_match.group(1)

            port_match = re.search(r"\bport\s*\(len:\s*\d+\):\s*(\S+)", message, re.IGNORECASE)
            if port_match:
                ctx["port"] = port_match.group(1)

            login_match = re.search(
                r"shell login for\s+'([^']+)'\s+from\s+(\S+)\s+on\s+(\S+)\s+(succeeded|failed)(?:\s+\(profile=(.*?)\))?",
                message,
                re.IGNORECASE,
            )
            if login_match:
                ctx["username"] = login_match.group(1)
                ctx["remote_addr"] = login_match.group(2)
                ctx["port"] = login_match.group(3)
                if login_match.group(5):
                    ctx["profile"] = login_match.group(5)

            if "username" in attrs and attrs["username"]:
                ctx["username"] = attrs["username"]
            if "rem_addr" in attrs and attrs["rem_addr"]:
                ctx["remote_addr"] = attrs["rem_addr"]

        effective_kind = kind or (session_kind.get(session_id) if session_id else None)
        lower = message.lower()
        is_aaa_line = bool(
            effective_kind
            and (
                "authen" in lower
                or "author" in lower
                or "acct" in lower
                or "authorization" in lower
                or "accounting" in lower
                or "shell login" in lower
                or "writing " in lower
                or "/reply" in lower
            )
        )

        if not is_aaa_line:
            continue

        ctx = session_ctx.get(session_id or "", {})
        event_attrs = dict(attrs)
        if not session_id:
            tab_parts = [part.strip() for part in message.split("\t") if part.strip()]
            if tab_parts:
                if not ctx.get("username"):
                    ctx["username"] = tab_parts[0]
                if len(tab_parts) > 1 and not ctx.get("port"):
                    ctx["port"] = tab_parts[1]
                if not ctx.get("remote_addr"):
                    ctx["remote_addr"] = line.get("host")
                if len(tab_parts) > 2 and "device" not in event_attrs:
                    event_attrs["device"] = tab_parts[2]

        if "profile" in ctx and "profile" not in event_attrs:
            event_attrs["profile"] = str(ctx["profile"])

        events.append(
            {
                "id": len(events) + 1,
                "line_id": line.get("id"),
                "timestamp": line.get("timestamp"),
                "session": session,
                "session_id": session_id,
                "host": line.get("host"),
                "kind": effective_kind,
                "result": _event_result_from_message(message),
                "message": message,
                "username": ctx.get("username"),
                "remote_addr": ctx.get("remote_addr"),
                "port": ctx.get("port"),
                "attrs": event_attrs,
            }
        )

    return events


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    full_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    password: Optional[str] = Field(None, min_length=1)
    full_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class VendorCreate(BaseModel):
    vendor_name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None


class DeviceCreate(BaseModel):
    ip_address: str
    tacacs_key: str
    hostname: Optional[str] = None
    vendor_name: str = Field(..., min_length=1)
    description: Optional[str] = None


class DeviceUpdate(BaseModel):
    new_ip_address: Optional[str] = None
    tacacs_key: Optional[str] = None
    hostname: Optional[str] = None
    vendor_name: Optional[str] = None
    description: Optional[str] = None


class DeviceGroupCreate(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=64)
    tacacs_key: Optional[str] = None
    description: Optional[str] = None


class UserGroupMemberModify(BaseModel):
    username: str
    group_name: str
    ro_rw: int = Field(0, ge=0, le=1)


class DeviceGroupMemberModify(BaseModel):
    ip_address: str
    group_name: str


class ProfileCreate(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=64)
    profile_body: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_active: bool = True


class UserProfileMemberModify(BaseModel):
    username: str
    profile_name: str


class TotpCreate(BaseModel):
    issuer: str = "tacacs-plus"
    digits: int = Field(6, ge=4, le=10)
    period: int = Field(30, ge=10, le=300)
    is_enabled: bool = True


class TotpVerifyRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=16)
    digits: int = Field(6, ge=4, le=10)
    period: int = Field(30, ge=10, le=300)
    valid_window: int = Field(1, ge=0, le=5)


@app.get("/")
def root():
    return {"message": "TACACS Management API (new schema)"}


@app.get("/health")
def health():
    try:
        with tacacs_db.get_conn() as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


@app.get("/users")
def list_users():
    result = tacacs_db.user_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/users/{username}")
def get_user(username: str):
    result = tacacs_db.user_get(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    username = (user.username or "").strip()
    _ensure_no_spaces("username", username)
    if not username:
        raise HTTPException(status_code=400, detail="username is required")

    password_hash = hash_password(user.password)
    result = tacacs_db.user_put(  # type: ignore[attr-defined]
        username=username,
        password_hash=password_hash,
        full_name=_empty_to_none(user.full_name),
        description=_empty_to_none(user.description),
        is_active=user.is_active,
    )
    return handle_result(result)


@app.put("/users/{username}")
def update_user(username: str, body: UserUpdate):
    existing = tacacs_db.user_get(username)  # type: ignore[attr-defined]
    if not existing.get("success"):
        return handle_result(existing)

    user_row = existing["user"]
    password_hash = user_row["password_hash"]
    full_name = user_row.get("full_name")
    description = user_row.get("description")
    is_active = user_row.get("is_active", True)

    if body.password is not None:
        password_hash = hash_password(body.password)
    if body.full_name is not None:
        full_name = _empty_to_none(body.full_name)
    if body.description is not None:
        description = _empty_to_none(body.description)
    if body.is_active is not None:
        is_active = body.is_active

    result = tacacs_db.user_put(  # type: ignore[attr-defined]
        username=username,
        password_hash=password_hash,
        full_name=full_name,
        description=description,
        is_active=is_active,
    )
    return handle_result(result)


@app.delete("/users/{username}", status_code=204)
def delete_user(username: str):
    result = tacacs_db.user_delete(username)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="User not found")

    return None


@app.post("/user-group-members", status_code=201)
def add_user_to_group(member: UserGroupMemberModify):
    result = tacacs_db.usergroup_member_add(  # type: ignore[attr-defined]
        username=member.username,
        group_name=member.group_name,
        ro_rw=member.ro_rw,
    )
    return handle_result(result)


@app.delete("/user-group-members", status_code=204)
def remove_user_from_group(member: UserGroupMemberModify):
    result = tacacs_db.usergroup_member_remove(  # type: ignore[attr-defined]
        username=member.username,
        group_name=member.group_name,
    )
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Membership not found")

    return None


@app.get("/user-group-members")
def list_user_group_members(
    username: Optional[str] = None,
    group_name: Optional[str] = None,
):
    result = tacacs_db.usergroup_member_list(  # type: ignore[attr-defined]
        username=username,
        group_name=group_name,
    )
    return handle_result(result)


@app.get("/vendors")
def list_vendors():
    result = tacacs_db.vendor_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/vendors/{vendor_name}")
def get_vendor(vendor_name: str):
    result = tacacs_db.vendor_get(vendor_name)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/vendors", status_code=201)
def create_vendor(vendor: VendorCreate):
    vendor_name = (vendor.vendor_name or "").strip()
    _ensure_no_spaces("vendor_name", vendor_name)
    if not vendor_name:
        raise HTTPException(status_code=400, detail="vendor_name is required")

    result = tacacs_db.vendor_put(  # type: ignore[attr-defined]
        vendor_name=vendor_name,
        description=_empty_to_none(vendor.description),
    )
    return handle_result(result)


@app.put("/vendors/{vendor_name}")
def update_vendor(vendor_name: str, body: VendorCreate):
    _ensure_no_spaces("vendor_name", (vendor_name or "").strip())
    result = tacacs_db.vendor_put(  # type: ignore[attr-defined]
        vendor_name=(vendor_name or "").strip(),
        description=_empty_to_none(body.description),
    )
    return handle_result(result)


@app.delete("/vendors/{vendor_name}", status_code=204)
def delete_vendor(vendor_name: str):
    result = tacacs_db.vendor_delete(vendor_name)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Vendor not found")

    return None


@app.get("/devices")
def list_devices():
    result = tacacs_db.device_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/devices/{ip_address}")
def get_device_by_ip(ip_address: str):
    result = tacacs_db.device_get_ip(ip_address)  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/devices/by-name/{hostname}")
def get_device_by_name(hostname: str):
    result = tacacs_db.device_get_name(hostname)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/devices", status_code=201)
def create_device(device: DeviceCreate):
    ip_address = (device.ip_address or "").strip()
    hostname = _empty_to_none(device.hostname)
    vendor_name = (device.vendor_name or "").strip()
    _ensure_no_spaces("hostname", hostname)
    _ensure_no_spaces("vendor_name", vendor_name)

    existing = tacacs_db.device_get_ip(ip_address)  # type: ignore[attr-defined]
    if existing.get("success"):
        raise HTTPException(status_code=400, detail=f"Device with IP '{ip_address}' already exists")

    result = tacacs_db.device_create(  # type: ignore[attr-defined]
        ip_address=ip_address,
        tacacs_key=(device.tacacs_key or "").strip(),
        hostname=hostname,
        vendor_name=vendor_name,
        description=_empty_to_none(device.description),
    )
    return handle_result(result)


@app.put("/devices/{ip_address}")
def update_device(ip_address: str, body: DeviceUpdate):
    current_ip = (ip_address or "").strip()
    existing = tacacs_db.device_get_ip(current_ip)  # type: ignore[attr-defined]
    if not existing.get("success"):
        return handle_result(existing)

    device_row = existing["device"]
    new_ip_address = (body.new_ip_address or current_ip).strip()
    tacacs_key = body.tacacs_key.strip() if body.tacacs_key is not None else device_row["tacacs_key"]
    hostname = _empty_to_none(body.hostname) if body.hostname is not None else device_row.get("hostname")
    description = _empty_to_none(body.description) if body.description is not None else device_row.get("description")
    vendor_name = (body.vendor_name.strip() if body.vendor_name is not None else (device_row.get("vendor_name") or ""))

    _ensure_no_spaces("hostname", hostname)
    _ensure_no_spaces("vendor_name", vendor_name)

    if new_ip_address != current_ip:
        conflict = tacacs_db.device_get_ip(new_ip_address)  # type: ignore[attr-defined]
        if conflict.get("success"):
            raise HTTPException(status_code=400, detail=f"Device with IP '{new_ip_address}' already exists")

    result = tacacs_db.device_update(  # type: ignore[attr-defined]
        current_ip_address=current_ip,
        new_ip_address=new_ip_address,
        tacacs_key=tacacs_key,
        hostname=hostname,
        vendor_name=vendor_name,
        description=description,
    )
    return handle_result(result)


@app.delete("/devices/{ip_address}", status_code=204)
def delete_device(ip_address: str):
    result = tacacs_db.device_delete(ip_address)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Device not found")

    return None


@app.get("/device-groups")
def list_device_groups():
    result = tacacs_db.devicegroup_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/device-groups/{group_name}")
def get_device_group(group_name: str):
    result = tacacs_db.devicegroup_get(group_name)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/device-groups", status_code=201)
def create_device_group(group: DeviceGroupCreate):
    group_name = (group.group_name or "").strip()
    _ensure_no_spaces("group_name", group_name)
    if not group_name:
        raise HTTPException(status_code=400, detail="group_name is required")

    result = tacacs_db.devicegroup_put(  # type: ignore[attr-defined]
        group_name=group_name,
        tacacs_key=_empty_to_none(group.tacacs_key),
        description=_empty_to_none(group.description),
    )
    return handle_result(result)


@app.put("/device-groups/{group_name}")
def update_device_group(group_name: str, body: DeviceGroupCreate):
    normalized_group_name = (group_name or "").strip()
    _ensure_no_spaces("group_name", normalized_group_name)
    result = tacacs_db.devicegroup_put(  # type: ignore[attr-defined]
        group_name=normalized_group_name,
        tacacs_key=_empty_to_none(body.tacacs_key),
        description=_empty_to_none(body.description),
    )
    return handle_result(result)


@app.delete("/device-groups/{group_name}", status_code=204)
def delete_device_group(group_name: str):
    result = tacacs_db.devicegroup_delete(group_name)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Device group not found")

    return None


@app.post("/device-group-members", status_code=201)
def add_device_to_group(member: DeviceGroupMemberModify):
    result = tacacs_db.devicegroup_member_add(  # type: ignore[attr-defined]
        ip_address=member.ip_address,
        group_name=member.group_name,
    )
    return handle_result(result)


@app.delete("/device-group-members", status_code=204)
def remove_device_from_group(member: DeviceGroupMemberModify):
    result = tacacs_db.devicegroup_member_remove(  # type: ignore[attr-defined]
        ip_address=member.ip_address,
        group_name=member.group_name,
    )
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Membership not found")

    return None


@app.get("/device-group-members")
def list_device_group_members(
    ip_address: Optional[str] = None,
    group_name: Optional[str] = None,
):
    result = tacacs_db.devicegroup_member_list(  # type: ignore[attr-defined]
        ip_address=ip_address,
        group_name=group_name,
    )
    return handle_result(result)


@app.get("/profiles")
def list_profiles():
    result = tacacs_db.profile_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/profiles/{profile_name}")
def get_profile(profile_name: str):
    result = tacacs_db.profile_get(profile_name)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/profiles", status_code=201)
def create_profile(profile: ProfileCreate):
    profile_name = (profile.profile_name or "").strip()
    _ensure_no_spaces("profile_name", profile_name)
    if not profile_name:
        raise HTTPException(status_code=400, detail="profile_name is required")

    result = tacacs_db.profile_put(  # type: ignore[attr-defined]
        profile_name=profile_name,
        profile_body=profile.profile_body,
        description=_empty_to_none(profile.description),
        is_active=profile.is_active,
    )
    return handle_result(result)


@app.put("/profiles/{profile_name}")
def update_profile(profile_name: str, body: ProfileCreate):
    normalized_profile_name = (profile_name or "").strip()
    _ensure_no_spaces("profile_name", normalized_profile_name)
    result = tacacs_db.profile_put(  # type: ignore[attr-defined]
        profile_name=normalized_profile_name,
        profile_body=body.profile_body,
        description=_empty_to_none(body.description),
        is_active=body.is_active,
    )
    return handle_result(result)


@app.delete("/profiles/{profile_name}", status_code=204)
def delete_profile(profile_name: str):
    result = tacacs_db.profile_delete(profile_name)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Profile not found")

    return None


@app.post("/user-profile-members", status_code=201)
def add_user_profile(member: UserProfileMemberModify):
    result = tacacs_db.userprofile_member_add(  # type: ignore[attr-defined]
        username=member.username,
        profile_name=member.profile_name,
    )
    return handle_result(result)


@app.delete("/user-profile-members", status_code=204)
def remove_user_profile(member: UserProfileMemberModify):
    result = tacacs_db.userprofile_member_remove(  # type: ignore[attr-defined]
        username=member.username,
        profile_name=member.profile_name,
    )
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Membership not found")

    return None


@app.get("/user-profile-members")
def list_user_profile_members(
    username: Optional[str] = None,
    profile_name: Optional[str] = None,
):
    result = tacacs_db.userprofile_member_list(  # type: ignore[attr-defined]
        username=username,
        profile_name=profile_name,
    )
    return handle_result(result)


@app.post("/users/{username}/totp", status_code=201)
def create_or_update_totp(username: str, cfg: TotpCreate):
    result = tacacs_db.totp_put(  # type: ignore[attr-defined]
        username=username,
        issuer=cfg.issuer,
        digits=cfg.digits,
        period=cfg.period,
        is_enabled=cfg.is_enabled,
    )
    return handle_result(result)


@app.get("/users/{username}/totp")
def get_totp(username: str):
    result = tacacs_db.totp_get(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/users/{username}/totp/disable")
def disable_totp(username: str):
    result = tacacs_db.totp_disable(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.delete("/users/{username}/totp", status_code=204)
def delete_totp(username: str):
    result = tacacs_db.totp_delete(username)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="TOTP profile not found")

    return None


@app.post("/users/{username}/totp/verify")
def verify_totp(username: str, body: TotpVerifyRequest):
    result = tacacs_db.verify_totp_for_user(  # type: ignore[attr-defined]
        username=username,
        token=body.token,
        digits=body.digits,
        period=body.period,
        valid_window=body.valid_window,
    )

    if not result.get("success"):
        detail = result.get("reason") or "Unknown error"
        lower = str(detail).lower()
        code = 404 if "not found" in lower else 400
        raise HTTPException(status_code=code, detail=detail)

    return result


@app.get("/logs/tacacs")
def get_tacacs_logs(limit: int = 200):
    bounded_limit = max(1, min(limit, 1000))

    logger.info(
        "tacacs_log_request path=%s parent=%s exists=%s parent_exists=%s limit=%s",
        TACACS_LOG_FILE,
        TACACS_LOG_FILE.parent,
        TACACS_LOG_FILE.exists(),
        TACACS_LOG_FILE.parent.exists(),
        bounded_limit,
    )

    try:
        lines, total = _tail_log_lines(TACACS_LOG_FILE, bounded_limit)
    except FileNotFoundError:
        return {
            "success": True,
            "file_path": str(TACACS_LOG_FILE),
            "limit": bounded_limit,
            "total_lines": 0,
            "missing": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lines": [],
            "events": [],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read TACACS log: {exc}")

    parsed_lines = [_parse_tacacs_line(raw_line, idx + 1) for idx, raw_line in enumerate(lines)]
    aaa_events = _extract_aaa_events(parsed_lines)

    return {
        "success": True,
        "file_path": str(TACACS_LOG_FILE),
        "limit": bounded_limit,
        "total_lines": total,
        "missing": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lines": parsed_lines,
        "events": aaa_events,
    }


@app.post("/generate-config/")
def generate_config():
    try:
        export_result = export_tacacs_data()
        apply_result = _apply_via_reloader()
        export_result["apply"] = apply_result
        return export_result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate config files: {exc}")
