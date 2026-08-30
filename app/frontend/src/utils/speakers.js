// 说话人调色板与标签/对齐等纯前端工具（与 App.vue 原逻辑一致）

// 每人一色调色板（按代号首现序分配；浅背景 + 同色系边框 + 深色文字）
export const SPEAKER_PALETTE = [
  { bg: '#eef4ff', border: '#b7d0fb', text: '#1e409e' }, // 蓝
  { bg: '#e8f7f0', border: '#a9e2c6', text: '#146c4b' }, // 绿
  { bg: '#fdf4e3', border: '#f2d49b', text: '#8f5a12' }, // 琥珀
  { bg: '#f1eefb', border: '#cfc2f2', text: '#5b3bb0' }, // 紫
  { bg: '#fcecf0', border: '#f4bdcb', text: '#9c2f4f' }, // 玫红
  { bg: '#e7f6fa', border: '#b2e2ee', text: '#0f6b79' }, // 青
]
// 暗色气泡同色系（深底 + 亮文字，保证对比度）
export const SPEAKER_PALETTE_DARK = [
  { bg: '#1d2a44', border: '#3a5a96', text: '#aecbff' },
  { bg: '#1c3126', border: '#3a6b52', text: '#a3e6c5' },
  { bg: '#392f1d', border: '#735d2e', text: '#f0d6a0' },
  { bg: '#2c2544', border: '#5b4a96', text: '#cdbbf5' },
  { bg: '#3d242c', border: '#7a3c4c', text: '#f2b9cb' },
  { bg: '#1c3036', border: '#3d6773', text: '#a3dce7' },
]

export function fallbackColor(isDark) {
  return isDark
    ? { bg: '#232832', border: '#3a4250', text: '#e6e9ef' }
    : { bg: '#f3f4f6', border: '#d1d5db', text: '#374151' }
}

// 按代号首现序建立「代号 → 调色板颜色」映射
export function speakerColorMap(segments, isDark) {
  const map = {}
  const palette = isDark ? SPEAKER_PALETTE_DARK : SPEAKER_PALETTE
  for (const seg of segments || []) {
    if (seg.speaker && !(seg.speaker in map)) {
      map[seg.speaker] = palette[Object.keys(map).length % palette.length]
    }
  }
  return map
}

export function colorOf(map, speaker, isDark) {
  return map[speaker] || fallbackColor(isDark)
}

export function styleOf(map, seg, isDark) {
  const color = colorOf(map, seg.speaker, isDark)
  return {
    backgroundColor: color.bg,
    borderColor: color.border,
    color: color.text,
  }
}

export function labelOf(seg) {
  if (seg.role_label) return seg.role_label
  return `说话人 ${seg.speaker || '?'}`
}

// role=T 靠左、role=P 靠右；未判定按代号奇偶交替左右（A=0 左、B=1 右…）。
function speakerIndex(speaker) {
  const code = String(speaker || '').toUpperCase()
  const idx = code.charCodeAt(0) - 65
  return idx >= 0 && idx <= 25 ? idx : 0
}

export function alignClassOf(seg) {
  if (seg.role === 'T') return 'align-left'
  if (seg.role === 'P') return 'align-right'
  return speakerIndex(seg.speaker) % 2 === 0 ? 'align-left' : 'align-right'
}
