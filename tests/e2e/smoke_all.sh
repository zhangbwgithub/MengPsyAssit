#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# T-S0.5  一键全链路冒烟脚本
#
# 流程：起后端(8660) → build 前端(dist缺失时) → 起前端 preview(5199)
#       → 串行上传三段合成音频 → 轮询至 done/failed → 断言汇总 → 落盘
#
# 用法（仓库根执行）：
#   DASHSCOPE_API_KEY=xxx .venv/bin/bash tests/e2e/smoke_all.sh
#
# 退出码：0 = 全部通过，1 = 断言失败，2 = 环境/启动失败
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── 常量 ──────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BE_PORT=8660
FE_PORT=5199
POLL_TIMEOUT=600       # 每段音频 10 分钟
POLL_INTERVAL=5        # 轮询间隔 5 秒
HEALTH_WAIT=60         # 后端就绪超时
FE_WAIT=30             # 前端就绪超时

TS="$(date +%Y%m%d_%H%M%S)"
RESULT_DIR="$ROOT/tests/e2e/results/smoke_all_${TS}"
mkdir -p "$RESULT_DIR"

# 隔离数据库 & 数据目录（不污染真实 data/）
DB_PATH="$RESULT_DIR/smoke.db"
AUDIO_STORE="$RESULT_DIR/audio_store"
mkdir -p "$AUDIO_STORE"
export DATABASE_URL="sqlite:///$DB_PATH"
export DATA_DIR="$AUDIO_STORE"
# PYTHONPATH 确保 psyapp 可导入（已 editable install，双保险）
export PYTHONPATH="$ROOT/app/backend/src${PYTHONPATH:+:$PYTHONPATH}"

AUDIO_DIR="$ROOT/tests/audio"
AUDIO_FILES=(
  "01_normal_dialogue.wav"
  "02_overlap_interruption.wav"
  "03_long_pauses.wav"
)

# ── 后台进程清理 ─────────────────────────────────────────────────────
BE_PID=""
FE_PID=""
cleanup() {
  echo "[smoke] cleanup: killing backend/frontend..."
  [ -n "${BE_PID:-}" ] && kill "$BE_PID" 2>/dev/null || true
  [ -n "${FE_PID:-}" ] && kill "$FE_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "[smoke] cleanup done"
}
trap cleanup EXIT

# ── 前置检查 ─────────────────────────────────────────────────────────
if [ -z "${DASHSCOPE_API_KEY:-}" ]; then
  echo "[FAIL] 环境缺少 DASHSCOPE_API_KEY" >&2
  exit 2
fi
if [ ! -f "$ROOT/.venv/bin/python" ]; then
  echo "[FAIL] .venv/bin/python 不存在" >&2
  exit 2
fi

echo "[smoke] start  ts=$TS"
echo "[smoke] results → $RESULT_DIR"

# ── 1. 启动后端 ──────────────────────────────────────────────────────
cd "$ROOT"
.venv/bin/python -m uvicorn psyapp.main:app \
  --port "$BE_PORT" --host 127.0.0.1 \
  > "$RESULT_DIR/backend.log" 2>&1 &
BE_PID=$!
echo "[smoke] backend PID=$BE_PID (port $BE_PORT)"

echo -n "[smoke] waiting backend "
for _i in $(seq 1 "$HEALTH_WAIT"); do
  if curl -sf "http://127.0.0.1:$BE_PORT/health" > /dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 1
  if [ "$_i" -eq "$HEALTH_WAIT" ]; then
    echo " ✗" >&2
    echo "[FAIL] backend /health not ready in ${HEALTH_WAIT}s" >&2
    exit 2
  fi
done

