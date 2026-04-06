<template>
  <div class="event-view">
    <!-- 좌측: 설정 + 이벤트 목록 -->
    <div class="sidebar">
      <h3>이벤트 시퀀스 생성</h3>

      <div class="section">
        <label class="sec-label">Rating</label>
        <div class="rating-row">
          <label v-for="r in ratings" :key="r.key" class="chk">
            <input type="checkbox" v-model="r.checked" /> {{ r.label }}
          </label>
        </div>
      </div>

      <div class="section">
        <label class="sec-label">프롬프트 (유사 검색)</label>
        <textarea class="input-area" v-model="prompt" placeholder="검색할 프롬프트 입력..." rows="3" />
      </div>

      <div class="section">
        <label class="sec-label">이벤트 길이</label>
        <div class="row">
          <label class="mini-label">최소</label>
          <input type="number" class="num-input" v-model.number="minSteps" min="1" max="50" />
          <label class="mini-label">최대</label>
          <input type="number" class="num-input" v-model.number="maxSteps" min="1" max="50" />
        </div>
      </div>

      <div class="section">
        <label class="sec-label">제외 태그</label>
        <input class="finput" v-model="excludeTags" placeholder="제외할 태그 (쉼표 구분)" />
      </div>

      <div class="section">
        <label class="sec-label">옵션</label>
        <label class="chk"><input type="checkbox" v-model="limitResults" /> 상위 100개만</label>
        <label class="chk"><input type="checkbox" v-model="fixSeed" /> 시드 고정</label>
        <label class="chk"><input type="checkbox" v-model="useT2ISettings" /> T2I 설정 사용</label>
      </div>

      <button class="btn-search" @click="searchEvents" :disabled="searching">
        {{ searching ? '검색 중...' : '🔍 이벤트 검색' }}
      </button>

      <div class="status">{{ statusText }}</div>

      <!-- 이벤트 목록 -->
      <div class="event-list" v-if="events.length">
        <label class="sec-label">검색 결과 ({{ events.length }})</label>
        <div v-for="(ev, i) in events" :key="i" class="event-item"
          :class="{ selected: selectedIdx === i }" @click="selectEvent(i)"
        >
          <span class="ev-idx">#{{ i + 1 }}</span>
          <span class="ev-desc">{{ ev.summary || ev.copyright || '이벤트' }}</span>
          <span class="ev-count">{{ ev.step_count || '?' }}스텝</span>
        </div>
      </div>
    </div>

    <!-- 우측: 스텝 카드 + 프롬프트 미리보기 -->
    <div class="main-area">
      <div v-if="steps.length === 0" class="empty">
        <div class="empty-icon">🎬</div>
        <div>이벤트를 검색하고 선택하면<br/>스텝이 여기에 표시됩니다</div>
      </div>
      <template v-else>
        <!-- 캐리 옵션 -->
        <div class="carry-bar">
          <label class="sec-label">캐리 옵션</label>
          <label class="chk"><input type="checkbox" v-model="carryAppearance" /> 외모 유지</label>
          <label class="chk"><input type="checkbox" v-model="carryCostume" /> 의상 유지</label>
          <label class="chk"><input type="checkbox" v-model="carryBackground" /> 배경 유지</label>
        </div>

        <!-- 스텝 카드들 -->
        <div class="steps-scroll">
          <div v-for="(step, i) in steps" :key="i" class="step-card">
            <div class="step-header">
              <span class="step-num">Step {{ i + 1 }}</span>
              <span class="step-type" v-if="i === 0">Parent</span>
              <span class="step-type child" v-else>Child</span>
            </div>
            <div class="step-tags" v-if="i > 0">
              <span v-for="t in (step.added || [])" :key="'a'+t" class="tag added">+ {{ t }}</span>
              <span v-for="t in (step.removed || [])" :key="'r'+t" class="tag removed">- {{ t }}</span>
            </div>
            <div class="step-prompt-preview">{{ step.prompt || step.tags?.join(', ') || '' }}</div>
          </div>
        </div>

        <!-- 하단 액션 -->
        <div class="bottom-actions">
          <div class="row">
            <label class="mini-label">반복</label>
            <input type="number" class="num-input" v-model.number="repeatCount" min="1" max="100" />
          </div>
          <div class="btn-group">
            <button class="btn-action" @click="addToQueue">대기열 추가</button>
            <button class="btn-action primary" @click="generateNow">즉시 생성</button>
          </div>
        </div>
      </template>
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
const excludeTags = ref('')
const limitResults = ref(true)
const fixSeed = ref(false)
const useT2ISettings = ref(true)
const carryAppearance = ref(true)
const carryCostume = ref(false)
const carryBackground = ref(false)
const repeatCount = ref(1)

