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

// 主题标签：不再使用 ☀/⏾ emoji 类字形，仅返回纯文本（图标由内联 SVG 承载）
function themeLabel(value) {
  if (value === 'auto') {
    return storedSystem.value === 'dark' ? '自动（暗）' : '自动（亮）'
  }
  return value === 'dark' ? '暗色' : '亮色'
}

function themeIconType(value) {
  if (value === 'auto') return storedSystem.value === 'dark' ? 'moon' : 'sun'
  return value === 'dark' ? 'moon' : 'sun'
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
// T-S1.18：上传时可先选「来访者」，成功挂上后自动 PATCH 新会话 client_id
const uploadClientId = ref('')

// T-S1.10：左侧上传/分析记录看板
const sessions = ref([])
const boardLoading = ref(false)
const boardError = ref('')
const activeSessionId = ref(null)

const groups = ref([])
const groupsLoading = ref(false)

// T-S1.18：来访者档案（GET/POST /api/clients）
const clients = ref([])
const clientsLoading = ref(false)
const activeClientFilter = ref(null) // 选中来访者 id（null=全部）

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
    // T-S1.18：上传成功即把新会话挂到选中的来访者（一次性 PATCH）
    if (uploadClientId.value !== '' && uploadClientId.value != null) {
      try {
        await fetch(`/api/sessions/${json.data.session_id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: Number(uploadClientId.value) }),
        })
        loadClients()
      } catch {
        // 挂接失败不阻断上传主流程，看板刷新后可见未关联状态
      }
    }
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

// T-S1.18：把记录挂接/解挂来访者（PATCH /sessions/{id} 的 client_id）
async function assignSessionClient(s, clientId) {
  boardError.value = ''
  try {
    const payload = clientId === '' || clientId == null ? { client_id: null } : { client_id: Number(clientId) }
    await patchSession(s, payload)
    if (sessionData.value?.session_id === s.session_id) {
      sessionData.value = { ...sessionData.value, ...payload, client_name: clientNameOf(payload.client_id) }
    }
    loadClients()
  } catch (err) {
    boardError.value = err.message || '更新来访者失败'
  }
}

// 依 client_id 取当前档案（供记录条目/详情显示姓名）
function clientNameOf(cid) {
  if (cid == null) return ''
  const c = clients.value.find((x) => x.client_id === Number(cid))
  return c?.name || ''
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

// ── T-S1.18：来访者建档/编辑弹层与删除确认 ────────────────
const clientEditOpen = ref(false)
const clientEditMode = ref('create') // create | edit
const clientEditId = ref(null)
const clientForm = ref(emptyClientForm())
const clientEditError = ref('')
const clientEditBusy = ref(false)

function emptyClientForm() {
  return {
    name: '',
    gender: '女',
    age: '',
    phone: '',
    emergency_contact: '',
    emergency_phone: '',
    start_date: '',
    status: 'active',
    note: '',
  }
}

function openClientEdit(client) {
  clientEditOpen.value = true
  clientEditError.value = ''
  clientEditId.value = client ? client.client_id : null
  clientEditMode.value = client ? 'edit' : 'create'
  if (client) {
    clientForm.value = {
      name: client.name || '',
      gender: client.gender || '女',
      age: client.age != null ? String(client.age) : '',
      phone: client.phone || '',
      emergency_contact: client.emergency_contact || '',
      emergency_phone: client.emergency_phone || '',
      start_date: client.start_date || '',
      status: client.status || 'active',
      note: client.note || '',
    }
  } else {
    clientForm.value = emptyClientForm()
  }
}

function closeClientEdit() {
  if (clientEditBusy.value) return
  clientEditOpen.value = false
}

// 提交前清理：空串字段序列化为 null，与后端“显式传入字段”口径一致
function clientPayload() {
  const f = clientForm.value
  const numOrNull = (v) => (v === '' || v == null ? null : Number(v))
  return {
    name: f.name.trim(),
    gender: f.gender || null,
    age: numOrNull(f.age),
    phone: (f.phone || '').trim() || null,
    emergency_contact: (f.emergency_contact || '').trim() || null,
    emergency_phone: (f.emergency_phone || '').trim() || null,
    start_date: (f.start_date || '').trim() || null,
    status: f.status || 'active',
    note: (f.note || '').trim() || null,
  }
}

async function submitClient() {
  const name = (clientForm.value.name || '').trim()
  if (!name) {
    clientEditError.value = '姓名不能为空'
    return
  }
  const age = clientForm.value.age.trim()
  if (age !== '' && !/^\d+$/.test(age)) {
    clientEditError.value = '年龄须为非负整数'
    return
  }
  clientEditBusy.value = true
  clientEditError.value = ''
  try {
    let res
    if (clientEditMode.value === 'edit') {
      res = await fetch(`/api/clients/${clientEditId.value}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(clientPayload()),
      })
    } else {
      res = await fetch('/api/clients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(clientPayload()),
      })
    }
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '保存来访者失败')
    clientEditOpen.value = false
    loadClients()
    loadSessions()
  } catch (err) {
    clientEditError.value = err.message || '保存来访者失败'
  } finally {
    clientEditBusy.value = false
  }
}

