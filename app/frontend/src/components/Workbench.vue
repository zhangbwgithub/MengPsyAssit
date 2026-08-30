<script setup>
// T-S1.16：工作台页（FB-013 前端）。数据来自 GET /api/dashboard/summary，
// 全纯 CSS/SVG 实现，不引图表库；组概览复用 App 传入的既有 /api/groups 数据。
import { computed } from 'vue'

const props = defineProps({
  summary: { type: Object, default: null }, // null=加载中；加载失败由父级 error + 重试承载
  groups: { type: Array, default: () => [] },
})

const emit = defineEmits(['goto-todo'])

// ── KPI ─────────────────────────────────────────────────
function round1(n) {
  return Math.round((Number(n) || 0) * 10) / 10
}

function computeDelta(cur, prev) {
  const c = Number(cur) || 0
  const p = Number(prev) || 0
  if (c === p) return { dir: 'flat', pct: 0 }
  if (p <= 0) return { dir: 'up', pct: null } // 上期为 0：无有意义百分比
  return {
    dir: c > p ? 'up' : 'down',
    pct: Math.round((Math.abs(c - p) / p) * 1000) / 10,
  }
}

const week = computed(() => props.summary?.week || {})
const totals = computed(() => props.summary?.totals || {})
const statusDist = computed(() => props.summary?.status_dist || [])
const tagCloud = computed(() => props.summary?.tag_cloud || [])
const trend = computed(() => props.summary?.trend || [])
const todos = computed(() => props.summary?.todos || {})

const deltaMap = {
  sessions: computed(() => computeDelta(week.value.sessions, week.value.sessions_prev)),
  hours: computed(() => computeDelta(week.value.hours, week.value.hours_prev)),
  avg: computed(() => computeDelta(week.value.avg_minutes, week.value.avg_minutes_prev)),
}

function deltaClass(d) {
  if (!d) return 'flat'
  if (d.dir === 'flat') return 'flat'
  return d.dir === 'up' ? 'up' : 'down'
}

function arrow(d) {
  if (!d || d.dir === 'flat') return '◆'
  return d.dir === 'up' ? '↑' : '↓'
}

function deltaText(d) {
  if (!d) return '—'
  if (d.dir === 'up') {
    return d.pct == null ? `较上周有增长` : `较上周 ↑ ${d.pct}%`
  }
  if (d.dir === 'down') {
    return d.pct == null ? `较上周下降` : `较上周 ↓ ${d.pct}%`
  }
  return `较上周持平（0%）`
}

function fmtWeekRange() {
  const w = week.value
  if (!w?.start) return '—'
  return `${w.start} ~ ${w.end}`
}

