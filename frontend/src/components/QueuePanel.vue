<template>
  <div class="queue-panel" :class="{ expanded: isExpanded }">
    <div class="queue-header" @click="isExpanded = !isExpanded">
      <span class="title">
        QUEUE
        <span class="count-badge" v-if="items.length">{{ items.length }}</span>
        <span class="running-badge" v-if="isRunning && !isPaused">▶ RUNNING</span>
        <span class="paused-badge" v-if="isPaused">⏸ PAUSED</span>
        <span class="selected-badge" v-if="selectedIds.size > 0">{{ selectedIds.size }} 선택됨</span>
      </span>
      <div class="queue-actions" @click.stop>
        <button class="btn" @click="startQueue" v-if="items.length && !isRunning">▶ 시작</button>
        <button class="btn" @click="pauseQueue" v-if="isRunning && !isPaused" title="일시정지">⏸ 일시정지</button>
        <button class="btn primary" @click="resumeQueue" v-if="isPaused" title="재개">▶ 재개</button>
        <button class="btn danger" @click="stopQueue" v-if="isRunning">⏹ 중지</button>
        <button class="btn danger" @click="removeSelected" v-if="selectedIds.size > 0" title="선택한 항목 삭제">
          🗑 선택삭제 ({{ selectedIds.size }})
        </button>
        <button class="btn" @click="clearAll" v-if="items.length && !isRunning && selectedIds.size === 0">🗑 전체</button>
        <span class="expand-icon">{{ isExpanded ? '▼' : '▲' }}</span>
      </div>
    </div>
    <div class="queue-strip" v-if="isExpanded && items.length">
      <template v-for="(item, i) in items" :key="item.id || i">
        <button class="q-chip"
          :class="{ active: i === currentIdx && isRunning, done: item._done }"
          :title="(item.prompt || 'No prompt').toString().substring(0, 160) + '\n(클릭하여 편집)'"
          @click="openEdit(item, i)">
          <span class="q-chip-st" v-if="i === currentIdx && isRunning && !isPaused">⏳</span>
          <span class="q-chip-st" v-else-if="i === currentIdx && isPaused">⏸</span>
          <span class="q-chip-st" v-else-if="item._done">✅</span>
          <span class="q-chip-num">큐{{ i + 1 }}</span>
          <span class="q-chip-prev">{{ (item.prompt || '—').toString().slice(0, 16) }}</span>
        </button>
        <span class="q-arrow" v-if="i < items.length - 1">→</span>
      </template>
    </div>

    <!-- 큐 항목 편집 모달 -->
    <div class="qe-overlay" v-if="editItem" @click.self="closeEdit">
      <div class="qe-modal">
        <div class="qe-head">
          <h3>큐{{ editIdx + 1 }} 편집</h3>
          <button class="qe-x" @click="closeEdit">✕</button>
        </div>
        <label class="qe-label">프롬프트</label>
        <textarea v-model="editPrompt" class="qe-text" rows="6" placeholder="프롬프트..."></textarea>
        <label class="qe-label">네거티브</label>
        <textarea v-model="editNeg" class="qe-text" rows="3" placeholder="네거티브..."></textarea>
        <div class="qe-foot">
          <button class="qe-btn" @click="moveEdit('up')" :disabled="editIdx <= 0">▲ 위로</button>
          <button class="qe-btn" @click="moveEdit('down')" :disabled="editIdx >= items.length - 1">▼ 아래로</button>
          <button class="qe-btn danger" @click="deleteEdit">🗑 삭제</button>
          <div class="qe-sp"></div>
          <button class="qe-btn" @click="closeEdit">취소</button>
          <button class="qe-btn primary" @click="saveEdit">💾 저장</button>
        </div>
      </div>
    </div>
    <div class="queue-progress" v-if="isRunning">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <span class="progress-text">
        {{ completedCount }} / {{ items.length }}
        <span v-if="etaText" class="eta">· ETA {{ etaText }}</span>
      </span>
    </div>
    <div class="queue-empty" v-if="isExpanded && !items.length">
      대기열이 비어있습니다
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const items = ref([])
const isExpanded = ref(false)
const isRunning = ref(false)
const isPaused = ref(false)
const currentIdx = ref(-1)
const completedCount = ref(0)
const selectedIds = ref(new Set())  // 다중 선택 (Shift+클릭으로 범위 선택)
const _lastClickedIdx = ref(-1)

