<script setup>
import { ref, computed, onUnmounted } from 'vue'

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

const acceptedTypes = ALLOWED_EXTS.join(',')

const statusText = computed(() => {
  const map = {
    uploading: '正在上传音频…',
    transcribing: '正在转写与生成记录…',
    done: '处理完成',
    failed: '处理失败',
  }
  return map[sessionStatus.value] || sessionStatus.value || '等待上传'
})

// 三阶段进度条（纯前端推导，不加接口）：
// segments 为空 → 阶段1；有 segments 无 record 且未 done → 阶段2；
// 有 record → 阶段3；done → 全部点亮。failed 按同规则定位失败阶段。
const PROGRESS_STEP_LABELS = ['转写', '清理与角色判定', '生成记录']

const pipelineStage = computed(() => {
  if (sessionStatus.value === 'done') return 3
  const data = sessionData.value
  if (!data || !data.segments?.length) return 1
  if (!data.record && sessionStatus.value !== 'done') return 2
  if (data.record) return 3
  return 1
})

const progressSteps = computed(() => {
  if (!sessionStatus.value) return []
  const stage = pipelineStage.value
  const failed = sessionStatus.value === 'failed'
  return PROGRESS_STEP_LABELS.map((label, idx) => {
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
  try {
    const form = new FormData()
    form.append('file', file.value)
    const res = await fetch('/api/sessions', { method: 'POST', body: form })
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '上传失败')
    }
    sessionId.value = json.data.session_id
    sessionStatus.value = json.data.status
    startPolling()
  } catch (err) {
    error.value = err.message || '上传请求失败'
    uploading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer.value = setInterval(async () => {
    try {
      const res = await fetch(`/api/sessions/${sessionId.value}`)
      const json = await res.json()
      if (!json.ok) {
        throw new Error(json.error?.message || '查询失败')
      }
      sessionData.value = json.data
      sessionStatus.value = json.data.status
      if (['done', 'failed'].includes(json.data.status)) {
        stopPolling()
        uploading.value = false
      }
    } catch (err) {
      error.value = err.message || '轮询失败'
      stopPolling()
      uploading.value = false
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

function reset() {
  stopPolling()
  file.value = null
  fileName.value = ''
  uploading.value = false
  error.value = ''
  sessionId.value = null
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

const metaInfoText = computed(() => {
  const info = sessionData.value?.record?.basic_info
  if (!info) return ''
  const parts = []
  if (info.model) parts.push(`模型：${info.model}`)
  if (info.prompt_version) parts.push(`提示词版本：${info.prompt_version}`)
  if (info.session_id) parts.push(`会话编号：#${info.session_id}`)
  return parts.join(' · ')
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>咨询记录助手</h1>
      <p class="subtitle">录音 → 转写 → 清理 → 客观记录</p>
    </header>

    <main class="container">
      <!-- 上传区 -->
      <section class="card upload-card">
        <h2>1. 上传咨询录音</h2>
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
                <span class="time">#{{ seg.seq }} · {{ formatMs(seg.start_ms) }}</span>
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
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
  padding: 16px;
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

/* 响应式：窄屏纵向堆叠 */
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
