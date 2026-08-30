<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import BoardSidebar from './components/BoardSidebar.vue'
import UploadPanel from './components/UploadPanel.vue'
import DetailPanel from './components/DetailPanel.vue'
import Workbench from './components/Workbench.vue'

// 支持的音频扩展名（与后端校验保持一致）
const ALLOWED_EXTS = ['.wav', '.m4a', '.mp3', '.opus', '.flac']

// 简谐主题（T-S1.11.1）：默认跟随系统，用户选择持久化 localStorage
const STORAGE_KEY = 'psy-theme'
const THEMES = ['light', 'dark']

function parseStoredTheme(raw) {
  return THEMES.includes(raw) ? raw : null
}

const theme = ref(parseStoredTheme(localStorage.getItem(STORAGE_KEY)))
const storedSystem = ref('')
const isDarkTheme = ref(false)
applyTheme()

function applyTheme() {
  if (theme.value) {
    storedSystem.value = ''
    document.documentElement.dataset.theme = theme.value
  } else {
    const sys = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    storedSystem.value = sys
    document.documentElement.dataset.theme = sys
  }
  isDarkTheme.value = document.documentElement.dataset.theme === 'dark'
}

function setTheme(value) {
  if (value === 'auto') {
    theme.value = null
    localStorage.removeItem(STORAGE_KEY)
  } else {
    theme.value = value
    localStorage.setItem(STORAGE_KEY, value)
  }
  applyTheme()
}

function themeLabel(value) {
  if (value === 'auto') {
    return storedSystem.value === 'dark' ? '⏾自动（暗）' : '☀自动（亮）'
  }
  return value === 'dark' ? '⏾暗色' : '☀亮色'
}

function themeChecked(value) {
  if (value === 'auto') return theme.value === null
  return theme.value === value
}

// ── 上传 / 轮询状态（护栏逻辑保持 T-S1.10/T-S1.6 既定实现）──
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

const groups = ref([])
const groupsLoading = ref(false)

// T-S1.14：右侧功能区 Tab（upload | detail）
const activeTab = ref('upload')

// T-S1.16：顶层「记录看板 / 工作台」切换（纯前端状态）
const appView = ref('board')
const workbenchSummary = ref(null)
const workbenchError = ref('')

function gotoBoard() {
  appView.value = 'board'
}

function gotoWorkbench() {
  appView.value = 'workbench'
  if (!workbenchSummary.value && !workbenchError.value) loadWorkbenchSummary()
}

// T-S1.16：待办下钻 → 简单切回记录看板即可（不做精确筛选联动）
function gotoTodo() {
  appView.value = 'board'
}

async function loadWorkbenchSummary() {
  // 懒加载：仅进入工作台时请求，看板功能零回归
  workbenchError.value = ''
  try {
    const res = await fetch('/api/dashboard/summary')
    const json = await res.json()
    if (!json.ok) {
      throw new Error(json.error?.message || '加载工作台数据失败')
    }
    workbenchSummary.value = json.data
  } catch (err) {
    workbenchError.value = err.message || '加载工作台数据失败'
  }
}

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
  activeTab.value = 'upload'
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
      // T-S1.14：处理完成后自动切到记录详情区展示新记录
      if (json.data.status === 'done') {
        activeTab.value = 'detail'
        await refreshDetailMeta()
      }
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

// ── 详情数据：合并列表元数据（时长/字数/文件名）+ 详情 ──────
// sessionData 是 GET /sessions/{id} 详情；sessionMeta 是列表行补充字段
const sessionMeta = ref(null)

const detailSession = computed(() => {
  if (!sessionData.value) return null
  return {
    ...sessionMeta.value,
    ...sessionData.value,
    tags: sessionData.value.tags || [],
    record: sessionData.value.record || null,
  }
})

const detailGroupName = computed(() => {
  const gid = sessionData.value?.group_id
  if (!gid && gid !== 0) return ''
  return groups.value.find((g) => String(g.group_id) === String(gid))?.name || ''
})

async function refreshDetailMeta() {
  if (!sessionData.value) {
    sessionMeta.value = null
    return
  }
  const id = sessionData.value.session_id
  const row = sessions.value.find((s) => s.session_id === id)
  sessionMeta.value = row
    ? {
        original_filename: row.original_filename,
        duration_sec: row.duration_sec,
        word_count: row.word_count,
        started_at: row.started_at,
      }
    : { original_filename: null, duration_sec: 0, word_count: 0, started_at: sessionData.value.started_at }
}

