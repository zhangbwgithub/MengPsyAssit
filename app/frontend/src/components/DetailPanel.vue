<script setup>
import { ref, computed, watch } from 'vue'
import TranscriptBubbles from './TranscriptBubbles.vue'
import TranscriptTable from './TranscriptTable.vue'
import { styleOf, labelOf, speakerColorMap } from '../utils/speakers.js'
import {
  formatStartedAtFull,
  durationMMSS,
} from '../utils/format.js'

const props = defineProps({
  session: { type: Object, default: null }, // 列表元数据 + 详情合并
  groupName: { type: String, default: '' },
  clients: { type: Array, default: () => [] },
  isDark: { type: Boolean, default: false },
  showTimestamps: { type: Boolean, default: true },
})

const emit = defineEmits(['save-brief', 'save-tags', 'save-segment', 'assign-client'])

const viewMode = ref('bubble') // bubble | table
const collapsedBlocks = ref({})
const editOpen = ref(false)
const editType = ref('brief')
const editBriefValue = ref('')
const editTagsValue = ref('')
const editError = ref('')
const successHint = ref('')

watch(
  () => props.session?.session_id,
  () => {
    editOpen.value = false
    editError.value = ''
    successHint.value = ''
    viewMode.value = 'bubble'
  }
)

const segments = computed(() => props.session?.segments || [])

const record = computed(() => props.session?.record || null)

const summaryDisplay = computed(() => {
  const brief = props.session?.brief || ''
  if (brief) return brief.slice(0, 100)
  return (record.value?.summary || '').slice(0, 100)
})

const sessionTags = computed(() => props.session?.tags || [])

const statusText = computed(() => {
  const s = props.session?.status
  if (s === 'done') return '完成'
  if (s === 'failed') return '失败'
  if (s) return '处理中'
  return '—'
})

const wordCount = computed(() => props.session?.word_count ?? 0)

const colorMap = computed(() => speakerColorMap(segments.value, props.isDark))

function segStyle(seg) {
  return styleOf(colorMap.value, seg, props.isDark)
}

function segLabel(seg) {
  return labelOf(seg)
}

function toggleBlock(name) {
  collapsedBlocks.value[name] = !collapsedBlocks.value[name]
}

function openEditPanel(type) {
  editOpen.value = true
  editType.value = type
  editError.value = ''
  if (type === 'brief') {
    editBriefValue.value = (props.session?.brief || '').slice(0, 100)
  } else {
    editTagsValue.value = sessionTags.value.join(', ')
  }
}

function cancelEdit() {
  editOpen.value = false
  editError.value = ''
}

async function saveEdit() {
  editError.value = ''
  successHint.value = ''
  try {
    if (editType.value === 'brief') {
      const brief = editBriefValue.value.replace(/\s+$/, '')
      if (brief.length > 100) {
        editError.value = '摘要不能超过 100 字'
        return
      }
      await emit('save-brief', brief)
    } else {
      const tags = (editTagsValue.value || '')
        .split(/[,，]/)
        .map((t) => t.trim())
        .filter(Boolean)
      await emit('save-tags', tags)
    }
    editOpen.value = false
    successHint.value = editType.value === 'brief' ? '摘要已保存' : '标签已保存'
    setTimeout(() => (successHint.value = ''), 2000)
  } catch (err) {
    editError.value = err.message || '保存失败'
  }
}

// 父组件保存转写段：成功后父组件会更新 session（word_count 等）
async function saveSegment(seq, text) {
  await emit('save-segment', seq, text)
}

const metaInfoText = computed(() => {
  const info = record.value?.basic_info
  if (!info) return ''
  const parts = []
  if (props.session?.model_display) {
    parts.push(`处理管线：${props.session.model_display}`)
  }
  if (info.model) parts.push(`模型：${info.model}`)
  if (info.prompt_version) parts.push(`提示词版本：${info.prompt_version}`)
  if (info.session_id) parts.push(`会话编号：#${info.session_id}`)
  return parts.join(' · ')
})

// ── T-S1.18：来访者（可点击切换下拉）────────────────────────
const clientOptions = computed(() => [
  { value: '', label: '未关联' },
  ...props.clients.map((c) => ({ value: String(c.client_id), label: c.name })),
])

async function changeClient(event) {
  await emit('assign-client', event.target.value)
}
</script>

