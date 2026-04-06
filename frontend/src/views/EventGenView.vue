<template>
  <div class="event-view">
    <div class="left-panel">
      <h3>이벤트 생성</h3>
      <div class="rating-row">
        <label v-for="r in ratings" :key="r.key" class="chk">
          <input type="checkbox" v-model="r.checked" /> {{ r.label }}
        </label>
      </div>
      <label class="s-label">프롬프트 (유사 검색)</label>
      <textarea class="prompt-input" v-model="prompt" placeholder="검색할 프롬프트 입력..." rows="3" />
      <div class="opt-row">
        <label class="s-label">최소 스텝</label>
        <input type="number" v-model.number="minSteps" min="1" max="50" class="num-input" />
        <label class="s-label">최대 스텝</label>
        <input type="number" v-model.number="maxSteps" min="1" max="50" class="num-input" />
      </div>
      <button class="btn-search" @click="searchEvents" :disabled="searching">
        {{ searching ? '검색 중...' : '이벤트 검색' }}
      </button>
      <div class="result-list" v-if="events.length">
        <div v-for="(ev, i) in events" :key="i" class="event-item"
          :class="{ selected: selectedIdx === i }"
          @click="selectEvent(i)"
        >
          <span class="ev-idx">#{{ i + 1 }}</span>
          <span class="ev-desc">{{ ev.summary || ev.copyright || '이벤트' }}</span>
          <span class="ev-count">{{ ev.step_count }}스텝</span>
        </div>
      </div>
      <div class="status">{{ statusText }}</div>
    </div>
    <div class="right-panel">
      <div v-if="steps.length === 0" class="empty">이벤트를 선택하면 스텝이 표시됩니다</div>
      <div v-else class="steps-scroll">
        <div v-for="(step, i) in steps" :key="i" class="step-card">
          <div class="step-header">Step {{ i + 1 }}</div>
          <div class="step-tags">
            <span v-for="t in step.added" :key="'a'+t" class="tag added">+{{ t }}</span>
            <span v-for="t in step.removed" :key="'r'+t" class="tag removed">-{{ t }}</span>
          </div>
          <div class="step-prompt">{{ step.prompt }}</div>
        </div>
      </div>
      <div class="bottom-actions" v-if="steps.length">
        <button class="btn-gen" @click="addToQueue">대기열 추가</button>
        <button class="btn-gen primary" @click="generateNow">즉시 생성</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const ratings = reactive([
  { key: 'g', label: 'G', checked: true },
  { key: 's', label: 'S', checked: false },
  { key: 'q', label: 'Q', checked: false },
  { key: 'e', label: 'E', checked: false },
])
const prompt = ref('')
const minSteps = ref(3)
const maxSteps = ref(10)
const events = ref([])
const steps = ref([])
const selectedIdx = ref(-1)
const searching = ref(false)
const statusText = ref('')

function searchEvents() {
  searching.value = true
  statusText.value = '검색 중...'
  requestAction('search_events', {
    ratings: ratings.filter(r => r.checked).map(r => r.key),
    prompt: prompt.value,
    min_steps: minSteps.value,
    max_steps: maxSteps.value,
  })
  // Python에서 결과를 bridge로 전달 (TODO: 시그널 연결)
  setTimeout(() => {
    searching.value = false
    statusText.value = 'Python에서 이벤트 검색을 실행합니다'
  }, 1000)
}

function selectEvent(i) {
  selectedIdx.value = i
  requestAction('select_event', { index: i })
}

function addToQueue() { requestAction('event_add_to_queue') }
function generateNow() { requestAction('event_generate_now') }
</script>

<style scoped>
.event-view { height: 100%; display: flex; }
.left-panel {
  width: 300px; padding: 16px; border-right: 1px solid #1A1A1A;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto;
}
.left-panel h3 { color: #E8E8E8; font-size: 14px; margin: 0; }
.rating-row { display: flex; gap: 8px; }
.chk { color: #B0B0B0; font-size: 12px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.chk input { accent-color: #E2B340; }
.s-label { color: #585858; font-size: 11px; font-weight: 600; }
.prompt-input {
  background: #131313; border: none; border-radius: 4px; padding: 8px;
  color: #E8E8E8; font-size: 12px; resize: vertical; outline: none; font-family: inherit;
}
.opt-row { display: flex; align-items: center; gap: 6px; }
.num-input {
  width: 50px; background: #131313; border: none; border-radius: 4px;
  padding: 4px 6px; color: #E8E8E8; font-size: 12px; text-align: center; outline: none;
}
.btn-search {
  padding: 10px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer;
}
.btn-search:disabled { opacity: 0.4; }
.result-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.event-item {
  padding: 8px; border: 1px solid #1A1A1A; border-radius: 4px; cursor: pointer;
  display: flex; align-items: center; gap: 8px; font-size: 12px;
}
.event-item.selected { border-color: #E2B340; }
.ev-idx { color: #E2B340; font-weight: 600; }
.ev-desc { color: #B0B0B0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-count { color: #585858; }
.status { color: #585858; font-size: 11px; text-align: center; }

.right-panel { flex: 1; display: flex; flex-direction: column; }
.empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #484848; }
.steps-scroll { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.step-card { padding: 10px; border: 1px solid #1A1A1A; border-radius: 6px; }
.step-header { color: #E2B340; font-size: 12px; font-weight: 700; margin-bottom: 4px; }
.step-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.tag { font-size: 10px; padding: 2px 6px; border-radius: 3px; }
.tag.added { background: #1a2e1a; color: #4CAF50; }
.tag.removed { background: #2e1a1a; color: #E05252; }
.step-prompt { font-size: 11px; color: #787878; line-height: 1.4; }
.bottom-actions { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #1A1A1A; }
.btn-gen {
  flex: 1; padding: 10px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-weight: 600; cursor: pointer;
}
.btn-gen.primary { background: #E2B340; color: #000; }
</style>