async function selectSession(id) {
  if (sessionId.value === id && sessionStatus.value) {
    activeTab.value = 'detail'
    refreshDetailMeta()
    return
  }
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
    activeTab.value = 'detail'
    refreshDetailMeta()
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

// 气泡列表单一来源：segments；文本优先 cleaned_content，无则 content
const bubbleSegments = computed(() => {
  const segments = sessionData.value?.segments || []
  return segments.map((seg) => ({
    ...seg,
    bubbleText: seg.cleaned_content ?? seg.content ?? '',
  }))
})

// omni 直转无时间戳，气泡头不渲染时间行
const showTimestamps = computed(() => pipelineMode.value !== 'omni')

const isDark = computed(() => isDarkTheme.value)

// ── 摘要/标签编辑（PATCH /sessions/{id}，复用原逻辑）────────
async function patchSession(item, payload) {
  const res = await fetch(`/api/sessions/${item.session_id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const json = await res.json()
  if (!json.ok) throw new Error(json.error?.message || '保存失败')
  loadSessions()
  return json.data
}

async function saveBrief(brief) {
  if ((brief || '').length > 100) {
    throw new Error('摘要不能超过 100 字')
  }
  if (!sessionData.value) throw new Error('未选择记录')
  const data = await patchSession(sessionData.value, { brief })
  if (sessionData.value?.session_id === data.session_id) {
    sessionData.value = { ...sessionData.value, brief: data.brief, tags: data.tags || [] }
  }
  boardError.value = ''
  return data
}

async function saveTags(tags) {
  if (!sessionData.value) throw new Error('未选择记录')
  const data = await patchSession(sessionData.value, { tags })
  if (sessionData.value?.session_id === data.session_id) {
    sessionData.value = { ...sessionData.value, tags: data.tags || [] }
  }
  boardError.value = ''
  return data
}

async function moveSession(s, groupId) {
  boardError.value = ''
  try {
    const payload = groupId === '' || groupId == null ? { group_id: null } : { group_id: Number(groupId) }
    await patchSession(s, payload)
    if (sessionData.value?.session_id === s.session_id) {
      sessionData.value = { ...sessionData.value, group_id: payload.group_id }
      refreshDetailMeta()
    }
    loadGroups()
  } catch (err) {
    boardError.value = err.message || '移动失败'
  }
}

async function deleteSession(s) {
  boardError.value = ''
  try {
    const res = await fetch(`/api/sessions/${s.session_id}`, { method: 'DELETE' })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '删除失败')
    sessions.value = sessions.value.filter((x) => x.session_id !== s.session_id)
    if (activeSessionId.value === s.session_id) {
      stopPolling()
      activeSessionId.value = null
      sessionId.value = null
      sessionStatus.value = ''
      sessionData.value = null
      sessionMeta.value = null
      activeTab.value = 'upload'
    }
    loadGroups()
  } catch (err) {
    boardError.value = err.message || '删除失败'
  }
}

// ── T-S1.14：组删除双模式 / 批量删除 / 导出 ─────────────────
const groupDeleteGroup = ref(null) // 待删除的组（打开双模式弹层）
const groupDeleteBusy = ref(false)
const groupDeleteError = ref('')

function groupMemberCount(g) {
  return sessions.value.filter((s) => s.group_id === g.group_id).length
}

function openGroupDelete(g) {
  groupDeleteGroup.value = g
  groupDeleteError.value = ''
  groupDeleteBusy.value = false
}

function closeGroupDelete() {
  if (groupDeleteBusy.value) return
  groupDeleteGroup.value = null
}

async function deleteGroupMode(mode) {
  const g = groupDeleteGroup.value
  if (!g) return
  groupDeleteBusy.value = true
  groupDeleteError.value = ''
  try {
    const res = await fetch(`/api/groups/${g.group_id}?mode=${mode}`, { method: 'DELETE' })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '删除分组失败')
    groupDeleteGroup.value = null
    if (mode === 'with_records') {
      // 组内记录全删：清掉本地引用
      const ids = new Set(json.data?.deleted_sessions || [])
      sessions.value = sessions.value.filter((x) => !ids.has(x.session_id))
      if (ids.has(activeSessionId.value)) {
        stopPolling()
        activeSessionId.value = null
        sessionId.value = null
        sessionStatus.value = ''
        sessionData.value = null
        sessionMeta.value = null
        activeTab.value = 'upload'
      }
    } else if (sessionData.value?.group_id === g.group_id) {
      // 解散：当前详情所属组的 group_id 归未分组
      sessionData.value = { ...sessionData.value, group_id: null }
    }
    loadGroups()
    loadSessions()
  } catch (err) {
    groupDeleteError.value = err.message || '删除分组失败'
  } finally {
    groupDeleteBusy.value = false
  }
}

const confirmOpen = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
const confirmAction = ref(null)

function confirmDeleteSession(s) {
  confirmTitle.value = '删除记录'
  confirmMessage.value = `确定删除会话 #${s.session_id}（${s.original_filename || '无文件'}）？此操作不可撤销。`
  confirmAction.value = () => deleteSession(s)
  confirmOpen.value = true
}

function confirmBulkDelete(ids) {
  if (!ids || !ids.length) {
    boardError.value = '请先选择要删除的记录'
    return
  }
  confirmTitle.value = '批量删除记录'
  confirmMessage.value = `确定删除已选的 ${ids.length} 条记录？此操作不可撤销（含音频文件）。`
  confirmAction.value = async () => {
    const res = await fetch('/api/sessions/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_ids: ids }),
    })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '批量删除失败')
    const deleted = new Set(json.data?.deleted || [])
    sessions.value = sessions.value.filter((x) => !deleted.has(x.session_id))
    if (deleted.has(activeSessionId.value)) {
      stopPolling()
      activeSessionId.value = null
      sessionId.value = null
      sessionStatus.value = ''
      sessionData.value = null
      sessionMeta.value = null
      activeTab.value = 'upload'
    }
    loadSessions()
    loadGroups()
  }
  confirmOpen.value = true
}

