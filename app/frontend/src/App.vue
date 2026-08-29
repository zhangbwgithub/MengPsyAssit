<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 支持的音频扩展名（与后端校验保持一致）
const ALLOWED_EXTS = ['.wav', '.m4a', '.mp3', '.opus', '.flac']

// 每人一色调色板（按代号首现序分配；浅背景 + 同色系边框 + 深色文字）
const SPEAKER_PALETTE = [
  { bg: '#eef4ff', border: '#b7d0fb', text: '#1e409e' }, // 蓝
  { bg: '#e8f7f0', border: '#a9e2c6', text: '#146c4b' }, // 绿
  { bg: '#fdf4e3', border: '#f2d49b', text: '#8f5a12' }, // 琥珀
  { bg: '#f1eefb', border: '#cfc2f2', text: '#5b3bb0' }, // 紫
  { bg: '#fcecf0', border: '#f4bdcb', text: '#9c2f4f' }, // 玫红
  { bg: '#e7f6fa', border: '#b2e2ee', text: '#0f6b79' }, // 青
]

const file = ref(null)
const fileName = ref('')
const uploading = ref(false)
const error = ref('')
const sessionId = ref(null)
const sessionStatus = ref('')
const sessionData = ref(null)
const pollTimer = ref(null)
// T-S1.10：上传/轮询超时与在途护栏
const UPLOAD_TIMEOUT_MS = 300 * 1000 // 局域网大文件上传留余量
const POLL_TIMEOUT_MS = 10 * 1000
const POLL_MAX_CONSECUTIVE_FAILURES = 3
const pollingInFlight = ref(false)
const pollFailures = ref(0)
// T-S1.6：上传可选管线模式；默认多模态直转（推荐）
const selectedMode = ref('omni')

// T-S1.10：左侧上传/分析记录看板
const sessions = ref([])
const boardLoading = ref(false)
const boardError = ref('')
const activeSessionId = ref(null)

const acceptedTypes = ALLOWED_EXTS.join(',')

// 管线模式：会话详情返回后以服务端 pipeline_mode 为准，未返回前用用户选择
const pipelineMode = computed(
  () => sessionData.value?.pipeline_mode || selectedMode.value
)

const statusText = computed(() => {
  const map = {
    uploading: '正在上传音频…',
    transcribing:
      pipelineMode.value === 'omni'
        ? '正在多模态直转与生成记录…'
        : '正在转写与生成记录…',
    done: '处理完成',
    failed: '处理失败',
  }
  return map[sessionStatus.value] || sessionStatus.value || '等待上传'
})

// 进度条按模式自适应：omni 两阶段「多模态直转 → 生成记录」；asr 维持三阶段。
// segments 为空 → 阶段1；有 segments 无 record 且未 done → 阶段2；
// 有 record → 末阶段；done → 全部点亮。failed 按同规则定位失败阶段。
const progressLabels = computed(() =>
  pipelineMode.value === 'omni'
    ? ['多模态直转', '生成记录']
    : ['转写', '清理与角色判定', '生成记录']
)

const pipelineStage = computed(() => {
  const count = progressLabels.value.length
  if (sessionStatus.value === 'done') return count
  const data = sessionData.value
  if (!data || !data.segments?.length) return 1
  if (!data.record && sessionStatus.value !== 'done') return 2
  if (data.record) return count
  return 1
})

const progressSteps = computed(() => {
  if (!sessionStatus.value) return []
  const stage = pipelineStage.value
  const failed = sessionStatus.value === 'failed'
  return progressLabels.value.map((label, idx) => {
    const num = idx + 1
    let state = 'pending'
    if (sessionStatus.value === 'done') {
      state = 'done'
    } else if (failed) {
      if (num < stage) state = 'done'
      else if (num === stage) state = 'failed'
    } else if (num < stage) {
      state = 'done'
    } else if (num === stage) {
      state = 'active'
    }
    return { label, state }
  })
})

// 阶段2（有 segments、尚未判定角色）时使用紧凑气泡显示原始转写
const hasRoleAssignments = computed(() => {
  const segments = sessionData.value?.segments || []
  return segments.length > 0 && segments.some((seg) => seg.role)
})

