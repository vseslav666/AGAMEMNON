#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${TACACS_CONFIG_PATH:-/etc/tac_plus-ng/tac_plus-ng.cfg}"
LOG_DIR="${TACACS_LOG_DIR:-/var/log/tac_plus-ng}"
LOG_FILE="${TACACS_LOG_FILE:-${LOG_DIR}/tac_plus-ng.log}"
PIPE_PATH="/tmp/tac_plus-ng.pipe"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "[entrypoint] config not found: ${CONFIG_PATH}" >&2
  exit 1
fi

rm -f "${PIPE_PATH}"
mkfifo "${PIPE_PATH}"

TEE_PID=""
TAC_PID=""

shutdown() {
  if [[ -n "${TAC_PID}" ]] && kill -0 "${TAC_PID}" 2>/dev/null; then
    echo "[entrypoint] stopping tac_plus-ng pid=${TAC_PID}" >&2
    kill -TERM "${TAC_PID}" 2>/dev/null || true
  fi

  if [[ -n "${TEE_PID}" ]] && kill -0 "${TEE_PID}" 2>/dev/null; then
    kill -TERM "${TEE_PID}" 2>/dev/null || true
  fi

  rm -f "${PIPE_PATH}"
}

trap shutdown SIGINT SIGTERM EXIT

echo "[entrypoint] starting tac_plus-ng with config ${CONFIG_PATH}" >&2

# Keep service output in both docker logs and persistent file logs.
tee -a "${LOG_FILE}" < "${PIPE_PATH}" &
TEE_PID=$!

/usr/local/sbin/tac_plus-ng "${CONFIG_PATH}" > "${PIPE_PATH}" 2>&1 &
TAC_PID=$!

wait "${TAC_PID}"
