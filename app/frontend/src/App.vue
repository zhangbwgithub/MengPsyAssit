<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

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
    const sys = matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
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

// 每人一色调色板（按代号首现序分配；浅背景 + 同色系边框 + 深色文字）
const SPEAKER_PALETTE = [
  { bg: '#eef4ff', border: '#b7d0fb', text: '#1e409e' }, // 蓝
  { bg: '#e8f7f0', border: '#a9e2c6', text: '#146c4b' }, // 绿
  { bg: '#fdf4e3', border: '#f2d49b', text: '#8f5a12' }, // 琥珀
  { bg: '#f1eefb', border: '#cfc2f2', text: '#5b3bb0' }, // 紫
  { bg: '#fcecf0', border: '#f4bdcb', text: '#9c2f4f' }, // 玫红
  { bg: '#e7f6fa', border: '#b2e2ee', text: '#0f6b79' }, // 青
]
// 暗色气泡同色系（深底 + 亮文字，保证对比度）
const SPEAKER_PALETTE_DARK = [
  { bg: '#1d2a44', border: '#3a5a96', text: '#aecbff' },
  { bg: '#1c3126', border: '#3a6b52', text: '#a3e6c5' },
  { bg: '#392f1d', border: '#735d2e', text: '#f0d6a0' },
  { bg: '#2c2544', border: '#5b4a96', text: '#cdbbf5' },
  { bg: '#3d242c', border: '#7a3c4c', text: '#f2b9cb' },
  { bg: '#1c3036', border: '#3d6773', text: '#a3dce7' },
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

// T-S1.12：看板排序/筛选/折叠/分组
const sortKey = ref('started_at')
const sortAsc = ref(false) // 各键默认降序（时间倒序=现状）
const groupFilter = ref('')
const foldByAudio = ref(false)
const expandedAudios = ref({})
const groups = ref([])
const groupsLoading = ref(false)
const activeFoldAudios = {}
const expandedGroups = ref({})

const sortOptions = [
  { value: 'started_at', label: '上传时间' },
  { value: 'duration_sec', label: '时长' },
  { value: 'word_count', label: '字数' },
  { value: 'original_filename', label: '文件名' },
]

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
// T-S1.12：排序/筛选/折叠纯前端计算（基列表由 loadSessions 刷新）
const _collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })

const filteredSessions = computed(() => {
  const tagSel = new Set(
    (selectedTags.value || []).map((t) => String(t).trim()).filter(Boolean)
  )
  let rows = sessions.value
  if (tagSel.size > 0) {
    rows = rows.filter((s) => (s.tags || []).some((t) => tagSel.has(t)))
  }
  if (groupFilter.value !== '' && groupFilter.value != null) {
    rows = rows.filter((s) => String(s.group_id || '') === String(groupFilter.value))
  }
  return rows
})

const sortedSessions = computed(() => {
  const rows = [...filteredSessions.value]
  rows.sort((a, b) => {
    const key = sortKey.value
    let cmp = 0
    if (key === 'original_filename') {
      cmp = _collator.compare(a.original_filename || '', b.original_filename || '')
    } else if (key === 'started_at') {
      cmp = String(a.started_at || '').localeCompare(String(b.started_at || ''))
    } else {
      cmp = (a[key] || 0) - (b[key] || 0)
    }
    if (cmp === 0) cmp = (a.session_id || 0) - (b.session_id || 0)
    return sortAsc.value ? cmp : -cmp
  })
  return rows
})

