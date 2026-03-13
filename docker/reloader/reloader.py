import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException


app = FastAPI(title="TACACS Reloader", version="1.0.0")
logger = logging.getLogger("tacacs.reloader")


WATCH_DIR = Path(os.getenv("WATCH_DIR", "/etc/tac_plus-ng"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
TARGET_CONTAINER = os.getenv("TARGET_CONTAINER", "tacacs_plus")
RESTART_TIMEOUT = int(os.getenv("RESTART_TIMEOUT", "3"))
VALIDATION_CMD = os.getenv("VALIDATION_CMD", "tac_plus-ng -P /etc/tac_plus-ng/tac_plus-ng.cfg")
RELOADER_SOCKET_PATH = os.getenv("RELOADER_SOCKET_PATH", "/run/tacacs-reloader/reloader.sock")
DOCKER_PROXY_URL = os.getenv("DOCKER_PROXY_URL", "http://docker-socket-proxy:2375")
ALLOWED_TARGET_CONTAINERS = {"tacacs_plus"}
ALLOWED_VALIDATION_COMMANDS = {"tac_plus-ng -P /etc/tac_plus-ng/tac_plus-ng.cfg"}
FILES = [
    name.strip()
    for name in os.getenv("RELOADER_FILES", "users,user_groups,devices,profiles,ruleset").split(",")
    if name.strip()
]


def build_fingerprint() -> str:
    hasher = hashlib.sha256()
    for file_name in FILES:
        path = WATCH_DIR / file_name
        if path.exists():
            content = path.read_bytes()
            hasher.update(file_name.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(content)
            hasher.update(b"\0")
        else:
            hasher.update(file_name.encode("utf-8"))
            hasher.update(b"\0MISSING\0")
    return hasher.hexdigest()


def _decode_docker_exec_stream(payload: bytes) -> tuple[str, str]:
    if not payload:
        return "", ""

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    offset = 0
    length = len(payload)

    while offset + 8 <= length:
        stream_type = payload[offset]
        frame_size = int.from_bytes(payload[offset + 4 : offset + 8], byteorder="big")
        offset += 8

        if frame_size < 0 or offset + frame_size > length:
            break

        chunk = payload[offset : offset + frame_size]
        offset += frame_size
        text = chunk.decode("utf-8", errors="replace")
        if stream_type == 2:
            stderr_chunks.append(text)
        else:
            stdout_chunks.append(text)

    if offset == 0:
        return payload.decode("utf-8", errors="replace"), ""

    return "".join(stdout_chunks), "".join(stderr_chunks)


def _docker_request(method: str, path: str, payload: dict | None = None, timeout: float = 10.0) -> tuple[int, bytes]:
    base = DOCKER_PROXY_URL.rstrip("/")
    url = f"{base}{path}"
    logger.info("docker_proxy_request method=%s path=%s timeout=%s", method, path, timeout)
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read()
            logger.info("docker_proxy_response method=%s path=%s status=%s", method, path, response.status)
            return response.status, response_body
    except urllib.error.HTTPError as exc:
        error_body = exc.read()
        logger.error(
            "docker_proxy_response method=%s path=%s status=%s body=%s",
            method,
            path,
            exc.code,
            error_body.decode("utf-8", errors="replace"),
        )
        return exc.code, error_body
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Docker proxy request failed: {exc}")


def _enforce_allowlist() -> None:
    if TARGET_CONTAINER not in ALLOWED_TARGET_CONTAINERS:
        raise HTTPException(
            status_code=500,
            detail=f"TARGET_CONTAINER '{TARGET_CONTAINER}' is not allowed",
        )
    if VALIDATION_CMD not in ALLOWED_VALIDATION_COMMANDS:
        raise HTTPException(
            status_code=500,
            detail="VALIDATION_CMD is not allowed",
        )


def _exec_in_container(command: str) -> dict:
    target = urllib.parse.quote(TARGET_CONTAINER, safe="")
    create_status, create_body = _docker_request(
        method="POST",
        path=f"/containers/{target}/exec",
        payload={
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": False,
            "Cmd": ["bash", "-lc", command],
        },
        timeout=10,
    )
    if create_status != 201:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to create docker exec for '{TARGET_CONTAINER}': "
                f"status={create_status}, body={create_body.decode('utf-8', errors='replace')}"
            ),
        )

    try:
        exec_id = json.loads(create_body.decode("utf-8", errors="replace")).get("Id")
    except Exception:
        exec_id = None
    if not exec_id:
        raise HTTPException(status_code=502, detail="Docker exec create did not return Id")

    start_status, start_body = _docker_request(
        method="POST",
        path=f"/exec/{exec_id}/start",
        payload={"Detach": False, "Tty": False},
        timeout=30,
    )
    if start_status != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to start docker exec for '{TARGET_CONTAINER}': "
                f"status={start_status}, body={start_body.decode('utf-8', errors='replace')}"
            ),
        )

    inspect_status, inspect_body = _docker_request(
        method="GET",
        path=f"/exec/{exec_id}/json",
        payload=None,
        timeout=10,
    )
    if inspect_status != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to inspect docker exec for '{TARGET_CONTAINER}': "
                f"status={inspect_status}, body={inspect_body.decode('utf-8', errors='replace')}"
            ),
        )

    try:
        inspect_data = json.loads(inspect_body.decode("utf-8", errors="replace"))
    except Exception:
        inspect_data = {}
    exit_code = inspect_data.get("ExitCode")
    stdout, stderr = _decode_docker_exec_stream(start_body)
    return {
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "ok": exit_code == 0,
    }


