<template>
  <div class="eg-view">
    <!-- 좌측: 검색 설정 -->
    <aside class="eg-sidebar">
      <div class="eg-scroll">
        <div class="eg-header">
          <span class="eg-icon">🎬</span>
          <h3>EVENT GENERATOR</h3>
        </div>

        <div class="eg-card">
          <label>Rating</label>
          <div class="chip-row">
            <button v-for="r in ratings" :key="r.key" class="chip"
              :class="{ active: r.checked }" @click="r.checked = !r.checked">{{ r.label }}</button>
          </div>
        </div>

        <div class="eg-card">
          <label>Prompt (유사 검색)</label>
          <textarea v-model="prompt" rows="3" placeholder="검색할 프롬프트..."></textarea>
        </div>

        <div class="eg-card">
          <label>이벤트 길이</label>
          <div class="eg-row">
            <span class="eg-mini">Min</span>
            <input type="number" v-model.number="minSteps" min="1" max="50" />
            <span class="eg-mini">Max</span>
            <input type="number" v-model.number="maxSteps" min="1" max="100" />
          </div>
        </div>

        <div class="eg-card">
          <label>제외 태그</label>
          <input v-model="excludeTags" placeholder="쉼표 구분..." />
        </div>

        <div class="eg-card">
          <label>Options</label>
          <label><input type="checkbox" v-model="limitResults" /><span>상위 100개만</span></label>
          <label><input type="checkbox" v-model="fixSeed" /><span>시드 고정</span></label>
          <label><input type="checkbox" v-model="useT2ISettings" /><span>T2I 설정 사용</span></label>
        </div>
      </div>

      <div class="eg-footer">
        <button class="eg-go" @click="searchEvents" :disabled="searching">
          {{ searching ? 'SEARCHING...' : '🔍 RUN SEARCH' }}
        </button>
        <div class="eg-status">{{ statusText }}</div>
      </div>
    </aside>

    <!-- 중앙: 결과 목록 -->
    <div class="eg-list" v-if="events.length > 0">
      <div class="eg-list-header">RESULTS ({{ events.length }})</div>
      <div class="eg-list-scroll">
        <div v-for="(ev, i) in events" :key="i" class="eg-list-item"
          :class="{ active: selectedIdx === i }" @click="selectEvent(i)">
          <span class="eg-idx">#{{ i + 1 }}</span>
          <span class="eg-desc">{{ ev.character || ev.copyright || 'Event' }}</span>
          <span class="eg-cnt">{{ ev.children_count || '?' }}</span>
        </div>
      </div>
    </div>

    <!-- 우측: 스텝 상세 -->
    <section class="eg-main">
      <div v-if="steps.length === 0" class="eg-empty">
        <div class="eg-empty-icon">🎬</div>
        <h2>EVENT SEQUENCE</h2>
        <p>검색 후 이벤트를 선택하면 스텝이 표시됩니다</p>
      </div>
      <template v-else>
        <div class="eg-carry">
          <label><input type="checkbox" v-model="carryAppearance" /><span>외모 유지</span></label>
          <label><input type="checkbox" v-model="carryCostume" /><span>의상 유지</span></label>
          <label><input type="checkbox" v-model="carryBackground" /><span>배경 유지</span></label>
        </div>

        <div class="eg-steps">
          <div v-for="(step, i) in steps" :key="i" class="eg-step">
            <div class="step-head">
              <span class="step-no">Step {{ i + 1 }}</span>
              <span class="step-badge" :class="i === 0 ? 'parent' : 'child'">{{ i === 0 ? 'PARENT' : 'CHILD' }}</span>
            </div>
            <div class="step-diff" v-if="i > 0">
              <span v-for="t in (step.added || [])" :key="'a'+t" class="diff-tag add">+ {{ t }}</span>
              <span v-for="t in (step.removed || [])" :key="'r'+t" class="diff-tag rm">- {{ t }}</span>
            </div>
            <div class="step-prompt">{{ step.prompt || step.tags?.join(', ') || step.parent_tags || '' }}</div>
          </div>
        </div>

        <div class="eg-actions">
          <div class="eg-row">
            <span class="eg-mini">Repeat</span>
            <input type="number" v-model.number="repeatCount" min="1" max="100" />
          </div>
          <button class="eg-btn" @click="addToQueue">ADD TO QUEUE</button>
          <button class="eg-btn primary" @click="generateNow">GENERATE NOW</button>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const ratings = reactive([
  { key: 'g', label: 'GEN', checked: true },
  { key: 's', label: 'SENS', checked: false },
  { key: 'q', label: 'QUES', checked: false },
  { key: 'e', label: 'EXPL', checked: false },
])
const prompt = ref('')
const minSteps = ref(1)
const maxSteps = ref(50)
const excludeTags = ref('')
const limitResults = ref(true)
const fixSeed = ref(false)
const useT2ISettings = ref(true)
const repeatCount = ref(1)
const searching = ref(false)
const statusText = ref('READY')
const events = ref([])
const steps = ref([])
const selectedIdx = ref(-1)
const carryAppearance = ref(true)
const carryCostume = ref(true)
const carryBackground = ref(true)