async function runConfirmAction() {
  try {
    if (confirmAction.value) await confirmAction.value()
  } catch (err) {
    boardError.value = err.message || '操作失败'
  }
  confirmOpen.value = false
}

function cancelConfirm() {
  confirmOpen.value = false
}

function downloadJson(text, filename) {
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportSessions(selectedIds) {
  boardError.value = ''
  try {
    const res = await fetch('/api/export/sessions')
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '导出失败')
    let payload = json.data?.sessions || []
    if (selectedIds && selectedIds.length) {
      const set = new Set(selectedIds)
      payload = payload.filter((s) => set.has(s.session_id))
    }
    const now = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const dateStr = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
    const data = {
      exported_at: json.data?.exported_at || new Date().toISOString(),
      count: payload.length,
      sessions: payload,
    }
    downloadJson(JSON.stringify(data, null, 2), `mengpsy-records-${dateStr}.json`)
  } catch (err) {
    boardError.value = err.message || '导出失败'
  }
}

// ── T-S1.14：转写段精确编辑（PATCH /sessions/{id}/segments/{seq}）──
async function patchSegment(seq, text) {
  if (!sessionData.value) throw new Error('未选择记录')
  const res = await fetch(`/api/sessions/${sessionData.value.session_id}/segments/${seq}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  const json = await res.json()
  if (!json.ok) throw new Error(json.error?.message || '保存失败')
  // 更新本地状态：该段 cleaned_content 与总字数
  const segments = (sessionData.value.segments || []).map((seg) =>
    seg.seq === json.data.seq ? { ...seg, cleaned_content: text, content: seg.content } : seg
  )
  sessionData.value = {
    ...sessionData.value,
    segments,
    word_count: json.data.word_count,
    cleaned_text: segments.map((s) => s.cleaned_content ?? s.content ?? '').filter((t) => t).join('\n'),
  }
  if (sessionMeta.value) {
    sessionMeta.value = { ...sessionMeta.value, word_count: json.data.word_count }
  }
  boardError.value = ''
  return json.data
}

// ── 分组编辑弹层（复用原逻辑）───────────────────────────────
const groupEditOpen = ref(false)
const groupEditMode = ref('create') // create | edit
const groupEditName = ref('')
const groupEditTags = ref('')
const groupEditNote = ref('')
const groupEditError = ref('')
const groupEditId = ref(null)

function parseGroupTags(text) {
  return (text || '')
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean)
}

function openGroupEdit(group) {
  groupEditOpen.value = true
  groupEditError.value = ''
  groupEditName.value = (group && group.name) || ''
  groupEditTags.value = group ? (group.tags || []).join(', ') : ''
  groupEditNote.value = (group && group.note) || ''
  groupEditMode.value = group && group.group_id != null ? 'edit' : 'create'
  groupEditId.value = (group && group.group_id) || null
}

function closeGroupEdit() {
  groupEditOpen.value = false
}

async function submitGroup() {
  const name = groupEditName.value.trim()
  if (!name) {
    groupEditError.value = '组名不能为空'
    return
  }
  const payload = { name, tags: parseGroupTags(groupEditTags.value), note: groupEditNote.value.trim() }
  groupEditError.value = ''
  try {
    if (groupEditMode.value === 'edit') {
      const res = await fetch(`/api/groups/${groupEditId.value}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const json = await res.json()
      if (!json.ok) throw new Error(json.error?.message || '保存失败')
    } else {
      const res = await fetch('/api/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const json = await res.json()
      if (!json.ok) throw new Error(json.error?.message || '新建失败')
    }
    groupEditOpen.value = false
    loadGroups()
    loadSessions()
  } catch (err) {
    groupEditError.value = err.message || '保存失败'
  }
}

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
    refreshDetailMeta()
  } catch (err) {
    boardError.value = err.message || '加载记录失败'
  } finally {
    boardLoading.value = false
  }
}

