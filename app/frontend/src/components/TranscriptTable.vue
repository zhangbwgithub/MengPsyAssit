<script setup>
import { ref, watch, computed } from 'vue'
import { speakerColorMap, colorOf, labelOf } from '../utils/speakers.js'

const props = defineProps({
  segments: { type: Array, default: () => [] },
  isDark: { type: Boolean, default: false },
  sessionId: { type: [Number, String], default: null },
})

const emit = defineEmits(['save'])

// 本地草稿：以 cleaned_content ?? content 为初始值
const drafts = ref([])
const saving = ref({}) // seq -> bool
const savedSeq = ref(null) // 最近保存成功的 seq（用于短暂提示）
const error = ref('')

watch(
  () => props.segments,
  (segs) => {
    drafts.value = (segs || []).map((seg) => ({
      seq: seg.seq,
      text: seg.cleaned_content ?? seg.content ?? '',
    }))
    error.value = ''
    savedSeq.value = null
  },
  { immediate: true }
)

const colorMapFn = computed(() => speakerColorMap(props.segments, props.isDark))

function draftOf(seq) {
  return drafts.value.find((d) => d.seq === seq)
}

function speakerOf(seq) {
  const seg = (props.segments || []).find((s) => s.seq === seq)
  return seg || {}
}

function speakerStyle(seg) {
  const color = colorOf(colorMapFn.value, seg.speaker, props.isDark)
  return {
    backgroundColor: color.bg,
    borderColor: color.border,
    color: color.text,
  }
}

function isDirty(seq) {
  const d = draftOf(seq)
  const seg = speakerOf(seq)
  if (!d || !seg) return false
  const original = seg.cleaned_content ?? seg.content ?? ''
  return d.text !== original
}

async function saveRow(seq) {
  const d = draftOf(seq)
  if (!d) return
  const text = d.text.replace(/\s+$/, '')
  if (!text.trim()) {
    error.value = `第 ${seq} 轮内容不能为空`
    return
  }
  error.value = ''
  saving.value[seq] = true
  try {
    await emit('save', seq, text)
    savedSeq.value = seq
    setTimeout(() => {
      if (savedSeq.value === seq) savedSeq.value = null
    }, 2000)
  } catch (err) {
    error.value = err.message || `第 ${seq} 轮保存失败`
  } finally {
    saving.value[seq] = false
  }
}

// 可选「保存全部改动」：依次保存所有已改动行
async function saveAll() {
  error.value = ''
  const dirty = (props.segments || []).filter((seg) => isDirty(seg.seq))
  if (!dirty.length) return
  for (const seg of dirty) {
    await saveRow(seg.seq)
    if (error.value) return
  }
}
</script>

<template>
  <div class="table-wrap">
    <div v-if="error" class="error-box table-error">
      <p>{{ error }}</p>
    </div>
    <table class="seg-table">
      <thead>
        <tr>
          <th class="col-seq">轮次</th>
          <th class="col-speaker">说话人</th>
          <th class="col-content">内容</th>
          <th class="col-action"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="seg in segments" :key="seg.seq">
          <td class="col-seq">{{ seg.seq }}</td>
          <td class="col-speaker">
            <span class="role-tag" :style="speakerStyle(seg)">
              {{ labelOf(seg) }}
            </span>
          </td>
          <td class="col-content">
            <textarea
              v-model="draftOf(seg.seq).text"
              class="seg-editor"
              rows="2"
            ></textarea>
          </td>
          <td class="col-action">
            <button
              v-if="isDirty(seg.seq)"
              class="btn small primary save-btn"
              type="button"
              :disabled="saving[seg.seq]"
              @click="saveRow(seg.seq)"
            >
              {{ saving[seg.seq] ? '保存中…' : '保存' }}
            </button>
            <span v-else-if="savedSeq === seg.seq" class="saved-hint">✓ 已保存</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div class="table-actions">
      <button
        class="btn small secondary"
        type="button"
        :disabled="!segments.some((seg) => isDirty(seg.seq))"
        @click="saveAll"
      >
        保存全部改动
      </button>
    </div>
    <p class="table-note">修改内容后点击该行「保存」；原文由后端重建 cleaned_text 与字数。</p>
  </div>
</template>

<style scoped>
.table-wrap {
  min-width: 0;
}

.table-error {
  margin: 0 0 10px;
}

.table-error p {
  margin: 0;
}

.seg-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}

.seg-table th,
.seg-table td {
  border: 1px solid var(--border-subtle);
  padding: 6px 8px;
  vertical-align: top;
  text-align: left;
}

.seg-table th {
  background: var(--surface);
  color: var(--muted);
  font-weight: 600;
  font-size: 0.78rem;
  white-space: nowrap;
}

.col-seq {
  width: 56px;
  text-align: center;
  color: var(--muted);
}

.col-speaker {
  width: 110px;
}

.col-content {
  min-width: 220px;
}

.col-action {
  width: 90px;
  text-align: center;
  white-space: nowrap;
}

.role-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 0.74rem;
  border: 1px solid transparent;
  white-space: nowrap;
}

.seg-editor {
  width: 100%;
  box-sizing: border-box;
  min-height: 52px;
  resize: vertical;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  color: var(--text);
  font-size: 0.88rem;
  font-family: inherit;
  line-height: 1.5;
}

.seg-editor:focus {
  outline: none;
  border-color: var(--primary);
}

.save-btn {
  padding: 4px 10px;
  font-size: 0.78rem;
}

.saved-hint {
  color: var(--ok-text);
  font-size: 0.78rem;
}

.table-actions {
  margin-top: 10px;
}

.table-note {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 0.75rem;
}

/* 窄屏横向滚动 */
@media (max-width: 480px) {
  .table-wrap {
    overflow-x: auto;
  }

  .seg-table {
    min-width: 520px;
  }
}
</style>