const clientDeleteTarget = ref(null)
const clientDeleteError = ref('')
const clientDeleteBusy = ref(false)

function openClientDelete(c) {
  clientDeleteTarget.value = c
  clientDeleteError.value = ''
  clientDeleteBusy.value = false
}

function closeClientDelete() {
  if (clientDeleteBusy.value) return
  clientDeleteTarget.value = null
}

async function runClientDelete() {
  const c = clientDeleteTarget.value
  if (!c) return
  clientDeleteBusy.value = true
  clientDeleteError.value = ''
  try {
    const res = await fetch(`/api/clients/${c.client_id}`, { method: 'DELETE' })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '删除来访者失败')
    clientDeleteTarget.value = null
    if (activeClientFilter.value === c.client_id) activeClientFilter.value = null
    loadClients()
    loadSessions()
    if (sessionData.value?.client_id === c.client_id) {
      sessionData.value = { ...sessionData.value, client_id: null, client_name: null }
    }
  } catch (err) {
    clientDeleteError.value = err.message || '删除来访者失败'
  } finally {
    clientDeleteBusy.value = false
  }
}

async function loadClients() {
  clientsLoading.value = true
  try {
    const res = await fetch('/api/clients')
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '加载来访者失败')
    clients.value = json.data?.clients || []
  } catch (err) {
    boardError.value = err.message || '加载来访者失败'
  } finally {
    clientsLoading.value = false
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
  loadClients()
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
          <svg
            v-if="themeIconType(opt) === 'sun'"
            class="theme-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="4" />
            <line x1="12" y1="2" x2="12" y2="5" />
            <line x1="12" y1="19" x2="12" y2="22" />
            <line x1="4.9" y1="4.9" x2="7" y2="7" />
            <line x1="17" y1="17" x2="19.1" y2="19.1" />
            <line x1="2" y1="12" x2="5" y2="12" />
            <line x1="19" y1="12" x2="22" y2="12" />
            <line x1="4.9" y1="19.1" x2="7" y2="17" />
            <line x1="17" y1="7" x2="19.1" y2="4.9" />
          </svg>
          <svg
            v-else
            class="theme-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
          </svg>
          {{ themeLabel(opt) }}
        </label>
      </div>
    </header>

    <main v-show="appView === 'board'" class="container dashboard">
      <!-- 左侧看板 -->
      <BoardSidebar
        :sessions="sessions"
        :groups="groups"
        :clients="clients"
        :clients-loading="clientsLoading"
        :active-client-filter="activeClientFilter"
        :board-loading="boardLoading"
        :groups-loading="groupsLoading"
        :board-error="boardError"
        :active-session-id="activeSessionId"
        @refresh="() => { loadSessions(); loadGroups(); loadClients() }"
        @select="selectSession"
        @move-session="moveSession"
        @assign-client="assignSessionClient"
        @filter-client="(id) => activeClientFilter = id"
        @delete-session="confirmDeleteSession"
        @edit-group="openGroupEdit"
        @delete-group="openGroupDelete"
        @edit-client="openClientEdit"
        @delete-client="openClientDelete"
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
          v-model:client-id="uploadClientId"
          :clients="clients"
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
          :clients="clients"
          :is-dark="isDark"
          :show-timestamps="showTimestamps"
          @save-brief="saveBrief"
          @save-tags="saveTags"
          @save-segment="patchSegment"
          @assign-client="(cid) => assignSessionClient(sessionData, cid)"
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

    <!-- T-S1.18：来访者建档/编辑弹层 -->
    <div v-if="clientEditOpen" class="modal-mask" @click.self="closeClientEdit">
      <div class="modal client-modal">
        <h3>{{ clientEditMode === 'edit' ? '编辑来访者' : '新增来访者' }}</h3>
        <div class="form-row">
          <label class="modal-label">
            姓名 <span class="required">*</span>
            <input v-model="clientForm.name" type="text" placeholder="必填" />
          </label>
        </div>
        <div class="form-row">
          <span class="modal-label-inline-label">性别</span>
          <label v-for="g in ['女', '男', '其他']" :key="g" class="radio-pill">
            <input v-model="clientForm.gender" type="radio" :value="g" />
            {{ g }}
          </label>
        </div>
        <div class="form-row two-col">
          <label class="modal-label">
            年龄
            <input v-model="clientForm.age" type="text" inputmode="numeric" placeholder="选填" />
          </label>
          <label class="modal-label">
            电话
            <input v-model="clientForm.phone" type="text" placeholder="选填" />
          </label>
        </div>
        <div class="form-row two-col">
          <label class="modal-label">
            紧急联系人
            <input v-model="clientForm.emergency_contact" type="text" placeholder="选填" />
          </label>
          <label class="modal-label">
            紧急联系人电话
            <input v-model="clientForm.emergency_phone" type="text" placeholder="选填" />
          </label>
        </div>
        <div class="form-row two-col">
          <label class="modal-label">
            咨询开始时间
            <input v-model="clientForm.start_date" type="date" />
          </label>
          <label class="modal-label">
            状态
            <select v-model="clientForm.status">
              <option value="active">进行中</option>
              <option value="disabled">已结束</option>
            </select>
          </label>
        </div>
        <div class="form-row">
          <label class="modal-label">
            备注
            <textarea v-model="clientForm.note" rows="3" placeholder="选填"></textarea>
          </label>
        </div>
        <div v-if="clientEditError" class="error-box"><p>{{ clientEditError }}</p></div>
        <div class="edit-actions">
          <button
            class="btn small primary"
            type="button"
            :disabled="clientEditBusy"
            @click="submitClient"
          >
            保存
          </button>
          <button class="btn small secondary" type="button" :disabled="clientEditBusy" @click="closeClientEdit">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- T-S1.18：来访者删除确认弹层 -->
    <div v-if="clientDeleteTarget" class="modal-mask" @click.self="closeClientDelete">
      <div class="modal">
        <h3>删除来访者「{{ clientDeleteTarget.name }}」</h3>
        <p class="confirm-msg">
          名下 <strong>{{ clientDeleteTarget.session_count }}</strong> 条记录将保留并归为未关联。
        </p>
        <div v-if="clientDeleteError" class="error-box"><p>{{ clientDeleteError }}</p></div>
        <div class="edit-actions">
          <button
            class="btn small danger"
            type="button"
            :disabled="clientDeleteBusy"
            @click="runClientDelete"
          >
            确认删除
          </button>
          <button class="btn small secondary" type="button" :disabled="clientDeleteBusy" @click="closeClientDelete">
            取消
          </button>
        </div>
      </div>
    </div>

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

.theme-icon {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
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

.client-modal {
  width: min(480px, 100%);
}

.required {
  color: var(--danger);
}

.modal-label-inline-label {
  font-size: 0.85rem;
  color: var(--muted);
}

.radio-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  font-size: 0.85rem;
  color: var(--text);
  cursor: pointer;
  background: var(--surface);
}

.radio-pill input[type='radio'] {
  accent-color: var(--primary);
}

.form-row.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.modal-label textarea,
.modal-label select {
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  color: var(--text);
  font-size: 0.9rem;
  font-family: inherit;
}

.modal-label textarea {
  resize: vertical;
  min-height: 64px;
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

  .form-row.two-col {
    grid-template-columns: 1fr;
  }
}
</style>
