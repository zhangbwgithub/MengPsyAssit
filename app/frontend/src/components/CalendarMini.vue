<script setup>
import { ref, computed } from 'vue'
import { localDateKey, todayKey, formatAsDateKey } from '../utils/format.js'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' }, // YYYY-MM-DD 选中日期
})

const emit = defineEmits(['update:modelValue', 'select'])

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']
const today = todayKey()
const viewYear = ref(+today.slice(0, 4))
const viewMonth = ref(+today.slice(5, 7)) // 1-12

// 每一天的记录条数（按全部记录，不受标签/组筛选影响）
const countsByDay = computed(() => {
  const map = {}
  for (const s of props.sessions || []) {
    const key = localDateKey(s.started_at)
    if (key) map[key] = (map[key] || 0) + 1
  }
  return map
})

// 周一首列：本月 1 号所在周的周一为起点，共 42 格（6 周）
const grid = computed(() => {
  const year = viewYear.value
  const month = viewMonth.value
  const first = new Date(year, month - 1, 1)
  const startOffset = (first.getDay() + 6) % 7 // 周一起始偏移
  const cells = []
  const start = new Date(year, month - 1, 1 - startOffset)
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = formatAsDateKey(d)
    cells.push({
      key,
      day: d.getDate(),
      inMonth: d.getMonth() === month - 1 && d.getFullYear() === year,
      isToday: key === today,
      count: countsByDay.value[key] || 0,
    })
  }
  return cells
})

const title = computed(() => `${viewYear.value} 年 ${viewMonth.value} 月`)

function changeMonth(delta) {
  const d = new Date(viewYear.value, viewMonth.value - 1 + delta, 1)
  viewYear.value = d.getFullYear()
  viewMonth.value = d.getMonth() + 1
}

function goToday() {
  const d = new Date()
  viewYear.value = d.getFullYear()
  viewMonth.value = d.getMonth() + 1
  pick(today)
}

function pick(key) {
  emit('update:modelValue', key)
  emit('select', key)
}
</script>

<template>
  <div class="cal">
    <div class="cal-head">
      <button class="cal-nav" type="button" aria-label="上一月" @click="changeMonth(-1)">‹</button>
      <span class="cal-title">{{ title }}</span>
      <button class="cal-nav" type="button" aria-label="下一月" @click="changeMonth(1)">›</button>
      <button class="cal-today" type="button" @click="goToday">今天</button>
    </div>
    <div class="cal-grid">
      <div v-for="w in WEEKDAYS" :key="w" class="cal-weekday">{{ w }}</div>
      <button
        v-for="cell in grid"
        :key="cell.key"
        type="button"
        class="cal-cell"
        :class="{
          outside: !cell.inMonth,
          today: cell.isToday,
          selected: cell.key === modelValue,
          hasdata: cell.count > 0,
        }"
        :title="cell.count ? `${cell.key} · ${cell.count} 条` : cell.key"
        @click="pick(cell.key)"
      >
        <span class="cal-day">{{ cell.day }}</span>
        <span v-if="cell.count > 0" class="cal-dot-num" :class="{ many: cell.count > 9 }">
          <i class="cal-dot"></i>{{ cell.count > 99 ? '99+' : cell.count }}
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.cal {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--card-inset);
  padding: 8px;
}

.cal-head {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.cal-title {
  flex: 1;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text);
  text-align: center;
}

.cal-nav {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  width: 24px;
  height: 24px;
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
}

.cal-today {
  background: var(--surface);
  color: var(--primary-dark);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-size: 0.72rem;
  padding: 3px 6px;
  cursor: pointer;
}

.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.cal-weekday {
  text-align: center;
  font-size: 0.68rem;
  color: var(--muted);
  padding: 2px 0;
}

.cal-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  min-height: 30px;
  padding: 2px 0;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 0.72rem;
  cursor: pointer;
}

.cal-cell:hover {
  background: var(--hover);
  border-color: var(--primary-hover-border);
}

.cal-cell.outside .cal-day {
  color: var(--muted);
  opacity: 0.5;
}

.cal-cell.today .cal-day {
  color: var(--primary);
  font-weight: 700;
}

.cal-cell.selected {
  background: var(--primary-soft);
  border-color: var(--primary);
}

.cal-dot-num {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 14px;
  text-align: center;
  background: var(--primary);
  color: var(--on-primary);
  border-radius: 999px;
  font-size: 0.62rem;
  line-height: 14px;
  padding: 0 3px;
}

.cal-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--on-primary);
  font-style: normal;
}

.cal-dot-num.many {
  background: var(--primary-dark);
}
</style>