async function loadGroups() {
  groupsLoading.value = true
  try {
    const res = await fetch('/api/groups')
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '加载分组失败')
    groups.value = json.data?.groups || []
  } catch (err) {
    boardError.value = err.message || '加载分组失败'
  } finally {
    groupsLoading.value = false
  }
}

let _mq = null
let _sys = null
onMounted(() => {
  loadSessions()
  loadGroups()
  _mq = matchMedia('(prefers-color-scheme: dark)')
  _sys = () => {
    if (!theme.value) applyTheme()
  }
  _mq.addEventListener('change', _sys)
})
onUnmounted(() => {
  stopPolling()
  if (_mq && _sys) _mq.removeEventListener('change', _sys)
})
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>咨询记录助手</h1>
      <p class="subtitle">录音 → 转写 → 清理 → 客观记录</p>
      <nav class="view-nav" role="tablist" aria-label="页面切换">
        <button
          type="button"
          class="view-tab"
          :class="{ active: appView === 'board' }"
          @click="gotoBoard"
        >
          记录看板
        </button>
        <button
          type="button"
          class="view-tab"
          :class="{ active: appView === 'workbench' }"
          @click="gotoWorkbench"
        >
          工作台
        </button>
      </nav>
      <div class="theme-ctl" role="group" aria-label="主题切换">
        <label
          v-for="opt in ['light', 'auto', 'dark']"
          :key="opt"
          class="theme-opt"
          :class="{ checked: themeChecked(opt) }"
        >
          <input
            type="radio"
            name="theme"
            :value="opt"
            :checked="themeChecked(opt)"
            @change="setTheme(opt)"
          />
          {{ themeLabel(opt) }}
        </label>
      </div>
    </header>

    <main v-show="appView === 'board'" class="container dashboard">
      <!-- 左侧看板 -->
      <BoardSidebar
        :sessions="sessions"
        :groups="groups"
        :board-loading="boardLoading"
        :groups-loading="groupsLoading"
        :board-error="boardError"
        :active-session-id="activeSessionId"
        @refresh="() => { loadSessions(); loadGroups() }"
        @select="selectSession"
        @move-session="moveSession"
        @delete-session="confirmDeleteSession"
        @edit-group="openGroupEdit"
        @delete-group="openGroupDelete"
        @bulk-delete="confirmBulkDelete"
        @export="exportSessions"
      />

      <!-- 右侧功能区 Tab -->
      <div class="main-panel">
        <div class="panel-tabs" role="tablist">
          <button
            class="panel-tab"
            :class="{ active: activeTab === 'upload' }"
            type="button"
            @click="activeTab = 'upload'"
          >
            ① 上传/转写区
          </button>
          <button
            class="panel-tab"
            :class="{ active: activeTab === 'detail' }"
            type="button"
            @click="activeTab = 'detail'"
          >
            ② 记录详情区
          </button>
        </div>

        <UploadPanel
          v-show="activeTab === 'upload'"
          v-model:selected-mode="selectedMode"
          :uploading="uploading"
          :file-name="fileName"
          :accepted-types="acceptedTypes"
          :error="error"
          :session-status="sessionStatus"
          :session-data="sessionData"
          :status-text="statusText"
          :progress-steps="progressSteps"
          :bubble-segments="bubbleSegments"
          :compact-transcript="compactTranscript"
          :show-timestamps="showTimestamps"
          :is-dark="isDark"
          @file-change="onFileChange"
          @upload="upload"
          @reset="reset"
          @retry="retry"
        />

        <DetailPanel
          v-show="activeTab === 'detail'"
          :session="detailSession"
          :group-name="detailGroupName"
          :is-dark="isDark"
          :show-timestamps="showTimestamps"
          @save-brief="saveBrief"
          @save-tags="saveTags"
          @save-segment="patchSegment"
        />
      </div>
    </main>

    <!-- T-S1.16：工作台页 -->
    <main v-show="appView === 'workbench'" class="container">
      <div v-if="workbenchError" class="error-box">
        <p>{{ workbenchError }}</p>
        <button class="btn small primary" type="button" @click="loadWorkbenchSummary">重试</button>
      </div>
      <div v-else-if="!workbenchSummary" class="wb-loading" role="status">
        <span class="wb-loading-text">加载中…</span>
      </div>
      <Workbench
        v-else
        :summary="workbenchSummary"
        :groups="groups"
        @goto-todo="gotoTodo"
      />
    </main>

    <!-- 分组新建/编辑弹层 -->
    <div v-if="groupEditOpen" class="modal-mask" @click.self="closeGroupEdit">
      <div class="modal">
        <h3>{{ groupEditMode === 'edit' ? '编辑分组' : '新建分组' }}</h3>
        <div class="form-row">
          <label class="modal-label">
            组名
            <input v-model="groupEditName" type="text" placeholder="组名" />
          </label>
        </div>
        <div class="form-row">
          <label class="modal-label">
            标签
            <input v-model="groupEditTags" type="text" placeholder="逗号分隔" />
          </label>
        </div>
        <div class="form-row">
          <label class="modal-label">
            备注
            <input v-model="groupEditNote" type="text" placeholder="备注" />
          </label>
        </div>
        <div v-if="groupEditError" class="error-box"><p>{{ groupEditError }}</p></div>
        <div class="edit-actions">
          <button class="btn small primary" type="button" @click="submitGroup">保存</button>
          <button class="btn small secondary" type="button" @click="closeGroupEdit">取消</button>
        </div>
      </div>
    </div>

    <!-- 组删除双模式确认层 -->
    <div v-if="groupDeleteGroup" class="modal-mask" @click.self="closeGroupDelete">
      <div class="modal group-delete-modal">
        <h3>删除分组「{{ groupDeleteGroup.name }}」</h3>
        <p class="confirm-msg">
          组内现有 <strong>{{ groupMemberCount(groupDeleteGroup) }}</strong> 条记录。请选择删除方式：
        </p>
        <div class="delete-mode-actions">
          <button
            class="btn secondary delete-mode-btn"
            type="button"
            :disabled="groupDeleteBusy"
            @click="deleteGroupMode('dissolve')"
          >
            <span class="delete-mode-title">仅解散组</span>
            <span class="delete-mode-desc">记录保留，归为未分组</span>
          </button>
          <button
            class="btn danger delete-mode-btn"
            type="button"
            :disabled="groupDeleteBusy"
            @click="deleteGroupMode('with_records')"
          >
            <span class="delete-mode-title">删除组和包含的记录</span>
            <span class="delete-mode-desc">
              将删除 {{ groupMemberCount(groupDeleteGroup) }} 条记录，不可撤销
            </span>
          </button>
        </div>
        <div v-if="groupDeleteError" class="error-box"><p>{{ groupDeleteError }}</p></div>
        <div class="edit-actions">
          <button class="btn small secondary" type="button" :disabled="groupDeleteBusy" @click="closeGroupDelete">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- 删除/操作确认弹层 -->
    <div v-if="confirmOpen" class="modal-mask" @click.self="cancelConfirm">
      <div class="modal">
        <h3>{{ confirmTitle }}</h3>
        <p class="confirm-msg">{{ confirmMessage }}</p>
        <div class="edit-actions">
          <button class="btn small danger" type="button" @click="runConfirmAction">确认删除</button>
          <button class="btn small secondary" type="button" @click="cancelConfirm">取消</button>
        </div>
      </div>
    </div>

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
  --card-inset: #f9fafb;
  --text: #1f2937;
  --muted: #6b7280;
  --border: #d1d5db;
  --border-subtle: #e5e7eb;
  --surface: #f3f4f6;
  --primary: #2563eb;
  --primary-dark: #1d4ed8;
  --primary-soft: #eef2ff;
  --hover: #f5f9ff;
  --primary-hover-border: #bfdbfe;
  --danger: #dc2626;
  --danger-soft: #fef2f2;
  --danger-border: #fecaca;
  --ok-bg: #e8f7f0;
  --ok-text: #146c4b;
  --on-primary: #ffffff;
  --radius: 12px;
  --shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  color-scheme: light;
}

