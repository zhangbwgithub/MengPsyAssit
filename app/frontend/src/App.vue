<script setup>
import { ref, computed, onUnmounted } from 'vue'

// 支持的音频扩展名（与后端校验保持一致）
const ALLOWED_EXTS = ['.wav', '.m4a', '.mp3', '.opus', '.flac']

const file = ref(null)
const fileName = ref('')
const speakerZero = ref('T')
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
    form.append('speaker_zero', speakerZero.value)
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

function splitCleanedText(text) {
  if (!text) return []
  return text.split('\n').filter((line) => line.trim().length > 0)
}

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

        <div class="form-row speaker-row">
          <span class="label">说话人 0 映射：</span>
          <label class="radio">
            <input
              type="radio"
              value="T"
              v-model="speakerZero"
              :disabled="uploading"
            />
            咨询师（T）
          </label>
          <label class="radio">
            <input
              type="radio"
              value="P"
              v-model="speakerZero"
              :disabled="uploading"
            />
            来访者（P）
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
      <section class="card dialogue-card" v-if="sessionData?.segments?.length">
        <h2>2. 转写对话稿</h2>
        <div class="segments">
          <div
            v-for="seg in sessionData.segments"
            :key="seg.seq"
            class="segment"
            :class="{ 'speaker-t': seg.speaker === 'T', 'speaker-p': seg.speaker === 'P' }"
          >
            <div class="bubble">
              <div class="bubble-header">
                <span class="speaker-label">{{ seg.speaker === 'T' ? '咨询师 T' : '来访者 P' }}</span>
                <span class="time">#{{ seg.seq }} · {{ formatMs(seg.start_ms) }}</span>
              </div>
              <p class="content">{{ seg.content }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- 结果区 -->
      <section class="card result-card" v-if="sessionData?.status === 'done'">
        <h2>3. 处理结果</h2>

        <div class="result-block" v-if="sessionData.cleaned_text">
          <h3>清理后文本</h3>
          <div class="cleaned-text">
            <p v-for="(line, idx) in splitCleanedText(sessionData.cleaned_text)" :key="idx">
              {{ line }}
            </p>
          </div>
        </div>

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
              <pre>{{ JSON.stringify(sessionData.record.basic_info, null, 2) }}</pre>
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
  --t-color: #2563eb;
  --t-bg: #eff6ff;
  --p-color: #059669;
  --p-bg: #ecfdf5;
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

.label {
  font-weight: 500;
  color: var(--text);
}

.radio {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 0.95rem;
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

.segment.speaker-t {
  justify-content: flex-start;
}

.segment.speaker-p {
  justify-content: flex-end;
}

.bubble {
  max-width: 80%;
  padding: 12px 14px;
  border-radius: 16px;
  border-top-left-radius: 4px;
}

.speaker-t .bubble {
  background: var(--t-bg);
  border: 1px solid #bfdbfe;
}

.speaker-p .bubble {
  background: var(--p-bg);
  border: 1px solid #a7f3d0;
  border-top-left-radius: 16px;
  border-top-right-radius: 4px;
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
}

.speaker-t .speaker-label {
  color: var(--t-color);
}

.speaker-p .speaker-label {
  color: var(--p-color);
}

.time {
  color: var(--muted);
  font-size: 0.75rem;
}

.content {
  margin: 0;
  font-size: 0.95rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.result-block {
  margin-bottom: 18px;
}

.result-block h3 {
  margin: 0 0 10px;
  font-size: 1rem;
  color: var(--muted);
}

.cleaned-text {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
  font-size: 0.95rem;
  white-space: pre-wrap;
}

.cleaned-text p {
  margin: 0 0 6px;
}

.cleaned-text p:last-child {
  margin-bottom: 0;
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

.record-item pre {
  margin: 0;
  font-size: 0.85rem;
  background: #fff;
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
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