def _restart_container() -> None:
    target = urllib.parse.quote(TARGET_CONTAINER, safe="")
    status, body = _docker_request(
        method="POST",
        path=f"/containers/{target}/restart?t={RESTART_TIMEOUT}",
        payload=None,
        timeout=max(5, RESTART_TIMEOUT + 2),
    )
    if status not in (204, 304):
        raise HTTPException(
            status_code=502,
            detail=(
                f"Restart failed for container '{TARGET_CONTAINER}': "
                f"status={status}, body={body.decode('utf-8', errors='replace')}"
            ),
        )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "watch_dir": str(WATCH_DIR),
        "target_container": TARGET_CONTAINER,
    }


@app.post("/apply")
def apply_reload() -> dict:
    _enforce_allowlist()
    validation = _exec_in_container(VALIDATION_CMD)
    if not validation["ok"]:
        message = validation.get("stderr") or validation.get("stdout") or "TACACS config validation failed"
        raise HTTPException(status_code=400, detail=str(message))

    _restart_container()
    return {
        "success": True,
        "validated": True,
        "reloaded": True,
        "validation": validation,
        "message": "Validation passed; container restarted",
    }


def watchdog_loop() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"[reloader] watchdog started; watch_dir={WATCH_DIR} files={FILES} poll={POLL_INTERVAL}s"
    )

    previous = build_fingerprint()
    print(f"[reloader] initial fingerprint={previous}")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            current = build_fingerprint()
            if current == previous:
                continue

            # debounce to avoid false positives during atomic multi-file updates
            time.sleep(0.8)
            stabilized = build_fingerprint()
            if stabilized != current:
                previous = stabilized
                print("[reloader] changes still settling, skip this cycle")
                continue

            print(f"[reloader] config changed: {previous[:12]} -> {stabilized[:12]}")
            previous = stabilized
        except Exception as exc:
            print(f"[reloader] error: {exc}")


def main() -> None:
    socket_path = Path(RELOADER_SOCKET_PATH)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    thread = threading.Thread(target=watchdog_loop, daemon=True)
    thread.start()

    print(f"[reloader] apply endpoint listening on unix socket {socket_path}")
    uvicorn.run(app, uds=str(socket_path), log_level="info")


if __name__ == "__main__":
    main()