const compactTranscript = computed(() => {
  if (!sessionData.value?.segments?.length) return false
  if (sessionStatus.value === 'done' || sessionStatus.value === 'failed') return false
  return pipelineStage.value === 2 && !hasRoleAssignments.value
})

function onFileChange(event) {
  const chosen = event.target.files?.[0]
  if (!chosen) return
  const ext = '.' + chosen.name.split('.').pop().toLowerCase()
  if (!ALLOWED_EXTS.includes(ext)) {
    error.value = `仅支持 ${ALLOWED_EXTS.join(' / ')} 音频文件`
    file.value = null
    fileName.value = ''
    return
  }
  file.value = chosen
  fileName.value = chosen.name
  error.value = ''
}

async function upload() {
  if (!file.value) {
    error.value = '请先选择音频文件'
    return
  }
  error.value = ''
  uploading.value = true
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('mode', selectedMode.value)
    const res = await fetch('/api/sessions', {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '上传失败')
    }
    sessionId.value = json.data.session_id
    activeSessionId.value = json.data.session_id
    sessionStatus.value = json.data.status
    loadSessions()
    startPolling()
  } catch (err) {
    if (err.name === 'AbortError') {
      error.value = '上传请求超时，请检查网络后重试'
    } else {
      error.value = err.message || '上传请求失败'
    }
    uploading.value = false
  } finally {
    clearTimeout(timeout)
  }
}

function startPolling() {
  stopPolling()
  pollingInFlight.value = false
  pollFailures.value = 0
  pollTimer.value = setInterval(() => {
    // T-S1.10：在途护栏——上一个轮询未结束时跳过，不叠加请求
    if (pollingInFlight.value) return
    pollOnce()
  }, 3000)
}

async function pollOnce() {
  const currentId = sessionId.value
  if (!currentId || pollingInFlight.value) return
  pollingInFlight.value = true
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), POLL_TIMEOUT_MS)
  try {
    const res = await fetch(`/api/sessions/${currentId}`, {
      signal: controller.signal,
    })
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '查询失败')
    }
    pollFailures.value = 0
    sessionData.value = json.data
    sessionStatus.value = json.data.status
    if (['done', 'failed'].includes(json.data.status)) {
      stopPolling()
      uploading.value = false
      loadSessions()
    }
  } catch (err) {
    pollFailures.value += 1
    if (pollFailures.value >= POLL_MAX_CONSECUTIVE_FAILURES) {
      stopPolling()
      uploading.value = false
      error.value = '查询会话状态失败，请刷新页面或点击重试'
    }
  } finally {
    clearTimeout(timeout)
    pollingInFlight.value = false
  }
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
  pollingInFlight.value = false
}

function reset() {
  stopPolling()
  file.value = null
  fileName.value = ''
  uploading.value = false
  error.value = ''
  sessionId.value = null
  activeSessionId.value = null
  sessionStatus.value = ''
  sessionData.value = null
}

function retry() {
  // 重试入口：清空状态，保留文件便于重新上传
  const keptFile = file.value
  reset()
  file.value = keptFile
  fileName.value = keptFile?.name || ''
}

// T-S1.10：看板列表加载 / 点击回看
async function loadSessions() {
  boardLoading.value = true
  boardError.value = ''
  try {
    const res = await fetch('/api/sessions')
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '加载记录失败')
    }
    sessions.value = json.data?.sessions || []
  } catch (err) {
    boardError.value = err.message || '加载记录失败'
  } finally {
    boardLoading.value = false
  }
}

const isActiveSession = (id) => activeSessionId.value === id

const boardStatusClass = (status) => {
  if (status === 'done') return 'done'
  if (status === 'failed') return 'failed'
  return 'processing'
}

const boardStatusText = (status) => {
  if (status === 'done') return '完成'
  if (status === 'failed') return '失败'
  return '处理中'
}