<template>
  <div v-if="!session" class="card detail-empty">
    <p>未选择记录。请点击左侧看板中的任意记录，或上传一条录音。</p>
  </div>

  <div v-else class="detail-area">
    <section class="card detail-head">
      <div class="detail-title-row">
        <h2 class="detail-title">#{{ session.session_id }} · 记录详情</h2>
        <span class="board-badge" :class="{
          done: session.status === 'done',
          failed: session.status === 'failed',
          processing: session.status && session.status !== 'done' && session.status !== 'failed',
        }">
          {{ statusText }}
        </span>
      </div>
      <dl class="detail-meta">
        <div class="meta-item">
          <dt>日期时间</dt>
          <dd>{{ formatStartedAtFull(session.started_at) }}</dd>
        </div>
        <div class="meta-item">
          <dt>来源文件</dt>
          <dd class="filename" :title="session.original_filename">{{ session.original_filename || '—' }}</dd>
        </div>
        <div class="meta-item">
          <dt>时长</dt>
          <dd>{{ durationMMSS(session.duration_sec) }}</dd>
        </div>
        <div class="meta-item">
          <dt>字数</dt>
          <dd>{{ wordCount }}</dd>
        </div>
        <div class="meta-item">
          <dt>所属组</dt>
          <dd>{{ groupName || '未分组' }}</dd>
        </div>
        <div class="meta-item">
          <dt>来访者</dt>
          <dd>
            <select
              class="client-select"
              :value="String(session.client_id || '')"
              @change="changeClient"
            >
              <option v-for="c in clientOptions" :key="c.value" :value="c.value">
                {{ c.label }}
              </option>
            </select>
          </dd>
        </div>
      </dl>

      <div class="result-meta-panel">
        <div class="result-meta-row">
          <span class="record-key">摘要</span>
          <p class="result-meta-value">{{ summaryDisplay || '暂无' }}</p>
          <button class="btn small secondary" type="button" @click="openEditPanel('brief')">
            编辑
          </button>
        </div>
        <div class="result-meta-row">
          <span class="record-key">标签</span>
          <div class="tag-chip-list">
            <span v-for="(t, i) in sessionTags" :key="i" class="tag-chip">{{ t }}</span>
            <span v-if="!sessionTags.length" class="tag-empty">无标签</span>
          </div>
          <button class="btn small secondary" type="button" @click="openEditPanel('tags')">
            编辑
          </button>
        </div>
        <div v-if="editOpen" class="edit-panel">
          <textarea
            v-if="editType === 'brief'"
            v-model="editBriefValue"
            class="edit-input"
            rows="3"
            maxlength="100"
            placeholder="摘要（≤100 字）"
          ></textarea>
          <input
            v-else
            v-model="editTagsValue"
            class="edit-input"
            type="text"
            placeholder="标签（逗号分隔）"
          />
          <div class="edit-actions">
            <button class="btn small primary" type="button" @click="saveEdit">保存</button>
            <button class="btn small secondary" type="button" @click="cancelEdit">取消</button>
          </div>
          <div v-if="editError" class="error-box"><p>{{ editError }}</p></div>
        </div>
        <div v-if="successHint" class="success-hint">{{ successHint }}</div>
      </div>
    </section>

    <!-- 咨询记录（沿用折叠块） -->
    <section v-if="record" class="card">
      <h3 class="result-block-title">
        <button class="block-toggle" type="button" @click="toggleBlock('record')">
          <span class="fold-marker">{{ collapsedBlocks.record ? '▸' : '▾' }}</span>
          咨询记录
        </button>
      </h3>
      <div class="record-card" v-show="!collapsedBlocks.record">
        <div class="record-item" v-if="record.summary">
          <span class="record-key">概述</span>
          <p>{{ record.summary }}</p>
        </div>
        <div class="record-item" v-if="record.counselor_work">
          <span class="record-key">咨询师的工作</span>
          <p>{{ record.counselor_work }}</p>
        </div>
        <div class="record-item" v-if="record.client_reported_topics?.length">
          <span class="record-key">来访者话题</span>
          <ul class="tag-list">
            <li v-for="(topic, idx) in record.client_reported_topics" :key="idx">{{ topic }}</li>
          </ul>
        </div>
        <div class="record-item" v-if="record.basic_info">
          <span class="record-key">其他信息</span>
          <p class="meta-info">{{ metaInfoText }}</p>
        </div>
      </div>
    </section>

    <!-- 完整转写稿：双视图 -->
    <section class="card">
      <div class="transcript-head">
        <h3 class="result-block-title">完整转写稿</h3>
        <div class="view-tabs" role="tablist">
          <button
            class="view-tab"
            :class="{ active: viewMode === 'bubble' }"
            type="button"
            @click="viewMode = 'bubble'"
          >
            气泡视图
          </button>
          <button
            class="view-tab"
            :class="{ active: viewMode === 'table' }"
            type="button"
            @click="viewMode = 'table'"
          >
            表格视图
          </button>
        </div>
      </div>

      <p v-if="!segments.length" class="transcript-empty">暂无转写内容。</p>

      <TranscriptBubbles
        v-else-if="viewMode === 'bubble'"
        :segments="segments"
        :is-dark="isDark"
        :show-timestamps="showTimestamps"
        :compact="false"
      />
      <TranscriptTable
        v-else
        :segments="segments"
        :is-dark="isDark"
        :session-id="session.session_id"
        @save="saveSegment"
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

