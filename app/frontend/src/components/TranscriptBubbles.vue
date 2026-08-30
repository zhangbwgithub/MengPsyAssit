<script setup>
import { computed } from 'vue'
import { styleOf, labelOf, alignClassOf, speakerColorMap } from '../utils/speakers.js'
import { formatMs } from '../utils/format.js'

const props = defineProps({
  segments: { type: Array, default: () => [] },
  isDark: { type: Boolean, default: false },
  showTimestamps: { type: Boolean, default: true },
  compact: { type: Boolean, default: false },
})

// 气泡文本：cleaned_content 优先，无则 content
const bubbleSegments = computed(() =>
  (props.segments || []).map((seg) => ({
    ...seg,
    bubbleText: seg.cleaned_content ?? seg.content ?? '',
  }))
)

function colorMap() {
  return speakerColorMap(props.segments, props.isDark)
}
</script>

<template>
  <div class="segments">
    <div
      v-for="seg in bubbleSegments"
      :key="seg.seq"
      class="segment"
      :class="[alignClassOf(seg), { compact }]"
    >
      <div
        class="bubble"
        :class="{ compact }"
        :style="styleOf(colorMap(), seg, isDark)"
      >
        <div v-if="compact" class="compact-label">说话人 {{ seg.speaker || '?' }}</div>
        <div v-else class="bubble-header">
          <span class="speaker-label">{{ labelOf(seg) }}</span>
          <span v-if="showTimestamps" class="time">
            #{{ seg.seq }} · {{ formatMs(seg.start_ms) }}
          </span>
        </div>
        <p class="content">{{ seg.bubbleText }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
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

@media (max-width: 480px) {
  .bubble {
    max-width: 92%;
  }
}
</style>
