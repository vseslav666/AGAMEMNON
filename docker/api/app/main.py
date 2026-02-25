from typing import Optional, List
from app import tacacs_db
from app.config_exporter import export_tacacs_data

import bcrypt

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from app.database import get_db
from app.models import UserCreate, UserUpdate, UserResponse, UserListResponse, PasswordType
from app.repositories.user_repository import UserRepository

app = FastAPI(title="TACACS Management API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Хешируем пароль bcrpyt-ом, чтобы не хранить его в открытом виде."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def handle_result(result: dict):
    """
    Унифицированная обработка ответов tacacs_db.*

    Ожидаем словарь вида:
      {"success": True, ...}
    или {"success": False, "error": "..."}.

    Если success=False — кидаем HTTPException.
    Если success=True — просто возвращаем словарь как есть.
    """
    if result.get("success"):
        return result

    detail = result.get("error") or result.get("reason") or "Unknown error"
    lower = str(detail).lower()
    status = 404 if "not found" in lower else 400
    raise HTTPException(status_code=status, detail=detail)


# ---------------------------------------------------------------------------
# Pydantic-схемы
# ---------------------------------------------------------------------------


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


class UserGroupCreate(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None


class HostCreate(BaseModel):
    ip_address: str
    tacacs_key: str
    hostname: Optional[str] = None
    description: Optional[str] = None


class HostUpdate(BaseModel):
    tacacs_key: Optional[str] = None
    hostname: Optional[str] = None
    description: Optional[str] = None


class HostGroupCreate(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=64)
    tacacs_key: Optional[str] = None
    description: Optional[str] = None


class UserGroupMemberModify(BaseModel):
    username: str
    group_name: str


class HostGroupMemberModify(BaseModel):
    ip_address: str
    group_name: str


class PolicyCreate(BaseModel):
    user_group_name: str
    host_group_name: str
    priv_lvl: int = Field(1, ge=0, le=15)
    allow_access: bool = True


class CommandRuleCreate(BaseModel):
    command_pattern: str
    action: str = Field("PERMIT", pattern="^(PERMIT|DENY|permit|deny)$")


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


# ---------------------------------------------------------------------------
# Общие эндпоинты
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "TACACS Management API (new schema)"}


@app.get("/health")
async def health():
    try:
        with tacacs_db.get_conn() as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


# ---------------------------------------------------------------------------
# USERS  (user_put / user_get / user_delete / user_list)
# ---------------------------------------------------------------------------


@app.get("/users")
async def list_users():
    """
    Вернуть список всех пользователей.
    Обёртка над tacacs_db.user_list()
    """
    result = tacacs_db.user_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/users/{username}")
async def get_user(username: str):
    """
    Получить пользователя по username.
    Обёртка над tacacs_db.user_get()
    """
    result = tacacs_db.user_get(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/users", status_code=201)
async def create_user(user: UserCreate):
    """
    Создать нового пользователя.
    Использует bcrypt для хеширования пароля и tacacs_db.user_put().
    """
    password_hash = hash_password(user.password)
    result = tacacs_db.user_put(  # type: ignore[attr-defined]
        username=user.username,
        password_hash=password_hash,
        full_name=user.full_name,
        description=user.description,
        is_active=user.is_active,
    )
    return handle_result(result)


@app.put("/users/{username}")
async def update_user(username: str, body: UserUpdate):
    """
    Обновить существующего пользователя (full_name / is_active / password).
    Реализовано через чтение текущего пользователя и tacacs_db.user_put().
    """
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
        full_name = body.full_name
    if body.description is not None:
        description = body.description
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
async def delete_user(username: str):
    """
    Удалить пользователя по username.
    Обёртка над tacacs_db.user_delete().
    """
    result = tacacs_db.user_delete(username)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        # Пользователь не найден
        raise HTTPException(status_code=404, detail="User not found")

    return None


# ---------------------------------------------------------------------------
# USER GROUPS (usergroup_put / get / delete / list)
# ---------------------------------------------------------------------------


@app.get("/user-groups")
async def list_user_groups():
    result = tacacs_db.usergroup_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/user-groups/{group_name}")
async def get_user_group(group_name: str):
    result = tacacs_db.usergroup_get(group_name)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/user-groups", status_code=201)
async def create_user_group(group: UserGroupCreate):
    result = tacacs_db.usergroup_put(  # type: ignore[attr-defined]
        group_name=group.group_name,
        description=group.description,
    )
    return handle_result(result)


@app.put("/user-groups/{group_name}")
async def update_user_group(group_name: str, body: UserGroupCreate):
    """
    Обновление описания группы пользователей.
    В БД ключом является имя группы, поэтому имя из URL.
    """
    result = tacacs_db.usergroup_put(  # type: ignore[attr-defined]
        group_name=group_name,
        description=body.description,
    )
    return handle_result(result)


@app.delete("/user-groups/{group_name}", status_code=204)
async def delete_user_group(group_name: str):
    result = tacacs_db.usergroup_delete(group_name)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="User group not found")

    return None


# ---------------------------------------------------------------------------
# USER-GROUP MEMBERS (usergroup_member_add / remove / list)
# ---------------------------------------------------------------------------


@app.post("/user-group-members", status_code=201)
async def add_user_to_group(member: UserGroupMemberModify):
    """
    Добавить пользователя в группу.
    Обёртка над tacacs_db.usergroup_member_add().
    """
    result = tacacs_db.usergroup_member_add(  # type: ignore[attr-defined]
        username=member.username,
        group_name=member.group_name,
    )
    return handle_result(result)


@app.delete("/user-group-members", status_code=204)
async def remove_user_from_group(member: UserGroupMemberModify):
    """
    Удалить пользователя из группы.
    Обёртка над tacacs_db.usergroup_member_remove().
    """
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
async def list_user_group_members(
    username: Optional[str] = None,
    group_name: Optional[str] = None,
):
    """
    Список членств.
    Если задан username — покажем группы пользователя.
    Если задан group_name — покажем юзеров в группе.
    Если ничего не задано — полный список.
    """
    result = tacacs_db.usergroup_member_list(  # type: ignore[attr-defined]
        username=username,
        group_name=group_name,
    )
    return handle_result(result)


# ---------------------------------------------------------------------------
# HOSTS (host_put / host_get_ip / host_get_name / host_delete / host_list)
# ---------------------------------------------------------------------------


@app.get("/hosts")
async def list_hosts():
    result = tacacs_db.host_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/hosts/{ip_address}")
async def get_host_by_ip(ip_address: str):
    result = tacacs_db.host_get_ip(ip_address)  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/hosts/by-name/{hostname}")
async def get_host_by_name(hostname: str):
    result = tacacs_db.host_get_name(hostname)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/hosts", status_code=201)
async def create_host(host: HostCreate):
    result = tacacs_db.host_put(  # type: ignore[attr-defined]
        ip_address=host.ip_address,
        tacacs_key=host.tacacs_key,
        hostname=host.hostname,
        description=host.description,
    )
    return handle_result(result)


@app.put("/hosts/{ip_address}")
async def update_host(ip_address: str, body: HostUpdate):
    existing = tacacs_db.host_get_ip(ip_address)  # type: ignore[attr-defined]
    if not existing.get("success"):
        return handle_result(existing)

    host_row = existing["host"]
    tacacs_key = body.tacacs_key or host_row["tacacs_key"]
    hostname = body.hostname if body.hostname is not None else host_row.get("hostname")
    description = (
        body.description if body.description is not None else host_row.get("description")
    )

    result = tacacs_db.host_put(  # type: ignore[attr-defined]
        ip_address=ip_address,
        tacacs_key=tacacs_key,
        hostname=hostname,
        description=description,
    )
    return handle_result(result)


@app.delete("/hosts/{ip_address}", status_code=204)
async def delete_host(ip_address: str):
    result = tacacs_db.host_delete(ip_address)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Host not found")

    return None


# ---------------------------------------------------------------------------
# HOST GROUPS (hostgroup_put / get / delete / list)
# ---------------------------------------------------------------------------


@app.get("/host-groups")
async def list_host_groups():
    result = tacacs_db.hostgroup_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/host-groups/{group_name}")
async def get_host_group(group_name: str):
    result = tacacs_db.hostgroup_get(group_name)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/host-groups", status_code=201)
async def create_host_group(group: HostGroupCreate):
    result = tacacs_db.hostgroup_put(  # type: ignore[attr-defined]
        group_name=group.group_name,
        tacacs_key=group.tacacs_key,
        description=group.description,
    )
    return handle_result(result)


@app.put("/host-groups/{group_name}")
async def update_host_group(group_name: str, body: HostGroupCreate):
    result = tacacs_db.hostgroup_put(  # type: ignore[attr-defined]
        group_name=group_name,
        tacacs_key=body.tacacs_key,
        description=body.description,
    )
    return handle_result(result)


@app.delete("/host-groups/{group_name}", status_code=204)
async def delete_host_group(group_name: str):
    result = tacacs_db.hostgroup_delete(group_name)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Host group not found")

    return None


# ---------------------------------------------------------------------------
# HOST-GROUP MEMBERS (hostgroup_member_add / remove / list)
# ---------------------------------------------------------------------------


@app.post("/host-group-members", status_code=201)
async def add_host_to_group(member: HostGroupMemberModify):
    result = tacacs_db.hostgroup_member_add(  # type: ignore[attr-defined]
        ip_address=member.ip_address,
        group_name=member.group_name,
    )
    return handle_result(result)


@app.delete("/host-group-members", status_code=204)
async def remove_host_from_group(member: HostGroupMemberModify):
    result = tacacs_db.hostgroup_member_remove(  # type: ignore[attr-defined]
        ip_address=member.ip_address,
        group_name=member.group_name,
    )
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Membership not found")

    return None


@app.get("/host-group-members")
async def list_host_group_members(
    ip_address: Optional[str] = None,
    group_name: Optional[str] = None,
):
    result = tacacs_db.hostgroup_member_list(  # type: ignore[attr-defined]
        ip_address=ip_address,
        group_name=group_name,
    )
    return handle_result(result)


# ---------------------------------------------------------------------------
# ACCESS POLICIES (policy_put / get / delete / list)
# ---------------------------------------------------------------------------


@app.get("/policies")
async def list_policies():
    result = tacacs_db.policy_list()  # type: ignore[attr-defined]
    return handle_result(result)


@app.get("/policies/{policy_id}")
async def get_policy(policy_id: int):
    result = tacacs_db.policy_get(policy_id)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/policies", status_code=201)
async def create_policy(policy: PolicyCreate):
    result = tacacs_db.policy_put(  # type: ignore[attr-defined]
        user_group_name=policy.user_group_name,
        host_group_name=policy.host_group_name,
        priv_lvl=policy.priv_lvl,
        allow_access=policy.allow_access,
    )
    return handle_result(result)


@app.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(policy_id: int):
    result = tacacs_db.policy_delete(policy_id)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Policy not found")

    return None


# ---------------------------------------------------------------------------
# COMMAND RULES (cmdrule_put / get / delete / list)
# ---------------------------------------------------------------------------


@app.get("/policies/{policy_id}/command-rules")
async def list_command_rules(policy_id: int):
    result = tacacs_db.cmdrule_list(policy_id)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/policies/{policy_id}/command-rules", status_code=201)
async def create_command_rule(policy_id: int, rule: CommandRuleCreate):
    result = tacacs_db.cmdrule_put(  # type: ignore[attr-defined]
        policy_id=policy_id,
        command_pattern=rule.command_pattern,
        action=rule.action.upper(),
    )
    return handle_result(result)


@app.get("/command-rules/{rule_id}")
async def get_command_rule(rule_id: int):
    result = tacacs_db.cmdrule_get(rule_id)  # type: ignore[attr-defined]
    return handle_result(result)


@app.delete("/command-rules/{rule_id}", status_code=204)
async def delete_command_rule(rule_id: int):
    result = tacacs_db.cmdrule_delete(rule_id)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Rule not found")

    return None


# ---------------------------------------------------------------------------
# USER TOTP (totp_put / totp_get / totp_disable / totp_delete / verify_totp_for_user)
# ---------------------------------------------------------------------------


@app.post("/users/{username}/totp", status_code=201)
async def create_or_update_totp(username: str, cfg: TotpCreate):
    """
    Создать или обновить TOTP-профиль пользователя.
    Обёртка над tacacs_db.totp_put().
    """
    result = tacacs_db.totp_put(  # type: ignore[attr-defined]
        username=username,
        issuer=cfg.issuer,
        digits=cfg.digits,
        period=cfg.period,
        is_enabled=cfg.is_enabled,
    )
    return handle_result(result)


@app.get("/users/{username}/totp")
async def get_totp(username: str):
    result = tacacs_db.totp_get(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.post("/users/{username}/totp/disable")
async def disable_totp(username: str):
    result = tacacs_db.totp_disable(username)  # type: ignore[attr-defined]
    return handle_result(result)


@app.delete("/users/{username}/totp", status_code=204)
async def delete_totp(username: str):
    result = tacacs_db.totp_delete(username)  # type: ignore[attr-defined]
    if not result.get("success"):
        handle_result(result)

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="TOTP profile not found")

    return None


@app.post("/users/{username}/totp/verify")
async def verify_totp(username: str, body: TotpVerifyRequest):
    """
    Проверить TOTP-код пользователя.
    В случае неверного кода вернётся verified=False, но HTTP 200.
    Ошибки БД/пользователя дадут HTTP 4xx.
    """
    result = tacacs_db.verify_totp_for_user(  # type: ignore[attr-defined]
        username=username,
        token=body.token,
        digits=body.digits,
        period=body.period,
        valid_window=body.valid_window,
    )

    # Ошибки "user not found", "TOTP profile not found" и т.п.
    if not result.get("success"):
        detail = result.get("reason") or "Unknown error"
        lower = str(detail).lower()
        status = 404 if "not found" in lower else 400
        raise HTTPException(status_code=status, detail=detail)

    # success=True -> либо verified=True, либо verified=False (неверный токен)
    return result


# ---------------------------------------------------------------------------
# USER HOSTS (user_hosts)
# ---------------------------------------------------------------------------


@app.get("/users/{username}/hosts")
async def list_user_hosts(username: str):
    """
    Вернуть список хостов, к которым пользователь имеет доступ,
    через матрицу access_policies.
    Обёртка над tacacs_db.user_hosts().
    """
    result = tacacs_db.user_hosts(username)  # type: ignore[attr-defined]
    return handle_result(result)

@app.post("/generate-config/")
async def generate_config():
    """Сгенерировать TACACS include-файлы из БД в общий volume."""
    try:
        return export_tacacs_data()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate config files: {exc}")