function searchEvents() {
  searching.value = true; statusText.value = 'SEARCHING...'
  requestAction('search_events', {
    ratings: ratings.filter(r => r.checked).map(r => r.key),
    prompt: prompt.value,
    min_steps: minSteps.value,
    max_steps: maxSteps.value,
    exclude_tags: excludeTags.value,
    limit: limitResults.value,
  })
}

function selectEvent(i) {
  selectedIdx.value = i
  const ev = events.value[i]
  // 이벤트 데이터에서 스텝 생성
  if (ev.steps) { steps.value = ev.steps }
  else {
    steps.value = [{ prompt: ev.parent_tags || ev.general || '', type: 'parent' }]
    if (ev.children) ev.children.forEach(c => steps.value.push({ ...c, type: 'child' }))
  }
  requestAction('select_event', { index: i })
}

function addToQueue() {
  requestAction('event_add_to_queue', {
    repeat: repeatCount.value, fix_seed: fixSeed.value, use_t2i: useT2ISettings.value,
    carry: { appearance: carryAppearance.value, costume: carryCostume.value, background: carryBackground.value },
  })
}
function generateNow() {
  requestAction('event_generate_now', {
    repeat: repeatCount.value, fix_seed: fixSeed.value, use_t2i: useT2ISettings.value,
    carry: { appearance: carryAppearance.value, costume: carryCostume.value, background: carryBackground.value },
  })
}

import { onMounted } from 'vue'
import { onBackendEvent } from '../bridge.js'
onMounted(() => {
  onBackendEvent('eventSearchResults', (json) => {
    try {
      const data = JSON.parse(json)
      if (Array.isArray(data)) { events.value = data; statusText.value = `${data.length} EVENTS` }
      else if (data.error) { statusText.value = data.error }
    } catch {}
    searching.value = false
  })
})
</script>

<style scoped>
.eg-view { height: 100%; display: flex; background: var(--bg-primary); }

/* Sidebar */
.eg-sidebar { width: 300px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); }
.eg-scroll { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.eg-header { display: flex; align-items: center; gap: 8px; }
.eg-icon { font-size: 18px; }
.eg-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-secondary); }
.eg-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 10px; }
.chip-row { display: flex; gap: 3px; }
.chip { flex: 1; padding: 5px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; text-align: center; }
.chip.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.eg-card label { display: flex; align-items: center; gap: 4px; white-space: nowrap; font-size: 10px; color: var(--text-secondary); cursor: pointer; margin-bottom: 2px; }
.eg-card label input[type="checkbox"] { flex-shrink: 0; margin: 0; }
.eg-carry label { white-space: nowrap; font-size: 10px; }
.eg-row { display: flex; align-items: center; gap: 6px; }
.eg-mini { font-size: 9px; color: var(--text-muted); font-weight: 700; }
.eg-footer { padding: 12px; background: var(--bg-card); border-top: 1px solid var(--border); }
.eg-go { width: 100%; height: 40px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 11px; cursor: pointer; }
.eg-status { font-size: 9px; color: var(--text-muted); text-align: center; margin-top: 6px; }

/* Event List */
.eg-list { width: 220px; display: flex; flex-direction: column; border-right: 1px solid var(--border); }
.eg-list-header { padding: 10px 12px; font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; border-bottom: 1px solid var(--border); }
.eg-list-scroll { flex: 1; overflow-y: auto; }
.eg-list-item { display: flex; align-items: center; gap: 6px; padding: 8px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.02); font-size: 11px; }
.eg-list-item:hover { background: rgba(255,255,255,0.02); }
.eg-list-item.active { background: var(--accent-dim); border-left: 3px solid var(--accent); }
.eg-idx { color: var(--text-muted); font-family: monospace; font-size: 10px; min-width: 24px; }
.eg-desc { flex: 1; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eg-cnt { font-size: 9px; color: var(--accent); }

/* Main */
.eg-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.eg-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; opacity: 0.2; }
.eg-empty-icon { font-size: 48px; margin-bottom: 12px; }
.eg-empty h2 { letter-spacing: 4px; }
.eg-carry { display: flex; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.eg-steps { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.eg-step { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.step-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.step-no { font-size: 12px; font-weight: 800; color: var(--text-primary); }
.step-badge { padding: 2px 8px; border-radius: 4px; font-size: 8px; font-weight: 900; letter-spacing: 1px; }
.step-badge.parent { background: var(--accent-dim); color: var(--accent); }
.step-badge.child { background: rgba(96,165,250,0.1); color: #60a5fa; }
.step-diff { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.diff-tag { padding: 2px 8px; border-radius: 4px; font-size: 9px; }
.diff-tag.add { background: rgba(74,222,128,0.1); color: #4ade80; border: 1px solid rgba(74,222,128,0.2); }
.diff-tag.rm { background: rgba(248,113,113,0.1); color: #f87171; border: 1px solid rgba(248,113,113,0.2); text-decoration: line-through; }
.step-prompt { font-size: 11px; color: var(--text-secondary); line-height: 1.5; max-height: 60px; overflow-y: auto; }
.eg-actions { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border); flex-shrink: 0; }
.eg-btn { padding: 8px 16px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); font-size: 11px; font-weight: 700; cursor: pointer; }
.eg-btn.primary { background: var(--accent); color: #000; border: none; }
</style>