// 큐 항목 편집 모달
const editItem = ref(null)
const editIdx = ref(-1)
const editPrompt = ref('')
const editNeg = ref('')
function openEdit(item, i) {
  editItem.value = item
  editIdx.value = i
  editPrompt.value = (item.prompt || '').toString()
  editNeg.value = (item.negative_prompt || '').toString()
}
function closeEdit() { editItem.value = null; editIdx.value = -1 }
function saveEdit() {
  if (editItem.value && editItem.value.id) {
    requestAction('update_queue_item', {
      item_id: editItem.value.id,
      prompt: editPrompt.value,
      negative_prompt: editNeg.value,
    })
  }
  closeEdit()
}
function deleteEdit() {
  if (editItem.value && editItem.value.id) {
    requestAction('remove_queue_items', { item_ids: [editItem.value.id] })
  }
  closeEdit()
}
function moveEdit(dir) {
  if (editItem.value && editItem.value.id) {
    requestAction('move_queue_item', { item_id: editItem.value.id, direction: dir })
  }
  closeEdit()
}

// ETA 추적: 처리된 항목당 평균 시간
const _startTime = ref(0)
const _completedAtStart = ref(0)

const progressPct = computed(() => {
  if (items.value.length === 0) return 0
  return Math.round(completedCount.value / items.value.length * 100)
})

const etaText = computed(() => {
  if (!isRunning.value || isPaused.value) return ''
  const done = completedCount.value - _completedAtStart.value
  const remaining = items.value.length - completedCount.value
  if (done < 1 || remaining <= 0 || _startTime.value === 0) return ''
  const elapsed = (Date.now() - _startTime.value) / 1000
  const avgPerItem = elapsed / done
  const sec = Math.round(avgPerItem * remaining)
  if (sec < 60) return `${sec}초`
  if (sec < 3600) return `${Math.floor(sec / 60)}분 ${sec % 60}초`
  return `${Math.floor(sec / 3600)}시 ${Math.floor((sec % 3600) / 60)}분`
})

function isItemRunning(i) {
  return i === currentIdx.value && isRunning.value
}
function canMoveUp(i) {
  if (isRunning.value && i <= 1) return false  // 0번은 처리 중
  return i > 0
}
function canMoveDown(i) {
  if (isRunning.value && i === 0) return false  // 처리 중인 항목은 못 내림
  return i < items.value.length - 1
}

function onItemClick(e, item, i) {
  if (!item.id) return  // id 없으면 선택 불가
  if (e.shiftKey && _lastClickedIdx.value >= 0) {
    // 범위 선택
    const [lo, hi] = [Math.min(_lastClickedIdx.value, i), Math.max(_lastClickedIdx.value, i)]
    const next = new Set(selectedIds.value)
    for (let k = lo; k <= hi; k++) {
      const it = items.value[k]
      if (it?.id) next.add(it.id)
    }
    selectedIds.value = next
  } else if (e.ctrlKey || e.metaKey) {
    // 개별 토글
    const next = new Set(selectedIds.value)
    if (next.has(item.id)) next.delete(item.id)
    else next.add(item.id)
    selectedIds.value = next
    _lastClickedIdx.value = i
  } else {
    // 일반 클릭은 선택 해제 (현재는 아무 동작 없음)
    if (selectedIds.value.size > 0) selectedIds.value = new Set()
    _lastClickedIdx.value = i
  }
}

function moveItem(item, direction) {
  if (!item.id) return
  requestAction('move_queue_item', { item_id: item.id, direction })
}

function removeItem(item, i) {
  if (item.id) {
    requestAction('remove_queue_items', { item_ids: [item.id] })
  } else {
    // fallback: id 없으면 로컬에서만 제거
    items.value.splice(i, 1)
  }
}

function removeSelected() {
  if (selectedIds.value.size === 0) return
  const ids = Array.from(selectedIds.value)
  requestAction('remove_queue_items', { item_ids: ids })
  selectedIds.value = new Set()
}

