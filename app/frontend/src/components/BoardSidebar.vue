<script setup>
import { ref, computed } from 'vue'
import CalendarMini from './CalendarMini.vue'
import {
  formatStartedAt,
  durationMMSS,
  localDateKey,
  truncate,
} from '../utils/format.js'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
  clients: { type: Array, default: () => [] },
  clientsLoading: { type: Boolean, default: false },
  activeClientFilter: { type: [Number, String], default: null },
  boardLoading: { type: Boolean, default: false },
  groupsLoading: { type: Boolean, default: false },
  boardError: { type: String, default: '' },
  activeSessionId: { type: [Number, String], default: null },
})

const emit = defineEmits([
  'select',
  'refresh',
  'move-session',
  'assign-client',
  'filter-client',
  'delete-session',
  'edit-group',
  'delete-group',
  'edit-client',
  'delete-client',
  'bulk-delete',
  'export',
])

// ── 排序 / 标签 / 组 / 音频折叠 ──────────────────────────────
const sortKey = ref('started_at')
const sortAsc = ref(false)
const groupFilter = ref('')
const foldByAudio = ref(false)
const expandedAudios = ref({})
const expandedGroups = ref({})
const selectedTags = ref([])
const dateFilter = ref('') // YYYY-MM-DD 或 ''
const activeFoldAudios = {}

const sortOptions = [
  { value: 'started_at', label: '上传时间' },
  { value: 'duration_sec', label: '时长' },
  { value: 'word_count', label: '字数' },
  { value: 'original_filename', label: '文件名' },
]

const _collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })

const filteredSessions = computed(() => {
  const tagSel = new Set(
    (selectedTags.value || []).map((t) => String(t).trim()).filter(Boolean)
  )
  let rows = props.sessions
  if (tagSel.size > 0) {
    rows = rows.filter((s) => (s.tags || []).some((t) => tagSel.has(t)))
  }
  if (groupFilter.value !== '' && groupFilter.value != null) {
    rows = rows.filter((s) => String(s.group_id || '') === String(groupFilter.value))
  }
  if (dateFilter.value) {
    rows = rows.filter((s) => localDateKey(s.started_at) === dateFilter.value)
  }
  if (props.activeClientFilter != null) {
    rows = rows.filter((s) => String(s.client_id ?? '') === String(props.activeClientFilter))
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

// ── 选择 / 全选 / 批量操作（以筛选后全集为准）──────────────
const selectMode = ref(false)
const selectedSet = ref(new Set())

const allFilteredIds = computed(() => new Set(sortedSessions.value.map((s) => s.session_id)))
const selectedCount = computed(
  () => [...selectedSet.value].filter((id) => allFilteredIds.value.has(id)).length
)
const allSelected = computed(
  () => allFilteredIds.value.size > 0 && selectedCount.value === allFilteredIds.value.size
)

function isChecked(id) {
  return selectedSet.value.has(id)
}

function toggleCheck(id) {
  const next = new Set(selectedSet.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedSet.value = next
}

function toggleSelectAll() {
  const next = new Set(selectedSet.value)
  if (allSelected.value) {
    // 取消全选：仅移除当前筛选全集里的 id
    for (const id of allFilteredIds.value) next.delete(id)
  } else {
    for (const id of allFilteredIds.value) next.add(id)
  }
  selectedSet.value = next
}

function clearSelection() {
  selectedSet.value = new Set()
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) clearSelection()
}

function exportSelected() {
  const ids = [...selectedSet.value].filter((id) => allFilteredIds.value.has(id))
  emit('export', ids)
}

function requestBulkDelete() {
  emit('bulk-delete', [...selectedSet.value].filter((id) => allFilteredIds.value.has(id)))
}

// ── 列表树（文件折叠 + 分组折叠，与原有逻辑一致）────────────
const displayTree = computed(() => {
  const rows = sortedSessions.value
  const out = []
  for (const key of Object.keys(activeFoldAudios)) delete activeFoldAudios[key]
  for (const s of rows) {
    if (foldByAudio.value && s.original_filename) {
      if (activeFoldAudios[s.original_filename]) continue
      const members = rows.filter((r) => r.original_filename === s.original_filename)
      if (members.length > 1) {
        activeFoldAudios[s.original_filename] = true
        out.push({
          type: 'file',
          key: 'file:' + s.original_filename,
          name: s.original_filename,
          members,
        })
        continue
      }
    }
    out.push({ type: 'session', key: 's:' + s.session_id, session: s })
  }
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
    for (const gn of groupNodes) {
      if (!emittedGroup.has(gn.key)) result.push(gn)
    }
    out.splice(0, out.length, ...result)
  }
  return out
})

// ── 标签 / 分组选项 ─────────────────────────────────────────
const tagFilterSet = computed(() => {
  const set = new Set()
  for (const s of props.sessions) {
    for (const t of s.tags || []) {
      if (t) set.add(t)
    }
  }
  return set
})
const allTags = computed(() => [...tagFilterSet.value].sort((a, b) => _collator.compare(a, b)))

const sortedGroups = computed(() => {
  const list = [...props.groups]
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

// ── T-S1.18：来访者名单（active 优先已由 API 排序保证）──────
const sortedClients = computed(() => props.clients)

const clientOptions = computed(() => [
  { value: '', label: '未关联' },
  ...sortedClients.value.map((c) => ({ value: String(c.client_id), label: c.name })),
])

function clientStatusText(c) {
  return c.status === 'disabled' ? '已结束' : '进行中'
}

function clientStatusClass(c) {
  return c.status === 'disabled' ? 'ended' : 'ongoing'
}

function clientNameOf(cid) {
  if (cid == null) return ''
  const c = props.clients.find((x) => x.client_id === Number(cid))
  return c?.name || ''
}

function isActiveClientFilter(cid) {
  return props.activeClientFilter != null && Number(props.activeClientFilter) === Number(cid)
}

// ── 分组成员展开 ───────────────────────────────────────────
const expandedMembers = ref({})
function expandMembers(g) {
  expandedMembers.value[g.group_id] = !expandedMembers.value[g.group_id]
}
function membersOf(g) {
  return props.sessions.filter((s) => s.group_id === g.group_id)
}
function groupOf(gid) {
  return props.groups.find((g) => g.group_id === gid)
}

// ── 勾选状态与本地 UI 辅助 ─────────────────────────────────
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

const isActiveSession = (id) => props.activeSessionId === id

const dateFilterCount = computed(() => filteredSessions.value.length)

function clearDateFilter() {
  dateFilter.value = ''
}

function onCalendarSelect(key) {
  dateFilter.value = key
}

function toggleAudioFold(name) {
  expandedAudios.value[name] = !expandedAudios.value[name]
}
function toggleGroupFold(id) {
  expandedGroups.value[id] = !expandedGroups.value[id]
}

// 行 checkbox 点击不触发选择会话
function checkboxClick(event) {
  event.stopPropagation()
}
</script>

<template>
  <aside class="board">
    <div class="board-header">
      <h2>看板</h2>
      <button
        class="btn board-refresh"
        type="button"
        :disabled="boardLoading"
        @click="emit('refresh')"
      >
        {{ boardLoading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div v-if="boardError" class="board-error">{{ boardError }}</div>

    <!-- T-S1.18：来访者区（名单点击过滤记录） -->
    <div class="panel-section client-panel">
      <div class="panel-head">
        <h3>来访</h3>
        <button class="btn small secondary" type="button" @click="emit('edit-client', undefined)">
          新增来访
        </button>
      </div>
      <p v-if="clientsLoading" class="board-empty">来访者加载中…</p>
      <ul v-else-if="sortedClients.length" class="client-list">
        <li
          v-for="c in sortedClients"
          :key="c.client_id"
          class="client-item"
          :class="{ 'filter-active': isActiveClientFilter(c.client_id) }"
        >
          <button class="client-main" type="button" @click="emit('filter-client', c.client_id)">
            <span class="client-name" :title="c.name">{{ truncate(c.name, 14) }}</span>
            <span class="client-badge" :class="clientStatusClass(c)">
              {{ clientStatusText(c) }}
            </span>
            <span class="client-count">{{ c.session_count }} 节</span>
          </button>
          <span class="client-actions">
            <button class="btn small client-action" type="button" @click="emit('edit-client', c)">
              编辑
            </button>
            <button class="btn small client-del" type="button" @click="emit('delete-client', c)">
              删除
            </button>
          </span>
        </li>
      </ul>
      <p v-else class="board-empty">暂无来访者</p>
    </div>

    <!-- 分组管理区（移上看板顶部） -->
    <div class="group-panel">
      <div class="group-header">
        <h3>分组</h3>
        <button class="btn small secondary" type="button" @click="emit('edit-group', undefined)">
          新建分组
        </button>
      </div>
      <p v-if="groupsLoading" class="board-empty">分组加载中…</p>
      <ul class="group-list">
        <li v-for="g in sortedGroups" :key="g.group_id" class="group-item">
          <div class="group-line">
            <span class="group-name">{{ g.name }}</span>
            <span v-for="(t, i) in g.tags || []" :key="i" class="tag-pill">{{ t }}</span>
            <button
              class="btn small group-action"
              type="button"
              @click="emit('edit-group', g)"
            >
              编辑
            </button>
            <button
              class="btn small board-del-outline"
              type="button"
              @click="emit('delete-group', g)"
            >
              删除
            </button>
          </div>
          <p v-if="g.note" class="group-note">{{ g.note }}</p>
          <p class="group-count">{{ g.member_count }} 条记录</p>
          <button
            class="btn small secondary group-members-toggle"
            type="button"
            @click="expandMembers(g)"
          >
            成员 {{ expandedMembers[g.group_id] ? '▾' : '▸' }}
          </button>
          <div v-if="expandedMembers[g.group_id]" class="group-members">
            <ul class="board-list sub">
              <li v-for="m in membersOf(g)" :key="m.session_id">
                <button
                  class="board-members-elem"
                  type="button"
                  @click="emit('select', m.session_id)"
                >
                  #{{ m.session_id }}
                </button>
              </li>
            </ul>
          </div>
        </li>
      </ul>
      <p v-if="sortedGroups.length === 0 && !groupsLoading" class="board-empty">暂无分组</p>
    </div>

    <!-- 日历索引（分组区与列表之间） -->
    <div class="calendar-zone">
      <div class="board-section-title">日历</div>
      <CalendarMini
        :sessions="sessions"
        :model-value="dateFilter"
        @select="onCalendarSelect"
      />
    </div>

    <!-- 日期过滤提示条 -->
    <div v-if="dateFilter" class="date-filter-bar">
      <span>{{ dateFilter }}</span><span> · </span><span>{{ dateFilterCount }} 条</span>
      <button class="date-clear" type="button" @click="clearDateFilter">清除</button>
    </div>

    <!-- 工具条：排序 / 折叠 / 选择模式 / 导出 / 全选 / 批量操作 -->
    <div class="board-tools">
      <label class="board-sort">
        排序
        <select v-model="sortKey">
          <option v-for="o in sortOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </label>
      <button class="btn small board-dir" type="button" @click="sortAsc = !sortAsc">
        {{ sortAsc ? '升序 ↑' : '降序 ↓' }}
      </button>
      <label class="board-fold">
        <input type="checkbox" v-model="foldByAudio" />
        按音频折叠
      </label>
    </div>
    <div class="board-tools board-tools-secondary">
      <label class="board-fold select-mode-toggle">
        <input type="checkbox" :checked="selectMode" @change="toggleSelectMode" />
        选择
      </label>
      <button class="btn small secondary" type="button" @click="exportSelected" title="导出全部或已选记录">
        导出
      </button>
      <button
        v-if="selectMode"
        class="btn small secondary"
        type="button"
        @click="toggleSelectAll"
      >
        {{ allSelected ? '取消全选' : '全选' }}
      </button>
    </div>

    <div v-if="selectMode && selectedCount >= 1" class="bulk-bar">
      <span class="bulk-count">已选 {{ selectedCount }} 条</span>
      <button class="btn small board-del" type="button" @click="requestBulkDelete">删除</button>
      <button class="btn small secondary" type="button" @click="exportSelected">导出</button>
      <button class="btn small secondary" type="button" @click="clearSelection">取消</button>
    </div>

    <div v-if="allTags.length" class="board-filter">
      <span class="board-filter-label">标签</span>
      <label v-for="t in allTags" :key="t" class="tag-check">
        <input type="checkbox" :value="t" v-model="selectedTags" />
        {{ t }}
      </label>
    </div>

    <div v-if="sortedGroups.length" class="board-filter">
      <label class="board-sort">
        组筛选
        <select v-model="groupFilter">
          <option value="">全部</option>
          <option v-for="g in sortedGroups" :key="g.group_id" :value="g.group_id">
            {{ g.name }}（{{ g.member_count }}）
          </option>
        </select>
      </label>
    </div>

    <div v-if="sortedClients.length" class="board-filter">
      <label class="board-sort">
        来访筛选
        <select
          :value="activeClientFilter != null ? String(activeClientFilter) : ''"
          @change="emit('filter-client', $event.target.value === '' ? null : $event.target.value)"
        >
          <option value="">全部</option>
          <option v-for="c in sortedClients" :key="c.client_id" :value="String(c.client_id)">
            {{ c.name }}（{{ c.session_count }} 节）
          </option>
        </select>
      </label>
    </div>

    <!-- 来访筛选提示条（清除方式与日期过滤一致） -->
    <div v-if="activeClientFilter != null" class="date-filter-bar">
      <span>来访者</span><span> · </span><span>{{ clientNameOf(activeClientFilter) }}</span>
      <button class="date-clear" type="button" @click="emit('filter-client', null)">清除</button>
    </div>

    <div v-if="sessions.length === 0 && !boardLoading" class="board-empty">暂无记录</div>

    <ul v-else-if="displayTree.length" class="board-list">
      <li v-for="node in displayTree" :key="node.key" class="board-row">
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
                @click="emit('select', m.session_id)"
              >
                <label v-if="selectMode" class="row-check" @click="checkboxClick">
                  <input
                    type="checkbox"
                    :checked="isChecked(m.session_id)"
                    @change="toggleCheck(m.session_id)"
                  />
                </label>
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
            <span v-for="(t, i) in groupOf(node.group_id)?.tags || []" :key="'gt' + i" class="tag-pill">
              {{ t }}
            </span>
            <span class="board-badge muted">{{ node.members.length }} 条</span>
            <span class="board-folder-arrow">
              {{ expandedGroups[node.group_id] ? '▾' : '▸' }}
            </span>
          </div>
          <p v-if="groupOf(node.group_id)?.note" class="group-note">
            {{ groupOf(node.group_id).note }}
          </p>
          <ul v-if="expandedGroups[node.group_id]" class="board-list sub">
            <li v-for="m in node.members" :key="m.session_id">
              <div
                class="board-item"
                :class="{ active: isActiveSession(m.session_id) }"
                @click="emit('select', m.session_id)"
              >
                <label v-if="selectMode" class="row-check" @click="checkboxClick">
                  <input
                    type="checkbox"
                    :checked="isChecked(m.session_id)"
                    @change="toggleCheck(m.session_id)"
                  />
                </label>
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
            @click="emit('select', node.session.session_id)"
          >
            <label v-if="selectMode" class="row-check" @click="checkboxClick">
              <input
                type="checkbox"
                :checked="isChecked(node.session.session_id)"
                @change="toggleCheck(node.session.session_id)"
              />
            </label>
            <span class="board-id">#{{ node.session.session_id }}</span>
            <span class="board-badge" :class="boardStatusClass(node.session.status)">
              <span
                v-if="node.session.status !== 'done' && node.session.status !== 'failed'"
                class="board-spinner"
              ></span>
              {{ boardStatusText(node.session.status) }}
            </span>
            <span v-if="node.session.group_name" class="board-badge muted group">
              {{ node.session.group_name }}
            </span>
            <span
              v-if="node.session.client_name"
              class="board-badge muted client"
              :title="'来访者：' + node.session.client_name"
            >
              {{ truncate(node.session.client_name, 8) }}
            </span>
            <span class="board-time">{{ formatStartedAt(node.session.started_at) }}</span>
          </div>
          <div class="board-meta">
            <span class="board-filename" :title="node.session.original_filename">
              {{ truncate(node.session.original_filename || '—', 22) }}
            </span>
            <span class="board-detail">{{ durationMMSS(node.session.duration_sec) }}</span>
            <span class="board-detail">字 {{ node.session.word_count ?? 0 }}</span>
            <span class="board-move-row">
              <select
                class="board-group-select"
                title="归属分组"
                :value="String(node.session.group_id || '')"
                @change="emit('move-session', node.session, $event.target.value)"
                @click.stop
              >
                <option v-for="g in groupOptions" :key="g.value" :value="g.value">
                  {{ g.label }}
                </option>
              </select>
              <select
                class="board-group-select client-assign"
                title="归属来访者"
                :value="String(node.session.client_id || '')"
                @change="emit('assign-client', node.session, $event.target.value)"
                @click.stop
              >
                <option v-for="c in clientOptions" :key="c.value" :value="c.value">
                  {{ c.label }}
                </option>
              </select>
              <button
                class="btn small board-del"
                type="button"
                @click="emit('delete-session', node.session)"
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
  </aside>
</template>

<style scoped>
.board {
  flex: 0 0 260px;
  width: 260px;
  position: sticky;
  top: 16px;
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
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

/* T-S1.18：来访者区 */
.panel-section.client-panel {
  margin-bottom: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 10px;
  background: var(--card-inset);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.panel-head h3 {
  margin: 0;
  font-size: 0.92rem;
  color: var(--text);
}

.client-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.client-item {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 6px 8px;
  background: var(--card);
}

.client-item.filter-active {
  border-color: var(--primary);
  background: var(--hover);
}

.client-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
  color: var(--text);
}

.client-name {
  font-weight: 600;
  font-size: 0.86rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.client-badge {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 0.7rem;
  white-space: nowrap;
  flex: 0 0 auto;
}

.client-badge.ongoing {
  background: var(--ok-bg);
  color: var(--ok-text);
}

.client-badge.ended {
  background: var(--surface);
  color: var(--muted);
}

.client-count {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--muted);
  flex: 0 0 auto;
}

.client-actions {
  display: inline-flex;
  gap: 4px;
  flex: 0 0 auto;
}

.client-action {
  padding: 2px 7px;
  font-size: 0.7rem;
}

.client-del {
  padding: 2px 7px;
  font-size: 0.7rem;
  background: transparent;
  color: var(--danger);
  border: 1px solid var(--danger-border);
}

/* 记录行上的来访者姓名徽标 */
.board-badge.client {
  background: var(--surface);
  color: var(--text);
}

.client-assign {
  max-width: 96px;
}

/* 分组管理区（顶部） */
.group-panel {
  margin-bottom: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 10px;
  background: var(--card-inset);
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.group-header h3 {
  margin: 0;
  font-size: 0.92rem;
  color: var(--text);
}

.group-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.group-item {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--card);
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

.group-action {
  padding: 2px 8px;
  font-size: 0.72rem;
}

.group-members-toggle {
  padding: 2px 8px;
  font-size: 0.72rem;
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

/* 日历 */
.calendar-zone {
  margin-bottom: 10px;
}

.board-section-title {
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 4px;
}

.date-filter-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 10px;
  padding: 4px 8px;
  background: var(--primary-soft);
  border: 1px solid var(--primary-hover-border);
  border-radius: 8px;
  font-size: 0.78rem;
  color: var(--primary-dark);
}

.date-clear {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--danger);
  font-size: 0.76rem;
  cursor: pointer;
  padding: 0;
}

.date-clear:hover {
  text-decoration: underline;
}

/* 工具条 */
.board-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.board-tools-secondary {
  border-top: 1px dashed var(--border-subtle);
  padding-top: 8px;
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

.select-mode-toggle {
  font-weight: 600;
  color: var(--primary-dark);
}

.bulk-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
  padding: 6px 8px;
  background: var(--primary-soft);
  border: 1px solid var(--primary-hover-border);
  border-radius: 8px;
}

.bulk-count {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--primary-dark);
}

/* 筛选 */
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

/* 列表 */
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

.row-check {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  flex: 0 0 auto;
}

.row-check input {
  accent-color: var(--primary);
}

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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 767px) {
  .board {
    flex: 1 1 auto;
    width: 100%;
    position: static;
    max-height: none;
  }
}
</style>