html[data-theme='dark'] {
  --bg: #0f1115;
  --card: #191d24;
  --card-inset: #232832;
  --text: #e6e9ef;
  --muted: #9aa3b2;
  --border: #3a4250;
  --border-subtle: #2b323d;
  --surface: #232832;
  --primary: #2563eb;
  --primary-dark: #86a9f9;
  --primary-soft: #23304a;
  --hover: #212a38;
  --primary-hover-border: #4c68a8;
  --danger: #f87171;
  --danger-soft: #3b1f22;
  --danger-border: #6b2a30;
  --ok-bg: #1d3228;
  --ok-text: #7fd0a4;
  --on-primary: #ffffff;
  --shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
  color-scheme: dark;
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

.view-nav {
  display: inline-flex;
  gap: 4px;
  margin-top: 12px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--surface);
}

.view-tab {
  padding: 6px 18px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 0.9rem;
  cursor: pointer;
}

.view-tab.active {
  background: var(--primary);
  color: var(--on-primary);
  font-weight: 600;
}

.wb-loading {
  padding: 48px 0;
  text-align: center;
  color: var(--muted);
  font-size: 0.95rem;
}

.theme-ctl {
  display: inline-flex;
  gap: 4px;
  margin-top: 8px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--surface);
}

.theme-opt {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}