function clearAll() {
  if (!items.value.length) return
  if (!confirm(`대기열 ${items.value.length}개 항목을 모두 삭제할까요?`)) return
  requestAction('clear_queue')
  selectedIds.value = new Set()
}
function startQueue() {
  _startTime.value = Date.now()
  _completedAtStart.value = completedCount.value
  requestAction('start_queue')
}
function stopQueue() {
  requestAction('stop_queue')
  _startTime.value = 0
}
function pauseQueue() { requestAction('pause_queue') }
function resumeQueue() { requestAction('resume_queue') }

// 이벤트 disconnect 핸들 — onUnmounted에서 정리 (메모리 누수 방지)
const _unsubs = []

// 자동화 자동 재시작 옵션 — Settings에서 토글, 여기선 읽기만
// 기본값 ON — 사용자가 명시적으로 'false' 저장한 경우만 OFF
// 기본 OFF — 큐를 열어 보기만 해도 이전 세션 큐가 자동 재시작되던 문제 방지.
// 자동 재시작을 원하면 설정에서 켜면 됨(localStorage 'queue.autoResumeOnStart'='true').
const autoResumeOnStart = ref(localStorage.getItem('queue.autoResumeOnStart') === 'true')
// Settings에서 변경 시 즉시 반영 (storage 이벤트는 다른 탭, 같은 탭은 작동 안 해서 unused지만 안전망)
function _onStorageEvent(e) {
  if (e.key === 'queue.autoResumeOnStart') {
    autoResumeOnStart.value = e.newValue !== 'false'
  }
}
let _autoResumeTried = false  // 1회만 시도 (재실행 방지)

onMounted(() => {
  // Python → Vue: 대기열 상태 실시간 동기화
  _unsubs.push(onBackendEvent('queueUpdated', (json) => {
    try {
      const data = JSON.parse(json)
      if (Array.isArray(data.items)) {
        items.value = data.items
        // 삭제된 항목의 선택 정리
        if (selectedIds.value.size > 0) {
          const validIds = new Set(data.items.map(it => it.id).filter(Boolean))
          const next = new Set()
          for (const id of selectedIds.value) if (validIds.has(id)) next.add(id)
          if (next.size !== selectedIds.value.size) selectedIds.value = next
        }
      }
      if (typeof data.running === 'boolean') isRunning.value = data.running
      if (typeof data.paused === 'boolean') isPaused.value = data.paused
      if (typeof data.current_index === 'number') currentIdx.value = data.current_index
      if (typeof data.completed === 'number') completedCount.value = data.completed
      // 자동 확장
      if (data.items?.length > 0) isExpanded.value = true
      // 시작 시 복구된 큐가 있으면 사용자 옵션에 따라 자동 재시작
      if (!_autoResumeTried && autoResumeOnStart.value
          && items.value.length > 0 && !isRunning.value) {
        _autoResumeTried = true
        // 살짝 늦춰서 — backend도 준비될 시간 + 사용자가 토스트 보고 인지 가능
        setTimeout(() => {
          if (items.value.length > 0 && !isRunning.value) {
            requestAction('show_toast', { type: 'info',
              msg: `이전 세션의 대기열 ${items.value.length}개 자동 재시작 중...` })
            startQueue()
          }
        }, 1500)
      }
    } catch {}
  }))

  // 아이템 추가 이벤트 — queueUpdated가 전체 상태를 보내므로 여기선 중복 방지하며 보강
  _unsubs.push(onBackendEvent('queueItemAdded', (json) => {
    try {
      const item = JSON.parse(json)
      // id 기준 중복 체크 — queueUpdated가 이미 반영했다면 push 안 함
      if (item.id && items.value.some(it => it.id === item.id)) {
        isExpanded.value = true
        return
      }
      items.value.push(item)
      isExpanded.value = true
    } catch {}
  }))

  // 완료 이벤트
  _unsubs.push(onBackendEvent('queueCompleted', (json) => {
    isRunning.value = false
    isPaused.value = false
    try {
      const data = JSON.parse(json)
      completedCount.value = data.total || items.value.length
    } catch {}
    _startTime.value = 0
  }))
})