const displayTree = computed(() => {
  const rows = sortedSessions.value
  const out = []
  for (const key of Object.keys(activeFoldAudios)) delete activeFoldAudios[key]
  for (const s of rows) {
    if (foldByAudio.value && s.original_filename) {
      if (activeFoldAudios[s.original_filename]) {
        continue
      }
      const members = rows.filter((r) => r.original_filename === s.original_filename)
      if (members.length > 1) {
        activeFoldAudios[s.original_filename] = true
        out.push({ type: 'file', key: 'file:' + s.original_filename, name: s.original_filename, members })
        continue
      }
    }
    out.push({ type: 'session', key: 's:' + s.session_id, session: s })
  }
  // 分组折叠：同 group_id 的≥2条记录聚合为一个组头（组名/标签/备注），
  // 组头插入到该组最早一条记录所在位置；成员从会话节点/文件折叠节点中移除。
  const byGid = new Map()
  for (const s of rows) {
    if (!s.group_id) continue
    const bucket = byGid.get(s.group_id) || []
    bucket.push(s)
    byGid.set(s.group_id, bucket)
  }
  const groupNodes = []
  const groupedIds = new Set()
  for (const [gid, members] of byGid.entries()) {
    if (members.length < 2) continue
    for (const m of members) groupedIds.add(m.session_id)
    groupNodes.push({
      type: 'group',
      key: 'g:' + gid,
      name: members[0].group_name || `分组 #${gid}`,
      group_id: gid,
      members,
      anchorId: members[0].session_id,
    })
  }
  if (groupNodes.length) {
    const byAnchor = new Map(groupNodes.map((g) => [g.anchorId, g]))
    const result = []
    const emittedGroup = new Set()
    for (const n of out) {
      if (n.type === 'file') {
        const remaining = n.members.filter((m) => !groupedIds.has(m.session_id))
        for (const m of n.members) {
          const gn = byAnchor.get(m.session_id)
          if (gn && !emittedGroup.has(gn.key)) {
            result.push(gn)
            emittedGroup.add(gn.key)
          }
        }
        if (remaining.length > 0) {
          result.push({ ...n, members: remaining })
        }
      } else if (n.type === 'session') {
        if (groupedIds.has(n.session.session_id)) {
          const gn = byAnchor.get(n.session.session_id)
          if (gn && !emittedGroup.has(gn.key)) {
            result.push(gn)
            emittedGroup.add(gn.key)
          }
        } else {
          result.push(n)
        }
      }
    }
    // 兜底：anchor 理论上必在 out 中，若不在也补上，避免丢组
    for (const gn of groupNodes) {
      if (!emittedGroup.has(gn.key)) result.push(gn)
    }
    out.splice(0, out.length, ...result)
  }
  return out
})

const tagFilterSet = computed(() => {
  const set = new Set()
  for (const s of sessions.value) {
    for (const t of s.tags || []) {
      if (t) set.add(t)
    }
  }
  return set
})
const allTags = computed(() => [...tagFilterSet.value].sort((a, b) => _collator.compare(a, b)))
const selectedTags = ref([])

