// 前端共用格式化工具（本地时区口径与后端 naive-UTC 约定一致）

// 后端 started_at 为 naive UTC（无时区后缀），JS 会把无后缀串当本地时间；
// 显式补 'Z' 使 new Date 按 UTC 解析，再转浏览器本地时区输出。
export function parseStartedAt(value) {
  if (!value) return null
  const date = new Date(`${value}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatStartedAt(value) {
  const date = parseStartedAt(value)
  if (!date) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatStartedAtFull(value) {
  const date = parseStartedAt(value)
  if (!date) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// 本地时区 YYYY-MM-DD（用于日历与日期过滤）
export function localDateKey(value) {
  const date = parseStartedAt(value)
  if (!date) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// key（YYYY-MM-DD）→ { year, month(1-12), day }
export function splitDateKey(key) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key || '')
  if (!m) return null
  return { year: +m[1], month: +m[2], day: +m[3] }
}

export function todayKey() {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export function formatAsDateKey(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function durationMMSS(sec) {
  const totalSeconds = Math.max(0, Math.round(sec || 0))
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function formatMs(ms) {
  const totalSeconds = Math.floor((ms || 0) / 1000)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function truncate(value, max) {
  const t = value || ''
  return t.length > max ? t.slice(0, max) + '…' : t
}
