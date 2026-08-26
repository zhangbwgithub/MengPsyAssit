#!/usr/bin/env bash
# 前端冒烟脚本：一键起后端 + 前端 preview，验证页面可达与 /api 代理可达。
# 说明：vite preview 已在本仓库 vite.config.js 中配置 proxy，
#       因此 /api/health 经前端服务 5199 转发到后端 8660。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE_DIR="$ROOT/app/frontend"
BE_PORT=8660
FE_PORT=5199
TS=$(date +%Y%m%d_%H%M%S)
RESULT_DIR="$ROOT/tests/e2e/results/frontend_${TS}"
mkdir -p "$RESULT_DIR"

LOG_BUNDLE="$RESULT_DIR/service.log"
FE_LOG="$RESULT_DIR/frontend.log"
BE_LOG="$RESULT_DIR/backend.log"
RESULT_FILE="$RESULT_DIR/result.txt"

cleanup() {
  echo "[smoke] cleaning up..." >> "$LOG_BUNDLE"
  [ -n "${BE_PID:-}" ] && kill "$BE_PID" 2>/dev/null || true
  [ -n "${FE_PID:-}" ] && kill "$FE_PID" 2>/dev/null || true
  # 等待端口释放，避免后续运行冲突
  sleep 1
}
trap cleanup EXIT

# 1. 起后端（工作目录为 backend src 包所在目录，uvicorn 才能解析 psyapp.main）
cd "$ROOT"
if [ -f ".venv/bin/python" ]; then
  .venv/bin/python -m uvicorn psyapp.main:app --port "$BE_PORT" --host 127.0.0.1 > "$BE_LOG" 2>&1 &
  BE_PID=$!
else
  echo "[FAIL] .venv/bin/python 不存在" | tee "$RESULT_FILE"
  exit 1
fi

# 2. 起前端 preview（vite preview 已在 vite.config.js 中配置 /api 代理）
cd "$FE_DIR"
npm run preview > "$FE_LOG" 2>&1 &
FE_PID=$!

cd "$ROOT"

# 3. 等待服务就绪
wait_for_url() {
  local url=$1
  local label=$2
  local max_wait=${3:-30}
  for i in $(seq 1 "$max_wait"); do
    if curl -sf "$url" > /dev/null 2>&1; then
      echo "[smoke] $label ready at ${url}" >> "$LOG_BUNDLE"
      return 0
    fi
    sleep 1
  done
  echo "[FAIL] $label 未在 ${max_wait}s 内就绪: $url" | tee "$RESULT_FILE"
  return 1
}

wait_for_url "http://127.0.0.1:$BE_PORT/health" "backend"
wait_for_url "http://127.0.0.1:$FE_PORT/" "frontend"

# 4. 断言页面含关键文案
PAGE_HTML=$(curl -sf "http://127.0.0.1:$FE_PORT/")
echo "$PAGE_HTML" > "$RESULT_DIR/page.html"
if ! echo "$PAGE_HTML" | grep -q "AI 生成内容仅供专业参考"; then
  echo "[FAIL] 页面缺少合规提示文案" | tee "$RESULT_FILE"
  exit 1
fi

# 5. 断言 /api/health 经前端代理可达
HEALTH_JSON=$(curl -sf "http://127.0.0.1:$FE_PORT/api/health")
echo "$HEALTH_JSON" > "$RESULT_DIR/health.json"
if ! echo "$HEALTH_JSON" | grep -q '"status"'; then
  echo "[FAIL] /api/health 经前端代理未返回预期 JSON" | tee "$RESULT_FILE"
  exit 1
fi

# 6. 写结果
{
  echo "PASS"
  echo "timestamp: $TS"
  echo "backend_port: $BE_PORT"
  echo "frontend_port: $FE_PORT"
  echo "page_has_disclaimer: yes"
  echo "api_health_via_frontend: yes"
  echo "health_response: $HEALTH_JSON"
} > "$RESULT_FILE"

echo "[smoke] all checks passed, results in $RESULT_DIR"
exit 0