const durationMMSS = (sec) => {
  const totalSeconds = Math.max(0, Math.round(sec || 0))
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
const truncate = (text, max) => {
  const t = text || ''
  return t.length > max ? t.slice(0, max) + '…' : t
}

const sortedGroups = computed(() => {
  const list = [...groups.value]
  list.sort((a, b) => {
    const ca = (a.tags || []).join(',')
    const cb = (b.tags || []).join(',')
    const c = _collator.compare(cb, ca)
    return c === 0 ? (b.group_id || 0) - (a.group_id || 0) : c
  })
  return list
})
const groupOptions = computed(() => [
  { value: '', label: '未分组' },
  ...sortedGroups.value.map((g) => ({ value: g.group_id, label: g.name })),
])

// T-S1.12：摘要/标签回看详情编辑（PATCH /sessions/{id}）
const summaryBefore = (s) => (s.brief || '').slice(0, 100)
const summaryDisplay = (s) => {
  const brief = s.brief || ''
  if (brief) return brief.slice(0, 100)
  return (s.record?.summary || '').slice(0, 100)
}
const sessionTags = (s) => s.tags || []

// 结果区摘要/标签内联编辑状态
const editOpen = ref(false)
const editTargetId = ref(null)
const editType = ref('brief')
const editBriefValue = ref('')
const editTagsValue = ref('')
const editError = ref('')

function openEditPanel(s, type) {
  editOpen.value = true
  editTargetId.value = s.session_id
  editType.value = type
  editError.value = ''
  if (type === 'brief') {
    editBriefValue.value = summaryBefore(s)
  } else {
    editTagsValue.value = sessionTags(s).join(', ')
  }
}

async function saveEdit(s) {
  editError.value = ''
  try {
    if (editType.value === 'brief') {
      const brief = editBriefValue.value.replace(/\s+$/, '')
      if (brief.length > 100) {
        editError.value = '摘要不能超过 100 字'
        return
      }
      await saveBrief(s, { brief })
    } else {
      const tags = (editTagsValue.value || '')
        .split(/[,，]/)
        .map((t) => t.trim())
        .filter(Boolean)
      await saveTags(s, { tags })
    }
    editOpen.value = false
    editTargetId.value = null
  } catch (err) {
    editError.value = err.message || '保存失败'
  }
}

function cancelEdit() {
  editOpen.value = false
  editTargetId.value = null
  editError.value = ''
}

async function loadedDetail(id) {
  if (sessionData.value && sessionData.value.session_id === id && sessionData.value.status) {
    return sessionData.value
  }
  const res = await fetch(`/api/sessions/${id}`)
  const json = await res.json()
  if (!json.ok) throw new Error(json.error?.message || '加载会话失败')
  return json.data
}

async function saveBrief(item, payload) {
  if ((payload.brief || '').length > 100) {
    throw new Error('摘要不能超过 100 字')
  }
  const data = await patchSession(item, payload)
  const brief = data.brief || ''
  if (sessionData.value?.session_id === item.session_id) {
    sessionData.value = { ...sessionData.value, brief, tags: data.tags || [] }
  }
  boardError.value = ''
  return data
}

async function saveTags(item, payload) {
  const data = await patchSession(item, payload)
  if (sessionData.value?.session_id === item.session_id) {
    sessionData.value = { ...sessionData.value, tags: data.tags || [] }
  }
  boardError.value = ''
  return data
}

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

function toggleAudioFold(name) {
  expandedAudios.value[name] = !expandedAudios.value[name]
}

function toggleGroupFold(id) {
  expandedGroups.value[id] = !expandedGroups.value[id]
}

async function moveSession(s, groupId) {
  boardError.value = ''
  try {
    const payload = groupId === '' || groupId == null ? { group_id: null } : { group_id: Number(groupId) }
    const data = await patchSession(s, payload)
    if (sessionData.value?.session_id === s.session_id) {
      const keep = sessionData.value
      await loadedDetail(s.session_id)
        .then((d) => (sessionData.value = { ...keep, ...d }))
        .catch(() => (sessionData.value = { ...keep, group_id: data.group_id }))
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
    }
    loadGroups()
  } catch (err) {
    boardError.value = err.message || '删除失败'
  }
}

// ── T-S1.12 分组面板：新建/编辑/删除/成员 ──────────────────
const expandedMembers = ref({})
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
  const payload = {
    name,
    tags: parseGroupTags(groupEditTags.value),
    note: groupEditNote.value.trim(),
  }
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

// 全站确认弹层（T-S1.12）：记录删除 / 分组删除
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

function confirmDeleteGroup(g) {
  confirmTitle.value = '删除分组'
  confirmMessage.value = `确定删除分组「${g.name}」？组内记录将变为未分组，不会删除。`
  confirmAction.value = async () => {
    const res = await fetch(`/api/groups/${g.group_id}`, { method: 'DELETE' })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error?.message || '删除分组失败')
    loadGroups()
    loadSessions()
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

function expandMembers(g) {
  expandedMembers.value[g.group_id] = !expandedMembers.value[g.group_id]
}

function membersOf(g) {
  return sessions.value.filter((s) => s.group_id === g.group_id)
}

function groupOf(gid) {
  return groups.value.find((g) => g.group_id === gid)
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

// 按代号首现序建立「代号 → 调色板颜色」映射（每人一色，随主题换色板）
const speakerColors = computed(() => {
  const map = {}
  const palette = isDark.value ? SPEAKER_PALETTE_DARK : SPEAKER_PALETTE
  for (const seg of sessionData.value?.segments || []) {
    if (seg.speaker && !(seg.speaker in map)) {
      map[seg.speaker] = palette[Object.keys(map).length % palette.length]
    }
  }
  return map
})

const isDark = computed(() => isDarkTheme.value)

function colorOf(speaker) {
  const fallback = isDark.value
    ? { bg: '#232832', border: '#3a4250', text: '#e6e9ef' }
    : { bg: '#f3f4f6', border: '#d1d5db', text: '#374151' }
  return (
    speakerColors.value[speaker] || fallback
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

// 结果区板块折叠（默认展开，纯前端）
const collapsedBlocks = ref({})
function toggleBlock(name) {
  collapsedBlocks.value[name] = !collapsedBlocks.value[name]
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

        <div class="board-tools">
          <label class="board-sort">
            排序
            <select v-model="sortKey">
              <option v-for="o in sortOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </option>
            </select>
          </label>
          <button
            class="btn small board-dir"
            type="button"
            @click="sortAsc = !sortAsc"
          >
            {{ sortAsc ? '升序 ↑' : '降序 ↓' }}
          </button>
          <label class="board-fold">
            <input type="checkbox" v-model="foldByAudio" />
            按音频折叠
          </label>
        </div>

        <div v-if="allTags.length" class="board-filter">
          <span class="board-filter-label">标签</span>
          <label
            v-for="t in allTags"
            :key="t"
            class="tag-check"
          >
            <input type="checkbox" :value="t" v-model="selectedTags" />
            {{ t }}
          </label>
        </div>

        <div v-if="sortedGroups.length" class="board-filter">
          <label class="board-sort">
            组筛选
            <select v-model="groupFilter">
              <option value="">全部</option>
              <option
                v-for="g in sortedGroups"
                :key="g.group_id"
                :value="g.group_id"
              >
                {{ g.name }}（{{ g.member_count }}）
              </option>
            </select>
          </label>
        </div>

        <div v-if="sessions.length === 0 && !boardLoading" class="board-empty">
          暂无记录
        </div>

        <ul
          v-else-if="displayTree.length"
          class="board-list"
        >
          <li
            v-for="node in displayTree"
            :key="node.key"
            class="board-row"
          >
            <template v-if="node.type === 'file'">
              <div class="board-item group-row board-folder" @click="toggleAudioFold(node.name)">
                <span class="board-id">{{ truncate(node.name, 24) }}</span>
                <span class="board-badge muted">{{ node.members.length }} 条</span>
                <span class="board-folder-arrow">
                  {{ expandedAudios[node.name] ? '▾' : '▸' }}
                </span>
              </div>
              <ul v-if="expandedAudios[node.name]" class="board-list sub">
                <li v-for="m in node.members" :key="m.session_id">
                  <div
                    class="board-item"
                    :class="{ active: isActiveSession(m.session_id) }"
                    @click="selectSession(m.session_id)"
                  >
                    <span class="board-id">#{{ m.session_id }}</span>
                    <span class="board-badge clear">{{ boardStatusText(m.status) }}</span>
                    <span class="board-time">{{ formatStartedAt(m.started_at) }}</span>
                  </div>
                </li>
              </ul>
            </template>
            <template v-else-if="node.type === 'group'">
              <div class="board-item group-row board-folder" @click="toggleGroupFold(node.group_id)">
                <span class="board-id">{{ node.name }}</span>
                <span
                  v-for="(t, i) in (groupOf(node.group_id)?.tags || [])"
                  :key="'gt' + i"
                  class="tag-pill"
                >
                  {{ t }}
                </span>
                <span class="board-badge muted">{{ node.members.length }} 条</span>
                <span class="board-folder-arrow">
                  {{ expandedGroups[node.group_id] ? '▾' : '▸' }}
                </span>
              </div>
              <p
                v-if="groupOf(node.group_id)?.note"
                class="group-note"
              >
                {{ groupOf(node.group_id).note }}
              </p>
              <ul v-if="expandedGroups[node.group_id]" class="board-list sub">
                <li v-for="m in node.members" :key="m.session_id">
                  <div
                    class="board-item"
                    :class="{ active: isActiveSession(m.session_id) }"
                    @click="selectSession(m.session_id)"
                  >
                    <span class="board-id">#{{ m.session_id }}</span>
                    <span class="board-badge clear">{{ boardStatusText(m.status) }}</span>
                    <span class="board-time">{{ formatStartedAt(m.started_at) }}</span>
                  </div>
                </li>
              </ul>
            </template>
            <template v-else>
              <div
                class="board-item"
                :class="{ active: isActiveSession(node.session.session_id) }"
                @click="selectSession(node.session.session_id)"
              >
                <span class="board-id">#{{ node.session.session_id }}</span>
                <span
                  class="board-badge"
                  :class="boardStatusClass(node.session.status)"
                >
                  <span
                    v-if="node.session.status !== 'done' && node.session.status !== 'failed'"
                    class="board-spinner"
                  ></span>
                  {{ boardStatusText(node.session.status) }}
                </span>
                <span
                  v-if="node.session.group_name"
                  class="board-badge muted group"
                >
                  {{ node.session.group_name }}
                </span>
                <span class="board-time">
                  {{ formatStartedAt(node.session.started_at) }}
                </span>
              </div>
              <div class="board-meta">
                <span class="board-filename" :title="node.session.original_filename">
                  {{ truncate(node.session.original_filename || '—', 22) }}
                </span>
                <span class="board-detail">⏱ {{ durationMMSS(node.session.duration_sec) }}</span>
                <span class="board-detail">字 {{ node.session.word_count ?? 0 }}</span>
                <span class="board-move-row">
                  <select
                    class="board-group-select"
                    :value="String(node.session.group_id || '')"
                    @change="moveSession(node.session, $event.target.value)"
                    @click.stop
                  >
                    <option
                      v-for="g in groupOptions"
                      :key="g.value"
                      :value="g.value"
                    >
                      {{ g.label }}
                    </option>
                  </select>
                  <button
                    class="btn small board-del"
                    type="button"
                    @click="confirmDeleteSession(node.session)"
                  >
                    删除
                  </button>
                </span>
              </div>
            </template>
          </li>
        </ul>
        <p v-else-if="boardLoading" class="board-empty">加载中…</p>
        <p v-else class="board-empty">无匹配记录</p>

        <div class="group-panel">
          <div class="group-header">
            <h3>分组</h3>
            <button
              class="btn small secondary"
              type="button"
              @click="openGroupEdit()"
            >
              新建分组
            </button>
          </div>
          <p v-if="groupsLoading" class="board-empty">分组加载中…</p>
          <ul class="group-list">
            <li
              v-for="g in sortedGroups"
              :key="g.group_id"
              class="group-item"
            >
              <div class="group-line">
                <span class="group-name">{{ g.name }}</span>
                <button
                  v-for="(t, i) in (g.tags || [])"
                  :key="i"
                  class="tag-pill"
                  type="button"
                >
                  {{ t }}
                </button>
                <button
                  class="btn small board-del-outline"
                  type="button"
                  @click="confirmDeleteGroup(g)"
                >
                  删除
                </button>
              </div>
              <p v-if="g.note" class="group-note">{{ g.note }}</p>
              <p class="group-count">{{ g.member_count }} 条记录</p>
              <button
                class="btn small secondary"
                type="button"
                @click="openGroupEdit(g)"
              >
                编辑
              </button>
              <button
                class="btn small secondary"
                type="button"
                @click="expandMembers(g)"
              >
                成员
              </button>
              <div v-if="expandedMembers[g.group_id]" class="group-members">
                <ul class="board-list sub">
                  <li v-for="m in membersOf(g)" :key="m.session_id">
                    <button
                      class="board-members-elem"
                      type="button"
                      @click="selectSession(m.session_id)"
                    >
                      #{{ m.session_id }}
                    </button>
                  </li>
                </ul>
              </div>
            </li>
          </ul>
          <p v-if="sortedGroups.length === 0 && !groupsLoading" class="board-empty">
            暂无分组
          </p>
        </div>
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

        <div v-if="sessionData" class="result-meta-panel">
          <div class="result-meta-row">
            <span class="record-key">摘要</span>
            <p class="result-meta-value">{{ summaryDisplay(sessionData) || '暂无' }}</p>
            <button class="btn small secondary" type="button" @click="openEditPanel(sessionData, 'brief')">
              编辑
            </button>
          </div>
          <div class="result-meta-row">
            <span class="record-key">标签</span>
            <div class="tag-chip-list">
              <span v-for="(t, i) in sessionTags(sessionData)" :key="i" class="tag-chip">
                {{ t }}
              </span>
              <span v-if="!sessionTags(sessionData).length" class="tag-empty">无标签</span>
            </div>
            <button class="btn small secondary" type="button" @click="openEditPanel(sessionData, 'tags')">
              编辑
            </button>
          </div>
          <div v-if="editOpen && editTargetId === sessionData.session_id" class="edit-panel">
            <template v-if="editType === 'brief'">
              <textarea
                v-model="editBriefValue"
                class="edit-input"
                rows="3"
                maxlength="100"
                placeholder="摘要（≤100 字）"
              ></textarea>
            </template>
            <template v-else>
              <input
                v-model="editTagsValue"
                class="edit-input"
                type="text"
                placeholder="标签（逗号分隔）"
              />
            </template>
            <div class="edit-actions">
              <button class="btn small primary" type="button" @click="saveEdit(sessionData)">
                保存
              </button>
              <button class="btn small secondary" type="button" @click="cancelEdit">
                取消
              </button>
            </div>
          </div>
          <div v-if="editError && editTargetId === sessionData.session_id" class="error-box">
            <p>{{ editError }}</p>
          </div>
        </div>

        <div class="result-block" v-if="sessionData.record">
          <h3 class="result-block-title">
            <button class="block-toggle" type="button" @click="toggleBlock('record')">
              <span class="fold-marker">{{ collapsedBlocks.record ? '▸' : '▾' }}</span>
              咨询记录
            </button>
          </h3>
          <div class="record-card" v-show="!collapsedBlocks.record">
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

    <!-- 删除/操作确认弹层 -->
    <div v-if="confirmOpen" class="modal-mask" @click.self="cancelConfirm">
      <div class="modal">
        <h3>{{ confirmTitle }}</h3>
        <p class="confirm-msg">{{ confirmMessage }}</p>
        <div class="edit-actions">
          <button class="btn small primary" type="button" @click="runConfirmAction">确认</button>
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
  color: var(--on-primary);
}

.board-error {
  margin-bottom: 10px;
  padding: 8px 10px;
  background: var(--danger-soft);
  border: 1px solid var(--danger-border);
  border-radius: 8px;
  color: var(--danger);
  font-size: 0.8rem;
}

.board-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.board-sort {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--muted);
}

.board-sort select,
.board-group-select {
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 0.8rem;
  max-width: 150px;
}

.board-dir {
  padding: 3px 6px;
  font-size: 0.72rem;
}

.board-fold {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--muted);
  cursor: pointer;
}

.board-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.board-filter-label {
  font-size: 0.78rem;
  color: var(--muted);
}

.tag-check {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  font-size: 0.72rem;
  color: var(--muted);
  cursor: pointer;
  background: var(--surface);
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

.board-list.sub {
  gap: 4px;
  padding-left: 8px;
}

.board-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.board-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  color: var(--text);
}

.board-item:hover {
  border-color: var(--primary-hover-border);
  background: var(--hover);
}

.board-item.active {
  border-color: var(--primary);
  background: var(--hover);
}

.board-item.group-row {
  cursor: pointer;
  background: var(--surface);
}

.board-folder-arrow {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.8rem;
}

.board-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 4px 4px 4px;
  font-size: 0.75rem;
  color: var(--muted);
}

.board-filename {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.board-detail {
  white-space: nowrap;
}

.board-move-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.board-del {
  padding: 2px 8px;
  font-size: 0.72rem;
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid var(--danger-border);
}

.board-del-outline {
  padding: 2px 8px;
  font-size: 0.72rem;
  background: transparent;
  color: var(--danger);
  border: 1px solid var(--danger-border);
  margin-left: auto;
}

.board-badge.muted,
.board-badge.clear {
  background: var(--surface);
  color: var(--muted);
}

.board-badge.group {
  background: var(--primary-soft);
  color: var(--primary-dark);
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

.board-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--border-subtle);
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

/* 结果区摘要/标签元信息行与内联编辑 */
.result-meta-panel {
  margin-bottom: 16px;
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

/* 结果板块标题折叠 */
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

/* 分组面板 */
.group-panel {
  margin-top: 16px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.group-header h3 {
  margin: 0;
  font-size: 0.92rem;
  color: var(--text);
}

.group-list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.group-item {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--card-inset);
}

.group-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.group-name {
  font-weight: 600;
  font-size: 0.86rem;
  color: var(--text);
}

.group-note {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 0.78rem;
}

.group-count {
  margin: 2px 0 6px;
  color: var(--muted);
  font-size: 0.75rem;
}

.group-members {
  margin-top: 6px;
}

.board-members-elem {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: var(--primary-dark);
  cursor: pointer;
  font-size: 0.82rem;
  padding: 2px 0;
}

.board-members-elem:hover {
  text-decoration: underline;
}

/* 弹层 */
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

.confirm-msg {
  margin: 0 0 12px;
  color: var(--text);
  font-size: 0.92rem;
  word-break: break-word;
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