const events = ref([])
const steps = ref([])
const selectedIdx = ref(-1)
const searching = ref(false)
const statusText = ref('준비 완료')

function searchEvents() {
  searching.value = true
  statusText.value = '검색 중...'
  requestAction('search_events', {
    ratings: ratings.filter(r => r.checked).map(r => r.key),
    prompt: prompt.value,
    min_steps: minSteps.value,
    max_steps: maxSteps.value,
    exclude_tags: excludeTags.value,
    limit: limitResults.value,
  })
  // TODO: Python에서 결과를 bridge 시그널로 전달
  setTimeout(() => { searching.value = false; statusText.value = 'Python에서 이벤트를 검색합니다' }, 500)
}

function selectEvent(i) {
  selectedIdx.value = i
  requestAction('select_event', { index: i })
  // TODO: Python에서 steps 데이터를 bridge로 전달
}

function addToQueue() {
  requestAction('event_add_to_queue', {
    repeat: repeatCount.value,
    fix_seed: fixSeed.value,
    use_t2i: useT2ISettings.value,
    carry: { appearance: carryAppearance.value, costume: carryCostume.value, background: carryBackground.value },
  })
}

function generateNow() {
  requestAction('event_generate_now', {
    repeat: repeatCount.value,
    fix_seed: fixSeed.value,
    use_t2i: useT2ISettings.value,
    carry: { appearance: carryAppearance.value, costume: carryCostume.value, background: carryBackground.value },
  })
}
</script>

<style scoped>
.event-view { width: 100%; height: 100%; display: flex; }

.sidebar {
  width: 340px; min-width: 280px; padding: 14px; border-right: 1px solid #1A1A1A;
  overflow-y: auto; display: flex; flex-direction: column; gap: 6px;
}
.sidebar h3 { color: #E8E8E8; font-size: 14px; margin: 0 0 6px; }
.section { margin-bottom: 2px; }
.sec-label { color: #585858; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.rating-row { display: flex; gap: 6px; margin-top: 4px; }
.chk { color: #B0B0B0; font-size: 11px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.chk input { accent-color: #E2B340; }
.input-area {
  background: #131313; border: none; border-radius: 4px; padding: 8px;
  color: #E8E8E8; font-size: 12px; resize: vertical; outline: none; font-family: inherit; width: 100%;
}
.finput {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; outline: none; width: 100%;
}
.row { display: flex; align-items: center; gap: 6px; }
.mini-label { color: #484848; font-size: 10px; }
.num-input {
  width: 50px; background: #131313; border: none; border-radius: 4px;
  padding: 4px 6px; color: #E8E8E8; font-size: 12px; text-align: center; outline: none;
}
.btn-search {
  padding: 10px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer; margin-top: 4px;
}
.btn-search:disabled { opacity: 0.4; }
.status { color: #E2B340; font-size: 11px; text-align: center; font-weight: 600; }

.event-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }
.event-item {
  padding: 6px 8px; border: 1px solid #1A1A1A; border-radius: 4px; cursor: pointer;
  display: flex; align-items: center; gap: 6px; font-size: 11px; transition: border-color 0.15s;
}
.event-item:hover { border-color: #333; }
.event-item.selected { border-color: #E2B340; background: #1a1810; }
.ev-idx { color: #E2B340; font-weight: 700; font-size: 10px; }
.ev-desc { color: #B0B0B0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-count { color: #585858; font-size: 10px; }

/* 우측 */
.main-area { flex: 1; display: flex; flex-direction: column; }
.empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #484848; font-size: 14px; text-align: center; line-height: 1.6;
}
.empty-icon { font-size: 48px; opacity: 0.2; margin-bottom: 12px; }

.carry-bar {
  display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-bottom: 1px solid #1A1A1A;
}
.steps-scroll { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.step-card { padding: 10px 12px; border: 1px solid #1A1A1A; border-radius: 6px; }
.step-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.step-num { color: #E2B340; font-size: 12px; font-weight: 700; }
.step-type { color: #585858; font-size: 10px; padding: 1px 6px; background: #1A1A1A; border-radius: 3px; }
.step-type.child { color: #4CAF50; background: #1a2a1a; }
.step-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.tag { font-size: 10px; padding: 2px 6px; border-radius: 3px; }
.tag.added { background: #1a2e1a; color: #4CAF50; }
.tag.removed { background: #2e1a1a; color: #E05252; }
.step-prompt-preview { font-size: 11px; color: #787878; line-height: 1.4; }

.bottom-actions {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-top: 1px solid #1A1A1A;
}
.btn-group { display: flex; gap: 8px; }
.btn-action {
  padding: 8px 18px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-weight: 600; font-size: 12px; cursor: pointer;
}
.btn-action.primary { background: #E2B340; color: #000; }
.btn-action:hover { opacity: 0.85; }
</style>