// Settings에서 autoResumeOnStart 변경 시 즉시 반영 (다른 창/탭 — 같은 창은 거의 불필요)
function _onEditKey(e) { if (e.key === 'Escape' && editItem.value) { e.stopPropagation(); closeEdit() } }
onMounted(() => {
  window.addEventListener('storage', _onStorageEvent)
  window.addEventListener('keydown', _onEditKey, true)
})
onUnmounted(() => {
  for (const off of _unsubs) { try { off() } catch {} }
  _unsubs.length = 0
  window.removeEventListener('storage', _onStorageEvent)
  window.removeEventListener('keydown', _onEditKey, true)
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
.paused-badge { background: #fbbf24; color: #000; padding: 1px 6px; border-radius: 8px; font-size: 9px; font-weight: 900; }
.selected-badge { background: #60a5fa; color: #000; padding: 1px 6px; border-radius: 8px; font-size: 9px; font-weight: 900; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.queue-actions { display: flex; align-items: center; gap: 6px; }
.expand-icon { color: var(--text-muted); font-size: 10px; }
.btn { padding: 3px 10px; background: #181818; border: none; border-radius: 4px; color: #585858; font-size: 10px; cursor: pointer; font-weight: 600; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn.danger { color: #f87171; }
.btn.primary { background: var(--accent); color: #000; }
.btn.primary:hover { background: #fff176; }

/* (auto-resume 토글은 Settings로 이전됨) */

/* 가로 칩 스트립 — 큐1 → 큐2 → 큐3 */
.queue-strip { display: flex; align-items: center; gap: 4px; overflow-x: auto; overflow-y: hidden; padding: 6px 12px; }
.q-chip {
  flex-shrink: 0; width: 86px; height: 50px; display: flex; flex-direction: column;
  align-items: flex-start; justify-content: center; gap: 1px; padding: 5px 8px;
  background: #161616; border: 1px solid var(--border); border-radius: 8px;
  cursor: pointer; transition: 0.15s; position: relative; text-align: left;
}
.q-chip:hover { background: #1f1f1f; border-color: var(--accent); }
.q-chip.active { border-color: var(--accent); background: rgba(226,179,64,0.1); box-shadow: 0 0 0 1px var(--accent) inset; }
.q-chip.done { opacity: 0.45; }
.q-chip-st { position: absolute; top: 3px; right: 5px; font-size: 11px; }
.q-chip-num { color: var(--accent); font-weight: 800; font-size: 11px; }
.q-chip-prev { color: var(--text-muted); font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; }
.q-arrow { flex-shrink: 0; color: #444; font-size: 12px; user-select: none; }

/* 큐 항목 편집 모달 */
.qe-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 3000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(3px); }
.qe-modal { width: min(620px, 92vw); max-height: 86vh; overflow-y: auto; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.qe-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.qe-head h3 { font-size: 16px; font-weight: 800; color: var(--text-primary); }
.qe-x { background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); width: 28px; height: 28px; cursor: pointer; }
.qe-label { display: block; font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 1px; margin: 8px 0 4px; }
.qe-text { width: 100%; background: var(--bg-input); border: 1px solid var(--border); border-radius: 7px; padding: 9px 11px; color: var(--text-primary); font-size: 12px; line-height: 1.5; resize: vertical; }
.qe-text:focus { outline: none; border-color: var(--accent); }
.qe-foot { display: flex; align-items: center; gap: 6px; margin-top: 14px; }
.qe-sp { flex: 1; }
.qe-btn { background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 11px; font-weight: 700; padding: 7px 12px; cursor: pointer; }
.qe-btn:hover:not(:disabled) { color: var(--text-primary); border-color: var(--accent); }
.qe-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.qe-btn.danger { color: #f87171; }
.qe-btn.primary { background: var(--accent); color: #000; border-color: var(--accent); }

.queue-progress { padding: 4px 16px 8px; }
.progress-bar { width: 100%; height: 3px; background: var(--bg-input); border-radius: 2px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.3s; }
.progress-text { font-size: 9px; color: var(--text-muted); text-align: right; margin-top: 2px; display: block; }
.progress-text .eta { color: var(--accent); font-weight: 700; margin-left: 4px; }

.queue-empty { padding: 12px; text-align: center; color: #383838; font-size: 11px; }
</style>