# ── 2. 构建前端（dist 缺失时）────────────────────────────────────────
FE_DIR="$ROOT/app/frontend"
if [ ! -d "$FE_DIR/dist" ] || [ -z "$(ls -A "$FE_DIR/dist" 2>/dev/null)" ]; then
  echo "[smoke] building frontend (dist missing)..."
  cd "$FE_DIR"
  npm run build > "$RESULT_DIR/frontend_build.log" 2>&1
  cd "$ROOT"
  echo "[smoke] frontend build done"
else
  echo "[smoke] frontend dist/ exists, skipping build"
fi

# ── 3. 启动前端 preview ──────────────────────────────────────────────
cd "$FE_DIR"
npm run preview > "$RESULT_DIR/frontend.log" 2>&1 &
FE_PID=$!
cd "$ROOT"
echo "[smoke] frontend PID=$FE_PID (port $FE_PORT)"

echo -n "[smoke] waiting frontend "
for _i in $(seq 1 "$FE_WAIT"); do
  if curl -sf "http://127.0.0.1:$FE_PORT/" > /dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 1
  if [ "$_i" -eq "$FE_WAIT" ]; then
    echo " ✗" >&2
    echo "[FAIL] frontend not ready in ${FE_WAIT}s" >&2
    exit 2
  fi
done

# ── 4. 健康检查经前端代理 ────────────────────────────────────────────
echo "[smoke] GET /api/health via frontend proxy..."
HEALTH_JSON="$(curl -sf "http://127.0.0.1:$FE_PORT/api/health")"
echo "$HEALTH_JSON" > "$RESULT_DIR/health_proxy.json"
if echo "$HEALTH_JSON" | jq -e '.status == "ok"' > /dev/null 2>&1; then
  echo "[smoke] /api/health via proxy ✓"
else
  echo "[FAIL] /api/health via proxy: $HEALTH_JSON" >&2
  exit 1
fi

# ── 5. 串行上传三段音频 ──────────────────────────────────────────────
declare -a ROWS=()
FAIL_COUNT=0

