<template>
  <div class="queue-panel" :class="{ expanded: isExpanded }">
    <div class="queue-header" @click="isExpanded = !isExpanded">
      <span class="title">
        QUEUE
        <span class="count-badge" v-if="items.length">{{ items.length }}</span>
        <span class="running-badge" v-if="isRunning">▶ RUNNING</span>
      </span>
      <div class="queue-actions" @click.stop>
        <button class="btn" @click="startQueue" v-if="items.length && !isRunning">▶ 시작</button>
        <button class="btn danger" @click="stopQueue" v-if="isRunning">⏹ 중지</button>
        <button class="btn" @click="clearAll" v-if="items.length && !isRunning">🗑 전체 삭제</button>
        <span class="expand-icon">{{ isExpanded ? '▼' : '▲' }}</span>
      </div>
    </div>
    <div class="queue-list" v-if="isExpanded && items.length">
      <div v-for="(item, i) in items" :key="i" class="queue-item"
        :class="{ active: i === currentIdx, done: item._done }">
        <span class="q-idx">#{{ i + 1 }}</span>
        <span class="q-status" v-if="i === currentIdx && isRunning">⏳</span>
        <span class="q-status" v-else-if="item._done">✅</span>
        <span class="q-text">{{ item.prompt?.substring(0, 80) || 'No prompt' }}</span>
        <button class="q-rm" @click="removeItem(i)" v-if="!isRunning">×</button>
      </div>
    </div>
    <div class="queue-progress" v-if="isRunning">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <span class="progress-text">{{ completedCount }} / {{ items.length }}</span>
    </div>
    <div class="queue-empty" v-if="isExpanded && !items.length">
      대기열이 비어있습니다
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const items = ref([])
const isExpanded = ref(false)
const isRunning = ref(false)
const currentIdx = ref(-1)
const completedCount = ref(0)

const progressPct = computed(() => {
  if (items.value.length === 0) return 0
  return Math.round(completedCount.value / items.value.length * 100)
})

function clearAll() { items.value = []; completedCount.value = 0; currentIdx.value = -1 }
function removeItem(i) { items.value.splice(i, 1) }
function startQueue() { requestAction('start_queue') }
function stopQueue() { requestAction('stop_queue') }

onMounted(() => {
  // Python → Vue: 대기열 상태 실시간 동기화
  onBackendEvent('queueUpdated', (json) => {
    try {
      const data = JSON.parse(json)
      if (data.items) items.value = data.items
      if (typeof data.running === 'boolean') isRunning.value = data.running
      if (typeof data.current_index === 'number') currentIdx.value = data.current_index
      if (typeof data.completed === 'number') completedCount.value = data.completed
      // 자동 확장
      if (data.items?.length > 0) isExpanded.value = true
    } catch {}
  })

  // 아이템 추가 이벤트
  onBackendEvent('queueItemAdded', (json) => {
    try {
      const item = JSON.parse(json)
      items.value.push(item)
      isExpanded.value = true
    } catch {}
  })

  // 완료 이벤트
  onBackendEvent('queueCompleted', (json) => {
    isRunning.value = false
    try {
      const data = JSON.parse(json)
      completedCount.value = data.total || items.value.length
    } catch {}
  })
})

defineExpose({ items })
</script>

<style scoped>
.queue-panel {
  background: #0A0A0A; min-height: 36px; max-height: 240px;
  display: flex; flex-direction: column; flex-shrink: 0;
  border-top: 1px solid var(--border);
}
.queue-panel.expanded { min-height: 80px; }
.queue-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 16px; cursor: pointer; user-select: none;
}
.title { color: var(--text-muted); font-size: 11px; font-weight: 800; letter-spacing: 1px; display: flex; align-items: center; gap: 8px; }
.count-badge { background: var(--accent); color: #000; padding: 1px 6px; border-radius: 8px; font-size: 9px; font-weight: 900; }
.running-badge { background: #4ade80; color: #000; padding: 1px 6px; border-radius: 8px; font-size: 9px; font-weight: 900; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.queue-actions { display: flex; align-items: center; gap: 6px; }
.expand-icon { color: var(--text-muted); font-size: 10px; }
.btn { padding: 3px 10px; background: #181818; border: none; border-radius: 4px; color: #585858; font-size: 10px; cursor: pointer; font-weight: 600; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn.danger { color: #f87171; }

.queue-list { flex: 1; overflow-y: auto; padding: 2px 8px; }
.queue-item {
  display: flex; align-items: center; gap: 6px; padding: 5px 8px;
  font-size: 11px; border-radius: 4px; margin-bottom: 2px; transition: 0.15s;
}
.queue-item.active { background: rgba(226, 179, 64, 0.05); border-left: 2px solid var(--accent); }
.queue-item.done { opacity: 0.4; }
.q-idx { color: var(--accent); font-weight: 700; font-size: 10px; min-width: 24px; }
.q-status { font-size: 12px; }
.q-text { color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.q-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 14px; padding: 0 4px; }

.queue-progress { padding: 4px 16px 8px; }
.progress-bar { width: 100%; height: 3px; background: var(--bg-input); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.3s; }
.progress-text { font-size: 9px; color: var(--text-muted); text-align: right; margin-top: 2px; display: block; }

.queue-empty { padding: 12px; text-align: center; color: #383838; font-size: 11px; }
</style>