function fmtHours(h) {
  const v = round1(h)
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

// ── 环形图 ──────────────────────────────────────────────
const STATUS_META = {
  done: { color: '#16a34a' },
  processing: { color: '#2563eb' },
  failed: { color: '#dc2626' },
}
const DONUT_R = 54
const DONUT_C = 2 * Math.PI * DONUT_R
const GAP_FRACTION = 0.02 // 段间留白（不足 0.02 的全圆弧不缩）

function hue(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360
  return h
}

function clamp01(x) {
  return Math.max(0, Math.min(1, x))
}

const donutSegments = computed(() => {
  const items = (statusDist.value || [])
    .map((d) => ({ ...d, color: STATUS_META[d.status]?.color || '#94a3b8' }))
    .filter((d) => d.count > 0)
  const total = items.reduce((s, d) => s + d.count, 0)
  if (!total) return []
  let acc = 0
  return items.map((d) => {
    // 每段让出 GAP_FRACTION 做视觉分隔；多段时不影响段内占比展示
    const frac = d.count / total
    const dashLen = Math.max(0, (frac - GAP_FRACTION / items.length) * DONUT_C)
    const seg = {
      ...d,
      total,
      pct: Math.round(frac * 1000) / 10,
      dasharray: `${dashLen} ${DONUT_C - dashLen}`,
      dashoffset: -acc * DONUT_C,
    }
    acc += frac
    return seg
  })
})

const statusTotal = computed(() =>
  (statusDist.value || []).reduce((s, d) => s + (d.count || 0), 0)
)

// ── 词云 ────────────────────────────────────────────────
const cloudItems = computed(() => {
  const items = tagCloud.value || []
  if (!items.length) return []
  const minC = Math.min(...items.map((i) => i.count))
  const maxC = Math.max(...items.map((i) => i.count))
  const span = maxC - minC || 1
  return items.map((i, idx) => ({
    text: i.tag,
    count: i.count,
    // count 线性映射 12~28px；透明度整体抬升保证浅/深主题下可读
    size: Math.round(12 + ((i.count - minC) / span) * 16),
    raw: (i.count - minC) / span,
    // 确定性抖动：同数据渲染稳定（避免每次刷新跳色），两主题下均落在可读色相段
    h: (hue(i.tag) + idx * 17) % 360,
  }))
})

function cloudColor(it) {
  // hsl 色相 + 亮度随词频线性变化；亮度范围 24%~55% 在浅/深两主题下都可读
  return `hsl(${it.h} 42% ${Math.round(clamp01(0.92 - it.raw * 0.5) * 24 + 24)}%)`
}

// ── 近 14 天趋势 ────────────────────────────────────────
const trendEntries = computed(() => (trend.value || []).slice(-14))

const trendScale = computed(() => {
  const entries = trendEntries.value
  const maxV = Math.max(...entries.map((e) => Number(e.minutes) || 0), 0)
  return {
    maxV,
    pts: entries.map((e, i) => {
      const x = entries.length === 1 ? 330 : (i / (entries.length - 1)) * 660
      const y = maxV === 0 ? 120 : 120 - (Math.min(Number(e.minutes) || 0, maxV) / maxV) * 108
      return { ...e, x, y }
    }),
  }
})

const trendPts = computed(() => trendScale.value.pts)
const trendLine = computed(() =>
  trendPts.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
)
const trendArea = computed(() => {
  const pts = trendPts.value
  if (!pts.length) return ''
  return `${trendLine.value} L${pts[pts.length - 1].x.toFixed(1)},132 L${pts[0].x.toFixed(1)},132 Z`
})
const trendMaxLabels = computed(() => {
  const maxV = trendScale.value.maxV
  return [Math.ceil(maxV), Math.round(maxV / 2), 0]
})
const sparseTicks = computed(() => {
  const entries = trendEntries.value
  const n = entries.length
  const stride = n <= 5 ? 1 : n <= 14 ? 3 : 2
  return entries
    .map((e, i) => ({ label: (e.date || '').slice(5).replace('-', '/'), i }))
    .filter((t) => (t.i % stride === 0) || t.i === n - 1)
    .map((t) => {
      // 首/末刻度往内收，避免文字溢出画布
      const x = trendPts.value[t.i]?.x ?? 0
      const dx = t.i === 0 ? 0 : t.i === n - 1 ? -48 : 24
      return { ...t, x: Math.max(0, Math.min(632, x + dx)) }
    })
})

// ── 近 7 天工作量条形（第 4 格补位）──────────────────────
const barEntries = computed(() => (trend.value || []).slice(-7))

const barScale = computed(() => {
  const entries = barEntries.value
  const maxV = Math.max(...entries.map((e) => Number(e.sessions) || 0), 0)
  return entries.map((e) => {
    const v = Number(e.sessions) || 0
    return {
      ...e,
      v,
      pct: maxV === 0 ? 0 : Math.round((v / maxV) * 100),
      label: (e.date || '').slice(5),
    }
  })
})

// ── 待办 ────────────────────────────────────────────────
const todoCards = computed(() => [
  { key: 'no_brief', title: '待补摘要', desc: '记录缺少一句话摘要', count: todos.value.no_brief },
  { key: 'no_tags', title: '待补标签', desc: '记录缺少议题标签', count: todos.value.no_tags },
  { key: 'failed', title: '失败待处理', desc: '处理失败需重试/检查', count: todos.value.failed },
])

function safeCount(v) {
  return Number(v) || 0
}
</script>

<template>
  <div class="workbench">
    <section class="wb-section wb-kpis">
      <div class="wb-window">统计窗口：{{ fmtWeekRange() }}</div>
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-top">
            <svg class="kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="5" width="18" height="16" rx="2" />
              <line x1="3" y1="10" x2="21" y2="10" />
              <line x1="8" y1="3" x2="8" y2="7" />
              <line x1="16" y1="3" x2="16" y2="7" />
            </svg>
            <span class="kpi-window">本周</span>
          </div>
          <div class="kpi-num">{{ Number(week.sessions) || 0 }}</div>
          <div class="kpi-title">本周咨询数</div>
          <div class="kpi-delta" :class="deltaClass(deltaMap.sessions.value)">
            <span>{{ arrow(deltaMap.sessions.value) }}</span>
            {{ deltaText(deltaMap.sessions.value) }}
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <svg class="kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="13" r="8" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="13" x2="15" y2="15" />
              <line x1="9" y1="2" x2="15" y2="2" />
            </svg>
            <span class="kpi-unit">小时</span>
          </div>
          <div class="kpi-num">{{ fmtHours(week.hours) }}</div>
          <div class="kpi-title">本周咨询时长</div>
          <div class="kpi-delta" :class="deltaClass(deltaMap.hours.value)">
            <span>{{ arrow(deltaMap.hours.value) }}</span>
            {{ deltaText(deltaMap.hours.value) }}
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <svg class="kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <circle cx="12" cy="12" r="5" />
              <circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" />
            </svg>
            <span class="kpi-unit">分钟</span>
          </div>
          <div class="kpi-num">{{ Number(week.avg_minutes) || 0 }}</div>
          <div class="kpi-title">平均单次时长</div>
          <div class="kpi-delta" :class="deltaClass(deltaMap.avg.value)">
            <span>{{ arrow(deltaMap.avg.value) }}</span>
            {{ deltaText(deltaMap.avg.value) }}
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <svg class="kpi-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            </svg>
            <span class="kpi-window">累计</span>
          </div>
          <div class="kpi-num">{{ Number(totals.sessions) || 0 }}</div>
          <div class="kpi-title">累计记录数</div>
          <div class="kpi-delta flat">共 {{ Number(totals.groups) || 0 }} 个分组</div>
        </div>
      </div>
    </section>

    <section class="wb-section wb-charts">
      <div class="chart-grid">
        <!-- 咨询状态分布（环形图） -->
        <div class="chart-card">
          <h3 class="chart-title">咨询状态分布</h3>
          <div v-if="statusTotal === 0" class="chart-empty">
            <span class="chart-empty-icon">◌</span>
            <span class="chart-empty-text">暂无数据</span>
          </div>
          <div v-else class="donut-wrap">
            <svg class="donut" viewBox="0 0 160 160" role="img" aria-label="咨询状态分布环形图">
              <circle class="donut-track" cx="80" cy="80" :r="DONUT_R" />
              <g :transform="`translate(80,80) rotate(-90)`">
                <circle
                  v-for="(seg, i) in donutSegments"
                  :key="i"
                  class="donut-seg"
                  cx="0"
                  cy="0"
                  :r="DONUT_R"
                  :stroke="seg.color"
                  :stroke-dasharray="seg.dasharray"
                  :stroke-dashoffset="seg.dashoffset"
                />
              </g>
              <text class="donut-center-num" x="80" y="76" text-anchor="middle">
                {{ statusTotal }}
              </text>
              <text class="donut-center-label" x="80" y="94" text-anchor="middle">总记录</text>
            </svg>
            <ul class="donut-legend">
              <li v-for="seg in donutSegments" :key="seg.status" class="legend-row">
                <span class="legend-dot" :style="{ background: seg.color }"></span>
                <span class="legend-label">{{ seg.label }}</span>
                <span class="legend-val">{{ seg.count }} · {{ seg.pct }}%</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- 议题标签（词云） -->
        <div class="chart-card">
          <h3 class="chart-title">议题标签</h3>
          <div v-if="!cloudItems.length" class="chart-empty">
            <svg class="chart-empty-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M7 18h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.7 1.1A3.5 3.5 0 0 0 7 18z" />
            </svg>
            <span class="chart-empty-text">暂无数据</span>
          </div>
          <div v-else class="cloud">
            <span
              v-for="(it, i) in cloudItems"
              :key="i"
              class="cloud-tag"
              :style="{
                fontSize: it.size + 'px',
                color: cloudColor(it),
                background: `hsl(${it.h} 42% 55% / ${(0.08 + it.raw * 0.08).toFixed(2)})`,
              }"
              :title="`${it.text} ×${it.count}`"
            >{{ it.text }}</span>
          </div>
        </div>

        <!-- 近 14 天咨询时长（趋势） -->
        <div class="chart-card">
          <h3 class="chart-title">近 14 天咨询时长</h3>
          <div v-if="!trendEntries.length" class="chart-empty">
            <span class="chart-empty-icon">▁</span>
            <span class="chart-empty-text">暂无数据</span>
          </div>
          <div v-else class="line-wrap">
            <svg class="line-svg" viewBox="0 0 680 140" preserveAspectRatio="none" role="img" aria-label="近 14 天咨询时长趋势">
              <defs>
                <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="var(--primary)" stop-opacity="0.22" />
                  <stop offset="100%" stop-color="var(--primary)" stop-opacity="0.02" />
                </linearGradient>
              </defs>
              <g class="grid-lines">
                <line
                  v-for="(v, i) in trendMaxLabels"
                  :key="i"
                  x1="0"
                  :x2="680"
                  :y1="i * 60"
                  :y2="i * 60"
                />
                <text
                  v-for="(v, i) in trendMaxLabels"
                  :key="'y' + i"
                  class="y-label"
                  x="0"
                  :y="i === 0 ? 10 : i * 60 - 4"
                >{{ v }}</text>
              </g>
              <path v-if="trendArea" class="trend-area" :d="trendArea" />
              <polyline class="trend-line" :points="trendPts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')" />
              <circle
                v-for="(p, i) in trendPts"
                :key="i"
                class="trend-dot"
                :cx="p.x"
                :cy="p.y"
                r="2.6"
              >
                <title>第 {{ i + 1 }} 天 · {{ Number(p.minutes) || 0 }} 分钟 · {{ Number(p.sessions) || 0 }} 次</title>
              </circle>
              <text
                v-for="(t, i) in sparseTicks"
                :key="i"
                class="x-label"
                :x="t.x"
                y="136"
              >{{ t.label }}</text>
            </svg>
          </div>
        </div>

        <!-- 本周工作量（近 7 天条数） -->
        <div class="chart-card">
          <h3 class="chart-title">本周工作量</h3>
          <div v-if="barScale.every((b) => !b.v)" class="chart-empty">
            <span class="chart-empty-icon">▂</span>
            <span class="chart-empty-text">暂无数据</span>
          </div>
          <div v-else class="bars">
            <div v-for="(b, i) in barScale" :key="i" class="bar-col" :title="`${b.date} · ${b.v} 次`">
              <div class="bar-track">
                <div class="bar-fill" :style="{ height: b.pct + '%' }"></div>
              </div>
              <span class="bar-val">{{ b.v }}</span>
              <span class="bar-date">{{ b.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="wb-section wb-todos">
      <div class="todos-grid">
        <button
          v-for="card in todoCards"
          :key="card.key"
          type="button"
          class="todo-card"
          @click="emit('goto-todo', card.key)"
        >
          <span class="todo-icon" aria-hidden="true">
            <template v-if="card.key === 'no_brief'">⋯</template>
            <template v-else-if="card.key === 'no_tags'">#</template>
            <template v-else>!</template>
          </span>
          <span class="todo-text">
            <span class="todo-title">{{ card.title }}</span>
            <span class="todo-desc">{{ card.desc }}</span>
          </span>
          <span class="todo-badge" :class="{ zero: safeCount(card.count) === 0 }">
            {{ safeCount(card.count) }}
          </span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wb-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wb-window {
  align-self: flex-end;
  font-size: 0.78rem;
  color: var(--muted);
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 2px 12px;
}

/* ── KPI 行 ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.kpi-card {
  background: var(--card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.kpi-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.kpi-icon {
  width: 22px;
  height: 22px;
  color: var(--primary-dark);
  flex: 0 0 auto;
}

.kpi-window,
.kpi-unit {
  font-size: 0.72rem;
  color: var(--muted);
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 0 8px;
  line-height: 1.5;
}

.kpi-num {
  font-size: 1.9rem;
  font-weight: 700;
  line-height: 1.15;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.kpi-title {
  font-size: 0.83rem;
  color: var(--muted);
}

.kpi-delta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.76rem;
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-delta span {
  font-weight: 700;
}

.kpi-delta.up {
  color: var(--ok-text);
}

.kpi-delta.down {
  color: var(--danger);
}

.kpi-delta.flat {
  color: var(--muted);
}

/* ── 图表行 ── */
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.chart-card {
  background: var(--card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chart-title {
  margin: 0 0 12px;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text);
}

.chart-empty {
  flex: 1;
  min-height: 148px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--muted);
}

.chart-empty-icon {
  font-size: 1.8rem;
  line-height: 1;
  opacity: 0.35;
}

.chart-empty-svg {
  width: 28px;
  height: 28px;
  opacity: 0.35;
}

.chart-empty-text {
  font-size: 0.85rem;
}

/* 环形图 */
.donut-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  justify-content: center;
  flex: 1;
  min-height: 148px;
}

.donut {
  width: 148px;
  height: 148px;
  flex: none;
}

.donut-track {
  fill: none;
  stroke: var(--surface);
  stroke-width: 14;
}

.donut-seg {
  fill: none;
  stroke-width: 14;
  stroke-linecap: butt;
  transition: stroke-dasharray 0.3s;
}

.donut-center-num {
  font-size: 1.35rem;
  font-weight: 700;
  fill: var(--text);
}

.donut-center-label {
  font-size: 0.72rem;
  fill: var(--muted);
}

.donut-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-width: 128px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: none;
}