.detail-empty p {
  margin: 0;
  color: var(--muted);
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.detail-title {
  margin: 0;
  font-size: 1.15rem;
  border-bottom: none;
  padding-bottom: 0;
}

.board-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.74rem;
  white-space: nowrap;
}

.board-badge.done {
  background: var(--ok-bg);
  color: var(--ok-text);
}

.board-badge.failed {
  background: var(--danger-soft);
  color: var(--danger);
}

.board-badge.processing {
  background: var(--primary-soft);
  color: var(--primary-dark);
}

.detail-meta {
  margin: 0 0 12px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.meta-item {
  margin: 0;
}

.meta-item dt {
  font-size: 0.75rem;
  color: var(--muted);
}

.meta-item dd {
  margin: 0;
  font-size: 0.9rem;
}

.meta-item dd.filename {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.client-select {
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 0.85rem;
  max-width: 180px;
  cursor: pointer;
}

.result-meta-panel {
  margin-bottom: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--card-inset);
}

.result-meta-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
}

.record-key {
  display: block;
  font-weight: 600;
  color: var(--primary-dark);
  margin-bottom: 0;
  font-size: 0.9rem;
  flex: 0 0 52px;
}

.result-meta-value {
  flex: 1;
  margin: 0;
  font-size: 0.92rem;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.tag-chip-list {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tag-chip,
.tag-pill {
  display: inline-flex;
  align-items: center;
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 0.74rem;
  background: var(--primary-soft);
  color: var(--primary-dark);
  white-space: nowrap;
}

.tag-empty {
  color: var(--muted);
  font-size: 0.85rem;
}

.edit-panel {
  margin-top: 4px;
  border-top: 1px dashed var(--border-subtle);
  padding-top: 8px;
}

.edit-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  color: var(--text);
  font-size: 0.9rem;
  font-family: inherit;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.success-hint {
  margin-top: 6px;
  color: var(--ok-text);
  font-size: 0.8rem;
}

.result-block-title {
  margin: 0 0 10px;
  font-size: 1rem;
  color: var(--muted);
}

.block-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: inherit;
  font-size: inherit;
  font-weight: 600;
}

.fold-marker {
  color: var(--muted);
}

.record-card {
  background: var(--card-inset);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 14px;
}

.record-item {
  margin-bottom: 14px;
}

.record-item:last-child {
  margin-bottom: 0;
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

.transcript-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.transcript-head .result-block-title {
  margin: 0;
}

.view-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--surface);
}

.view-tab {
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 0.78rem;
  color: var(--muted);
  background: none;
  border: none;
  cursor: pointer;
}

.view-tab.active {
  background: var(--primary);
  color: var(--on-primary);
}

.transcript-empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}

.error-box {
  margin-top: 12px;
  padding: 12px;
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  border-radius: 8px;
  color: var(--danger);
}

.error-box p {
  margin: 0;
}

.btn {
  border: none;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: opacity 0.2s;
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

@media (max-width: 480px) {
  .card {
    padding: 16px;
  }

  .detail-meta {
    grid-template-columns: 1fr;
  }

  .meta-item dd.filename {
    max-width: 100%;
  }
}
</style>