for AUDIO_FILE in "${AUDIO_FILES[@]}"; do
  AUDIO_PATH="$AUDIO_DIR/$AUDIO_FILE"
  TAG="${AUDIO_FILE%.wav}"
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "[smoke] >>> $AUDIO_FILE  ($(du -h "$AUDIO_PATH" | cut -f1))"
  echo "════════════════════════════════════════════════════════════"

  T_START="$(date +%s)"

  # 上传
  UPLOAD_JSON="$(curl -s -X POST "http://127.0.0.1:$BE_PORT/sessions" \
    -F "speaker_zero=T" \
    -F "file=@$AUDIO_PATH")"
  echo "$UPLOAD_JSON" > "$RESULT_DIR/upload_${TAG}.json"

  if [ "$(echo "$UPLOAD_JSON" | jq -r '.ok // false')" != "true" ]; then
    ERR_MSG="$(echo "$UPLOAD_JSON" | jq -r '.error.message // "unknown"')"
    echo "[FAIL] upload failed: $ERR_MSG" >&2
    ROWS+=("${AUDIO_FILE}|UPLOAD_FAIL|-|-|-")
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi

  SESSION_ID="$(echo "$UPLOAD_JSON" | jq -r '.data.session_id')"
  echo "[smoke] session_id=$SESSION_ID"

  # 轮询至终态
  STATUS=""
  DEADLINE="$(($(date +%s) + POLL_TIMEOUT))"
  while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    sleep "$POLL_INTERVAL"
    DETAIL_JSON="$(curl -s "http://127.0.0.1:$BE_PORT/sessions/$SESSION_ID")"
    STATUS="$(echo "$DETAIL_JSON" | jq -r '.data.status')"
    if [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ]; then
      break
    fi
    echo "[smoke]   …status=$STATUS"
  done

  T_END="$(date +%s)"
  ELAPSED="$((T_END - T_START))"
  echo "$DETAIL_JSON" > "$RESULT_DIR/final_${TAG}.json"

  if [ "$STATUS" != "done" ]; then
    echo "[FAIL] $AUDIO_FILE: status=$STATUS" >&2
    ROWS+=("${AUDIO_FILE}|${STATUS}|-|-|${ELAPSED}s")
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi

  # ── 断言 ──────────────────────────────────────────────────────
  SEG_COUNT="$(echo "$DETAIL_JSON" | jq '.data.segments | length')"
  SPEAKERS="$(echo "$DETAIL_JSON" | jq -r '[.data.segments[].speaker] | unique | sort | join("+")')"
  HAS_CT="$(echo "$DETAIL_JSON" | jq 'if .data.cleaned_text then true else false end')"
  HAS_SUM="$(echo "$DETAIL_JSON" | jq 'if .data.record.summary then true else false end')"
  HAS_CW="$(echo "$DETAIL_JSON" | jq 'if .data.record.counselor_work then true else false end')"

  ASSERT_OK=true
  [ "$SEG_COUNT" -lt 5 ]               && { echo "[FAIL] segments=$SEG_COUNT < 5"; ASSERT_OK=false; }
  ( echo "$SPEAKERS" | grep -q "T" && echo "$SPEAKERS" | grep -q "P" ) \
                                         || { echo "[FAIL] speakers=$SPEAKERS (need T+P)"; ASSERT_OK=false; }
  [ "$HAS_CT"  = "true" ]              || { echo "[FAIL] cleaned_text empty";               ASSERT_OK=false; }
  [ "$HAS_SUM" = "true" ]              || { echo "[FAIL] record.summary missing";            ASSERT_OK=false; }
  [ "$HAS_CW"  = "true" ]              || { echo "[FAIL] record.counselor_work missing";     ASSERT_OK=false; }

  if [ "$ASSERT_OK" = "true" ]; then
    ROWS+=("${AUDIO_FILE}|done|${SEG_COUNT}|${SPEAKERS}|${ELAPSED}s")
    echo "[PASS] ✓ seg=$SEG_COUNT sp=$SPEAKERS ${ELAPSED}s"
  else
    ROWS+=("${AUDIO_FILE}|DONE_ASSERT_FAIL|${SEG_COUNT}|${SPEAKERS}|${ELAPSED}s")
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done

# ── 6. 汇总表 ────────────────────────────────────────────────────────
echo ""
{
  echo "╔════════════════════════════════════════════════════════════════════╗"
  echo "║                     SMOKE ALL — SUMMARY                           ║"
  echo "╠════════════════════════════════════════════════════════════════════╣"
  printf "║  %-30s %-14s %5s  %-8s  %6s  ║\n" "Audio" "Status" "Seg" "Speaker" "Time"
  printf "║  %-30s %-14s %5s  %-8s  %6s  ║\n" "──────────────────────────────" "──────────────" "─────" "────────" "──────"
  for R in "${ROWS[@]}"; do
    IFS='|' read -r A S SP TP T <<< "$R"
    printf "║  %-30s %-14s %5s  %-8s  %6s  ║\n" "$A" "$S" "$SP" "$TP" "$T"
  done
  echo "╠════════════════════════════════════════════════════════════════════╣"
  if [ "$FAIL_COUNT" -eq 0 ]; then
    printf "║  RESULT: ALL PASSED (%d/%d)                                      ║\n" \
      "${#AUDIO_FILES[@]}" "${#AUDIO_FILES[@]}"
  else
    printf "║  RESULT: %d FAILED out of %d                                       ║\n" \
      "$FAIL_COUNT" "${#AUDIO_FILES[@]}"
  fi
  echo "╚════════════════════════════════════════════════════════════════════╝"
} | tee "$RESULT_DIR/summary.txt"

echo ""
echo "[smoke] 结果目录: $RESULT_DIR"
echo "[smoke] 落盘文件: $(ls "$RESULT_DIR" | tr '\n' ' ')"

# ── 退出 ─────────────────────────────────────────────────────────────
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