.legend-label {
  color: var(--text);
  flex: 1;
}

.legend-val {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

/* 词云 */
.cloud {
  flex: 1;
  min-height: 148px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  padding: 8px;
  align-content: center;
}

.cloud-tag {
  line-height: 1.3;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  transition: transform 0.15s;
}

.cloud-tag:hover {
  transform: scale(1.06);
}

/* 趋势线 */
.line-wrap {
  flex: 1;
  min-height: 148px;
}

.line-svg {
  width: 100%;
  height: 100%;
  min-height: 148px;
  display: block;
}

.grid-lines line {
  stroke: var(--border-subtle);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.y-label {
  font-size: 0.68rem;
  fill: var(--muted);
}

.trend-area {
  fill: url(#trendFill);
}

.trend-line {
  fill: none;
  stroke: var(--primary);
  stroke-width: 2.2;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.trend-dot {
  fill: var(--primary);
  stroke: var(--card);
  stroke-width: 1;
}

.x-label {
  font-size: 0.66rem;
  fill: var(--muted);
}

/* 条形 */
.bars {
  flex: 1;
  min-height: 148px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 6px;
  padding-top: 8px;
}

.bar-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  height: 100%;
}

.bar-track {
  width: 60%;
  max-width: 28px;
  flex: 1;
  min-height: 96px;
  display: flex;
  align-items: flex-end;
  background: var(--surface);
  border-radius: 6px 6px 3px 3px;
  overflow: hidden;
}

.bar-fill {
  width: 100%;
  background: linear-gradient(180deg, var(--primary) 0%, color-mix(in srgb, var(--primary) 55%, transparent) 100%);
  border-radius: 6px 6px 3px 3px;
  min-height: 2px;
  transition: height 0.25s;
}

.bar-val {
  font-size: 0.72rem;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.bar-date {
  font-size: 0.66rem;
  color: var(--muted);
  white-space: nowrap;
}

/* ── 待办行 ── */
.todos-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.todo-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  cursor: pointer;
  text-align: left;
  color: var(--text);
  transition: border-color 0.15s, transform 0.15s;
}

.todo-card:hover {
  border-color: var(--primary);
  transform: translateY(-1px);
}

.todo-icon {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  font-size: 1rem;
  font-weight: 700;
  color: var(--primary-dark);
  border: 1.5px solid var(--primary-hover-border);
  border-radius: 6px;
}

.todo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.todo-title {
  font-weight: 600;
  font-size: 0.92rem;
}

.todo-desc {
  font-size: 0.76rem;
  color: var(--muted);
}

.todo-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  min-width: 26px;
  height: 26px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--danger);
  color: #fff;
  font-size: 0.78rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  box-shadow: var(--shadow);
}

.todo-badge.zero {
  background: var(--muted);
}

/* ── 响应式 ── */
@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .chart-grid,
  .todos-grid {
    grid-template-columns: 1fr;
  }

  .donut-wrap {
    flex-direction: column;
  }

  .donut-legend {
    width: 100%;
    flex-direction: row;
    justify-content: center;
    flex-wrap: wrap;
  }
}
</style>