function formatStartedAt(value) {
  if (!value) return '—'
  // 后端 started_at 为 naive UTC（无时区后缀），JS 会把无后缀串当本地时间；
  // 显式补 'Z' 使 new Date 按 UTC 解析，再转浏览器本地时区输出。
  const date = new Date(`${value}Z`)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function selectSession(id) {
  if (sessionId.value === id && sessionStatus.value) return
  stopPolling()
  uploading.value = false
  error.value = ''
  activeSessionId.value = id
  sessionStatus.value = ''
  sessionData.value = null
  try {
    const res = await fetch(`/api/sessions/${id}`)
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '加载会话失败')
    }
    sessionId.value = id
    sessionData.value = json.data
    sessionStatus.value = json.data.status || ''
    if (json.data.status === 'done' || json.data.status === 'failed') {
      return
    }
    startPolling()
  } catch (err) {
    error.value = err.message || '加载会话失败'
    sessionId.value = null
    activeSessionId.value = null
  }
}

function formatMs(ms) {
  const totalSeconds = Math.floor((ms || 0) / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// 气泡列表单一来源：segments；文本优先 cleaned_content，无则 content
const bubbleSegments = computed(() => {
  const segments = sessionData.value?.segments || []
  return segments.map((seg) => ({
    ...seg,
    bubbleText: seg.cleaned_content ?? seg.content ?? '',
  }))
})

// 按代号首现序建立「代号 → 调色板颜色」映射（每人一色）
const speakerColors = computed(() => {
  const map = {}
  for (const seg of sessionData.value?.segments || []) {
    if (seg.speaker && !(seg.speaker in map)) {
      map[seg.speaker] =
        SPEAKER_PALETTE[Object.keys(map).length % SPEAKER_PALETTE.length]
    }
  }
  return map
})

function colorOf(speaker) {
  return (
    speakerColors.value[speaker] || {
      bg: '#f3f4f6',
      border: '#d1d5db',
      text: '#374151',
    }
  )
}

function styleOf(seg) {
  const color = colorOf(seg.speaker)
  return {
    backgroundColor: color.bg,
    borderColor: color.border,
    color: color.text,
  }
}

function labelOf(seg) {
  if (seg.role_label) return seg.role_label
  return `说话人 ${seg.speaker || '?'}`
}

// role=T 靠左、role=P 靠右；未判定按代号奇偶交替左右（A=0 左、B=1 右…）。
// 未知代号 U 的字母序号 20 为偶数，自然靠左；非 A-Z 代号兜底按偶数靠左。
function speakerIndex(speaker) {
  const code = String(speaker || '').toUpperCase()
  const idx = code.charCodeAt(0) - 65
  return idx >= 0 && idx <= 25 ? idx : 0
}

function alignClassOf(seg) {
  if (seg.role === 'T') return 'align-left'
  if (seg.role === 'P') return 'align-right'
  return speakerIndex(seg.speaker) % 2 === 0 ? 'align-left' : 'align-right'
}

// omni 直转无时间戳，气泡头不渲染时间行
const showTimestamps = computed(() => pipelineMode.value !== 'omni')

const metaInfoText = computed(() => {
  const info = sessionData.value?.record?.basic_info
  if (!info) return ''
  const parts = []
  if (sessionData.value?.model_display) {
    parts.push(`处理管线：${sessionData.value.model_display}`)
  }
  if (info.model) parts.push(`模型：${info.model}`)
  if (info.prompt_version) parts.push(`提示词版本：${info.prompt_version}`)
  if (info.session_id) parts.push(`会话编号：#${info.session_id}`)
  return parts.join(' · ')
})

onMounted(loadSessions)
onUnmounted(stopPolling)
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>咨询记录助手</h1>
      <p class="subtitle">录音 → 转写 → 清理 → 客观记录</p>
    </header>

    <main class="container dashboard">
      <!-- 左侧：上传与分析记录看板 -->
      <aside class="board">
        <div class="board-header">
          <h2>上传与记录</h2>
          <button
            class="btn board-refresh"
            type="button"
            @click="loadSessions"
            :disabled="boardLoading"
          >
            {{ boardLoading ? '刷新中…' : '刷新' }}
          </button>
        </div>

        <div v-if="boardError" class="board-error">{{ boardError }}</div>

        <p v-if="sessions.length === 0" class="board-empty">暂无记录</p>

        <ul v-else class="board-list">
          <li
            v-for="s in sessions"
            :key="s.session_id"
            class="board-item"
            :class="{ active: isActiveSession(s.session_id) }"
            @click="selectSession(s.session_id)"
          >
            <span class="board-id">#{{ s.session_id }}</span>
            <span class="board-badge" :class="boardStatusClass(s.status)">
              <span
                v-if="s.status !== 'done' && s.status !== 'failed'"
                class="board-spinner"
              ></span>
              {{ boardStatusText(s.status) }}
            </span>
            <span class="board-time">{{ formatStartedAt(s.started_at) }}</span>
          </li>
        </ul>
      </aside>

      <!-- 右侧：上传区 / 对话稿区 / 结果区 -->
      <div class="main-panel">
      <!-- 上传区 -->
      <section class="card upload-card">
        <h2>1. 上传咨询录音</h2>

        <div class="mode-selector">
          <label
            class="mode-option"
            :class="{ selected: selectedMode === 'omni' }"
          >
            <input
              type="radio"
              value="omni"
              v-model="selectedMode"
              :disabled="uploading"
            />
            <span class="mode-option-body">
              <span class="mode-title">多模态直转（推荐）</span>
              <span class="mode-model">模型 <code>qwen3.5-omni-plus</code></span>
              <span class="mode-desc">音频直接听写+清理+角色判定，约 10 秒出稿</span>
            </span>
          </label>
          <label
            class="mode-option"
            :class="{ selected: selectedMode === 'asr' }"
          >
            <input
              type="radio"
              value="asr"
              v-model="selectedMode"
              :disabled="uploading"
            />
            <span class="mode-option-body">
              <span class="mode-title">ASR + LLM 管线</span>
              <span class="mode-model">
                ASR <code>paraformer-v2</code> · 清理 <code>deepseek-v4-flash</code>
              </span>
              <span class="mode-desc">带时间戳，实时录音场景（未来）</span>
            </span>
          </label>
        </div>

        <div class="form-row">
          <label class="file-input">
            <input
              type="file"
              :accept="acceptedTypes"
              @change="onFileChange"
              :disabled="uploading"
            />
            <span class="file-button">选择音频</span>
            <span class="file-name">{{ fileName || '未选择文件' }}</span>
          </label>
        </div>

        <div class="form-row">
          <button
            class="btn primary"
            @click="upload"
            :disabled="!file || uploading"
          >
            {{ uploading ? '处理中…' : '开始上传' }}
          </button>
          <button class="btn secondary" @click="reset" :disabled="uploading">
            重置
          </button>
        </div>

        <div v-if="progressSteps.length" class="progress-steps">
          <div
            v-for="(step, idx) in progressSteps"
            :key="idx"
            class="progress-step"
            :class="step.state"
          >
            <span class="progress-dot"></span>
            <span class="progress-label">{{ step.label }}</span>
          </div>
        </div>

        <div v-if="sessionStatus" class="status-box">
          <span class="status-label">当前状态：</span>
          <span class="status-value">{{ statusText }}</span>
          <span
            v-if="sessionStatus !== 'done' && sessionStatus !== 'failed'"
            class="spinner"
          ></span>
        </div>

        <div v-if="error" class="error-box">
          <p>{{ error }}</p>
          <button class="btn secondary small" @click="retry">重新上传</button>
        </div>
      </section>

      <!-- 对话稿区 -->
      <section class="card dialogue-card" v-if="bubbleSegments.length">
        <h2>
          2. 转写对话稿
          <span v-if="sessionData?.model_display" class="model-tag">
            {{ sessionData.model_display }}
          </span>
          <span v-if="compactTranscript" class="raw-tag">原始转写，正在按语义清理…</span>
        </h2>
        <div class="segments">
          <div
            v-for="seg in bubbleSegments"
            :key="seg.seq"
            class="segment"
            :class="[alignClassOf(seg), { compact: compactTranscript }]"
          >
            <div class="bubble" :class="{ compact: compactTranscript }" :style="styleOf(seg)">
              <div v-if="!compactTranscript" class="bubble-header">
                <span class="speaker-label">{{ labelOf(seg) }}</span>
                <span v-if="showTimestamps" class="time">
                  #{{ seg.seq }} · {{ formatMs(seg.start_ms) }}
                </span>
              </div>
              <div v-else class="compact-label">说话人 {{ seg.speaker || '?' }}</div>
              <p class="content">{{ seg.bubbleText }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- 结果区 -->
      <section class="card result-card" v-if="sessionData?.status === 'done'">
        <h2>3. 处理结果</h2>

        <div class="result-block" v-if="sessionData.record">
          <h3>咨询记录</h3>
          <div class="record-card">
            <div class="record-item" v-if="sessionData.record.summary">
              <span class="record-key">概述</span>
              <p>{{ sessionData.record.summary }}</p>
            </div>
            <div class="record-item" v-if="sessionData.record.counselor_work">
              <span class="record-key">咨询师的工作</span>
              <p>{{ sessionData.record.counselor_work }}</p>
            </div>
            <div class="record-item" v-if="sessionData.record.client_reported_topics?.length">
              <span class="record-key">来访者话题</span>
              <ul class="tag-list">
                <li v-for="(topic, idx) in sessionData.record.client_reported_topics" :key="idx">
                  {{ topic }}
                </li>
              </ul>
            </div>
            <div class="record-item" v-if="sessionData.record.basic_info">
              <span class="record-key">其他信息</span>
              <p class="meta-info">{{ metaInfoText }}</p>
            </div>
          </div>
        </div>
      </section>
      </div>
    </main>

    <footer class="footer">
      <p>AI 生成内容仅供专业参考</p>
    </footer>
  </div>
</template>

<style>
/* 基础重置与变量 */
* {
  box-sizing: border-box;
}

:root {
  --bg: #f5f7fa;
  --card: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --primary: #2563eb;
  --primary-dark: #1d4ed8;
  --danger: #dc2626;
  --radius: 12px;
  --shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  text-align: center;
  padding: 24px 16px 8px;
}

.header h1 {
  margin: 0;
  font-size: 1.75rem;
  color: var(--primary-dark);
}

.subtitle {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 0.95rem;
}

.container {
  flex: 1;
  max-width: 1120px;
  width: 100%;
  margin: 0 auto;
  padding: 16px;
}

.dashboard {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.main-panel {
  flex: 1;
  min-width: 0;
}

/* 左侧上传/分析记录看板 */
.board {
  flex: 0 0 260px;
  width: 260px;
  position: sticky;
  top: 16px;
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
}

.board-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.board-header h2 {
  margin: 0;
  font-size: 1rem;
  border-bottom: none;
  padding-bottom: 0;
}

.btn.board-refresh {
  padding: 4px 10px;
  font-size: 0.8rem;
  background: var(--primary);
  color: #fff;
}

.board-error {
  margin-bottom: 10px;
  padding: 8px 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: var(--danger);
  font-size: 0.8rem;
}

.board-empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.board-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.board-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.board-item:hover {
  border-color: #bfdbfe;
  background: #f5f9ff;
}

.board-item.active {
  border-color: var(--primary);
  background: #f5f9ff;
}

.board-id {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--primary-dark);
}

.board-time {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.75rem;
  white-space: nowrap;
}

.board-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  white-space: nowrap;
}

.board-badge.done {
  background: #e8f7f0;
  color: #146c4b;
}

.board-badge.failed {
  background: #fef2f2;
  color: var(--danger);
}

.board-badge.processing {
  background: #e8f1ff;
  color: var(--primary-dark);
}

.board-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(0, 0, 0, 0.12);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  margin-bottom: 16px;
}

.card h2 {
  margin: 0 0 16px;
  font-size: 1.15rem;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 8px;
}

.form-row {
  margin-bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.mode-selector {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.mode-option {
  flex: 1 1 240px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.2s, background 0.2s;
}

.mode-option.selected {
  border-color: var(--primary);
  background: #f5f9ff;
}

.mode-option input[type='radio'] {
  margin-top: 3px;
  accent-color: var(--primary);
}

.mode-option-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mode-title {
  font-weight: 600;
  font-size: 0.95rem;
}

.mode-model {
  color: var(--primary-dark);
  font-size: 0.82rem;
}

.mode-model code {
  background: #eef2ff;
  border-radius: 4px;
  padding: 1px 4px;
}

.mode-desc {
  color: var(--muted);
  font-size: 0.8rem;
}

.model-tag {
  margin-left: 8px;
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--primary-dark);
  background: #eef2ff;
  border-radius: 999px;
  padding: 2px 8px;
  vertical-align: middle;
}

.file-input {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.file-input input[type='file'] {
  display: none;
}

.file-button {
  background: var(--primary);
  color: #fff;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.95rem;
}

.file-name {
  color: var(--muted);
  font-size: 0.9rem;
  word-break: break-all;
}

.btn {
  border: none;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn.primary {
  background: var(--primary);
  color: #fff;
}

.btn.secondary {
  background: #e5e7eb;
  color: var(--text);
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.85rem;
}

.status-box {
  margin-top: 14px;
  padding: 12px;
  background: #f3f4f6;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-steps {
  margin-top: 14px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.progress-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--muted);
  font-size: 0.85rem;
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
}

.progress-step.active {
  background: #e8f1ff;
  color: var(--primary-dark);
  font-weight: 600;
}

.progress-step.active .progress-dot {
  background: var(--primary);
}

.progress-step.done {
  background: #e8f7f0;
  color: #146c4b;
}

.progress-step.done .progress-dot {
  background: #34b27b;
}

.progress-step.failed {
  background: #fef2f2;
  color: var(--danger);
  font-weight: 600;
}

.progress-step.failed .progress-dot {
  background: var(--danger);
}

.status-label {
  color: var(--muted);
  font-size: 0.9rem;
}

.status-value {
  font-weight: 600;
  color: var(--text);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #d1d5db;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-box {
  margin-top: 14px;
  padding: 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: var(--danger);
}

.error-box p {
  margin: 0 0 10px;
}

.segments {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.segment {
  display: flex;
}

.segment.align-left {
  justify-content: flex-start;
}

.segment.align-right {
  justify-content: flex-end;
}

.bubble {
  max-width: 85%;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid transparent;
}

.align-right .bubble {
  border-top-left-radius: 16px;
  border-top-right-radius: 4px;
}

.align-left .bubble {
  border-top-left-radius: 4px;
  border-top-right-radius: 16px;
}

.bubble-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.speaker-label {
  font-weight: 600;
  font-size: 0.85rem;
  color: inherit;
}

.time {
  color: var(--muted);
  font-size: 0.75rem;
}

.content {
  margin: 0;
  font-size: 0.95rem;
  color: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 转写中间态（阶段2、未判定角色）紧凑显示 */
.raw-tag {
  margin-left: 8px;
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--muted);
  vertical-align: middle;
}

.segment.compact {
  width: 100%;
}

.bubble.compact {
  width: 100%;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 8px;
}

.compact-label {
  font-size: 0.72rem;
  font-weight: 600;
  opacity: 0.75;
  margin-bottom: 2px;
  color: inherit;
}

.result-block {
  margin-bottom: 18px;
}

.result-block h3 {
  margin: 0 0 10px;
  font-size: 1rem;
  color: var(--muted);
}

.record-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
}

.record-item {
  margin-bottom: 14px;
}

.record-item:last-child {
  margin-bottom: 0;
}

.record-key {
  display: block;
  font-weight: 600;
  color: var(--primary-dark);
  margin-bottom: 4px;
  font-size: 0.9rem;
}

.record-item p {
  margin: 0;
  font-size: 0.95rem;
}

.meta-info {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
}

.tag-list {
  margin: 0;
  padding-left: 18px;
  font-size: 0.95rem;
}

.footer {
  text-align: center;
  padding: 16px;
  color: var(--muted);
  font-size: 0.85rem;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}

/* 响应式：看板加宽断点，窄屏纵向堆叠 */
@media (max-width: 767px) {
  .dashboard {
    flex-direction: column;
  }

  .board {
    flex: 1 1 auto;
    width: 100%;
    position: static;
  }
}

@media (max-width: 480px) {
  .header h1 {
    font-size: 1.45rem;
  }

  .card {
    padding: 16px;
  }

  .form-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .btn {
    width: 100%;
  }

  .bubble {
    max-width: 92%;
  }
}
</style>