.theme-opt.checked {
  background: var(--primary);
  color: var(--on-primary);
}

.theme-opt input {
  display: none;
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

/* 右侧功能区 Tab */
.panel-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.panel-tab {
  flex: 1;
  max-width: 240px;
  padding: 10px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--surface);
  color: var(--muted);
  font-size: 0.9rem;
  cursor: pointer;
}

.panel-tab.active {
  background: var(--primary);
  color: var(--on-primary);
  border-color: var(--primary);
  font-weight: 600;
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

.btn.danger {
  background: var(--danger);
  color: var(--on-primary);
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.85rem;
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

.error-box p:last-child {
  margin: 0;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 50;
}

.modal {
  background: var(--card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  width: min(360px, 100%);
}

.group-delete-modal {
  width: min(420px, 100%);
}

.modal h3 {
  margin: 0 0 12px;
  font-size: 1.05rem;
  color: var(--text);
}

.modal-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  font-size: 0.85rem;
  color: var(--muted);
}

.modal-label input {
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  color: var(--text);
  font-size: 0.9rem;
}

.form-row {
  margin-bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.confirm-msg {
  margin: 0 0 12px;
  color: var(--text);
  font-size: 0.92rem;
  word-break: break-word;
}

.delete-mode-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 4px;
}

.delete-mode-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  text-align: left;
  padding: 12px 14px;
  font-size: 0.9rem;
}

.delete-mode-title {
  font-weight: 600;
}

.delete-mode-desc {
  font-size: 0.8rem;
  opacity: 0.85;
}

.footer {
  text-align: center;
  padding: 16px;
  color: var(--muted);
  font-size: 0.85rem;
  background: var(--card);
  border-top: 1px solid var(--border-subtle);
}

/* 响应式：看板加宽断点，窄屏纵向堆叠 */
@media (max-width: 767px) {
  .dashboard {
    flex-direction: column;
  }
}

@media (max-width: 480px) {
  .header h1 {
    font-size: 1.45rem;
  }

  .view-tab {
    padding: 5px 12px;
    font-size: 0.82rem;
  }

  .panel-tab {
    padding: 8px 10px;
    font-size: 0.82rem;
  }

  .btn {
    width: 100%;
  }

  .edit-actions .btn {
    width: auto;
  }
}
</style>
