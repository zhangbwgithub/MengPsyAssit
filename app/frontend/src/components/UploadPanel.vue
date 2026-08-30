<script setup>
import TranscriptBubbles from './TranscriptBubbles.vue'

const props = defineProps({
  selectedMode: { type: String, default: 'omni' },
  clientId: { type: [Number, String], default: '' },
  clients: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
  fileName: { type: String, default: '' },
  acceptedTypes: { type: String, default: '' },
  error: { type: String, default: '' },
  sessionStatus: { type: String, default: '' },
  sessionData: { type: Object, default: null },
  statusText: { type: String, default: '' },
  progressSteps: { type: Array, default: () => [] },
  bubbleSegments: { type: Array, default: () => [] },
  compactTranscript: { type: Boolean, default: false },
  showTimestamps: { type: Boolean, default: true },
  isDark: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:selectedMode',
  'update:clientId',
  'file-change',
  'upload',
  'reset',
  'retry',
])

function onModeChange(event) {
  emit('update:selectedMode', event.target.value)
}

function onClientChange(event) {
  emit('update:clientId', event.target.value)
}
</script>

<template>
  <div class="upload-tab">
    <!-- 上传卡 -->
    <section class="card upload-card">
      <h2>上传咨询录音</h2>

      <div class="mode-selector">
        <label class="mode-option" :class="{ selected: selectedMode === 'omni' }">
          <input
            type="radio"
            value="omni"
            :checked="selectedMode === 'omni'"
            :disabled="uploading"
            @change="onModeChange"
          />
          <span class="mode-option-body">
            <span class="mode-title">多模态直转（推荐）</span>
            <span class="mode-model">模型 <code>qwen3.5-omni-plus</code></span>
            <span class="mode-desc">音频直接听写+清理+角色判定，约 10 秒出稿</span>
          </span>
        </label>
        <label class="mode-option" :class="{ selected: selectedMode === 'asr' }">
          <input
            type="radio"
            value="asr"
            :checked="selectedMode === 'asr'"
            :disabled="uploading"
            @change="onModeChange"
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
            :disabled="uploading"
            @change="emit('file-change', $event)"
          />
          <span class="file-button">选择音频</span>
          <span class="file-name">{{ fileName || '未选择文件' }}</span>
        </label>
      </div>

      <div v-if="clients.length" class="form-row">
        <label class="client-pick">
          <span class="client-pick-label">来访者</span>
          <select
            :value="String(clientId || '')"
            :disabled="uploading"
            @change="onClientChange"
          >
            <option value="">不选择</option>
            <option v-for="c in clients" :key="c.client_id" :value="c.client_id">
              {{ c.name }}
            </option>
          </select>
        </label>
      </div>

      <div class="form-row">
        <button
          class="btn primary"
          :disabled="!fileName || uploading"
          @click="emit('upload')"
        >
          {{ uploading ? '处理中…' : '开始上传' }}
        </button>
        <button class="btn secondary" :disabled="uploading" @click="emit('reset')">
          重置
        </button>
      </div>

      <div v-if="progressSteps.length" class="progress-steps">
        <div v-for="(step, idx) in progressSteps" :key="idx" class="progress-step" :class="step.state">
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
        <button class="btn secondary small" @click="emit('retry')">重新上传</button>
      </div>
    </section>

    <!-- 转写气泡（处理中/处理完） -->
    <section v-if="bubbleSegments.length || (sessionData && !sessionData.segments?.length)" class="card dialogue-card">
      <h2>
        转写对话稿
        <span v-if="sessionData?.model_display" class="model-tag">
          {{ sessionData.model_display }}
        </span>
        <span v-if="compactTranscript && bubbleSegments.length" class="raw-tag">
          原始转写，正在按语义清理…
        </span>
      </h2>
      <p v-if="!bubbleSegments.length" class="dialogue-empty">正在处理，暂无转写内容…</p>
      <TranscriptBubbles
        v-else
        :segments="bubbleSegments"
        :is-dark="isDark"
        :show-timestamps="showTimestamps"
        :compact="compactTranscript"
      />
    </section>
  </div>
</template>

<style scoped>
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
  border-bottom: 1px solid var(--border-subtle);
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
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  background: var(--card);
  transition: border-color 0.2s, background 0.2s;
}

.mode-option.selected {
  border-color: var(--primary);
  background: var(--hover);
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
  background: var(--primary-soft);
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
  background: var(--primary-soft);
  border-radius: 999px;
  padding: 2px 8px;
  vertical-align: middle;
}

.raw-tag {
  margin-left: 8px;
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--muted);
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
  color: var(--on-primary);
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.95rem;
}

.file-name {
  color: var(--muted);
  font-size: 0.9rem;
  word-break: break-all;
}

.client-pick {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.client-pick-label {
  font-size: 0.85rem;
  color: var(--muted);
}

.client-pick select {
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 0.9rem;
  cursor: pointer;
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
  color: var(--on-primary);
}

.btn.secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border-subtle);
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.85rem;
}

.status-box {
  margin-top: 14px;
  padding: 12px;
  background: var(--surface);
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
  background: var(--surface);
  color: var(--muted);
  font-size: 0.85rem;
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
}

.progress-step.active {
  background: var(--primary-soft);
  color: var(--primary-dark);
  font-weight: 600;
}

.progress-step.active .progress-dot {
  background: var(--primary);
}

.progress-step.done {
  background: var(--ok-bg);
  color: var(--ok-text);
}

.progress-step.done .progress-dot {
  background: #34b27b;
}

.progress-step.failed {
  background: var(--danger-soft);
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
  border: 2px solid var(--border);
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
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  border-radius: 8px;
  color: var(--danger);
}

.error-box p {
  margin: 0 0 10px;
}

.dialogue-empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}

@media (max-width: 480px) {
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
}
</style>
