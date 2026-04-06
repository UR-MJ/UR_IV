<template>
  <div class="search-view">
    <!-- 좌측: 검색 설정 -->
    <div class="search-sidebar">
      <h3>Danbooru Search</h3>

      <!-- 레이팅 -->
      <div class="section">
        <label class="sec-label">Rating</label>
        <div class="rating-row">
          <label v-for="r in ratings" :key="r.key" class="chk">
            <input type="checkbox" v-model="r.checked" /> {{ r.label }}
          </label>
        </div>
      </div>

      <!-- 검색 (포함) -->
      <div class="section">
        <label class="sec-label">검색 (포함)</label>
        <div class="tip">💡 쉼표(,)=AND, [A|B]=OR</div>
        <div class="field-grid">
          <div class="field" v-for="f in fields" :key="f.key">
            <label class="flabel">{{ f.label }}</label>
            <input class="finput" v-model="f.include" :placeholder="f.placeholder" @keydown.enter="search" />
          </div>
        </div>
      </div>

      <!-- 제외 -->
      <div class="section exclude-section">
        <label class="sec-label exclude">제외할 태그</label>
        <div class="field-grid">
          <div class="field" v-for="f in fields" :key="'ex-'+f.key">
            <label class="flabel">{{ f.label }}</label>
            <input class="finput" v-model="f.exclude" :placeholder="'제외할 '+f.label" @keydown.enter="search" />
          </div>
        </div>
      </div>

      <button class="btn-search" @click="search" :disabled="searching">
        {{ searching ? '검색 중...' : '🚀 고속 검색 시작' }}
      </button>
      <div class="status">{{ statusText }}</div>

      <!-- 집중 검색 -->
      <div class="section" v-if="results.length > 0">
        <label class="sec-label">집중 검색 (결과 내 필터)</label>
        <div class="focus-row">
          <input class="finput" v-model="focusInclude" placeholder="포함할 태그" @keydown.enter="applyFocus" />
          <input class="finput" v-model="focusExclude" placeholder="제외할 태그" @keydown.enter="applyFocus" />
          <button class="btn-sm" @click="applyFocus">필터링</button>
        </div>
      </div>
    </div>

    <!-- 우측: 결과 미리보기 -->
    <div class="result-panel">
      <div v-if="results.length === 0" class="empty">
        검색 조건을 입력하고 검색을 시작하세요
      </div>
      <template v-else>
        <!-- 인덱스 + 네비게이션 -->
        <div class="nav-bar">
          <button class="nav-btn" @click="prevResult" :disabled="previewIdx <= 0">◀ 이전</button>
          <span class="nav-idx">[ {{ previewIdx + 1 }} / {{ filteredResults.length }} ]</span>
          <button class="nav-btn" @click="randomResult">🎲 랜덤</button>
          <button class="nav-btn" @click="nextResult" :disabled="previewIdx >= filteredResults.length - 1">다음 ▶</button>
        </div>

        <!-- 미리보기 카드 -->
        <div class="preview-card" v-if="currentResult">
          <div class="tag-section">
            <div class="tag-row"><span class="tag-cat copyright">작품</span> {{ currentResult.copyright || '-' }}</div>
            <div class="tag-row"><span class="tag-cat character">캐릭터</span> {{ currentResult.character || '-' }}</div>
            <div class="tag-row"><span class="tag-cat artist">작가</span> {{ currentResult.artist || '-' }}</div>
            <div class="tag-row"><span class="tag-cat rating">레이팅</span> {{ currentResult.rating || '-' }}</div>
          </div>
          <div class="general-tags">
            <label class="flabel">일반 태그</label>
            <div class="general-text">{{ currentResult.general || '' }}</div>
          </div>
          <div class="card-actions">
            <button class="btn-action apply" @click="applyResult">즉시 적용</button>
            <button class="btn-action queue" @click="addToQueue">대기열 추가</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const ratings = reactive([
  { key: 'g', label: 'General', checked: true },
  { key: 's', label: 'Sensitive', checked: false },
  { key: 'q', label: 'Questionable', checked: false },
  { key: 'e', label: 'Explicit', checked: false },
])
const fields = reactive([
  { key: 'copyright', label: '작품', placeholder: 'pokemon, [genshin|honkai]', include: '', exclude: '' },
  { key: 'character', label: '캐릭터', placeholder: 'hatsune_miku', include: '', exclude: '' },
  { key: 'artist', label: '작가', placeholder: '작가명', include: '', exclude: '' },
  { key: 'general', label: '일반태그', placeholder: '1boy, [blue_hair|red_hair]', include: '', exclude: '' },
])
const results = ref([])
const filteredResults = ref([])
const previewIdx = ref(0)
const searching = ref(false)
const statusText = ref('준비 완료')
const focusInclude = ref('')
const focusExclude = ref('')

const currentResult = computed(() => filteredResults.value[previewIdx.value] || null)

async function search() {
  searching.value = true
  statusText.value = '검색 중...'
  const backend = await getBackend()
  const query = {
    ratings: ratings.filter(r => r.checked).map(r => r.key),
    queries: Object.fromEntries(fields.map(f => [f.key, f.include])),
    excludes: Object.fromEntries(fields.map(f => [f.key, f.exclude])),
  }
  if (backend.searchDanbooru) {
    backend.searchDanbooru(JSON.stringify(query), (json) => {
      try {
        const data = JSON.parse(json)
        if (Array.isArray(data)) {
          results.value = data
          filteredResults.value = data
          previewIdx.value = 0
          statusText.value = `${data.length}개 결과`
        } else {
          statusText.value = data.error || '검색 실패'
        }
      } catch { statusText.value = '파싱 오류' }
      searching.value = false
    })
  }
}

function applyFocus() {
  const inc = focusInclude.value.toLowerCase().split(',').map(s => s.trim()).filter(Boolean)
  const exc = focusExclude.value.toLowerCase().split(',').map(s => s.trim()).filter(Boolean)
  filteredResults.value = results.value.filter(r => {
    const all = `${r.copyright} ${r.character} ${r.artist} ${r.general}`.toLowerCase()
    if (inc.length && !inc.every(t => all.includes(t))) return false
    if (exc.length && exc.some(t => all.includes(t))) return false
    return true
  })
  previewIdx.value = 0
  statusText.value = `필터: ${filteredResults.value.length} / ${results.value.length}개`
}

function prevResult() { if (previewIdx.value > 0) previewIdx.value-- }
function nextResult() { if (previewIdx.value < filteredResults.value.length - 1) previewIdx.value++ }
function randomResult() {
  if (filteredResults.value.length > 1) {
    previewIdx.value = Math.floor(Math.random() * filteredResults.value.length)
  }
}

function applyResult() {
  if (currentResult.value) requestAction('apply_search_result', currentResult.value)
}
function addToQueue() {
  if (currentResult.value) requestAction('add_search_to_queue', currentResult.value)
}
</script>

<style scoped>
.search-view { height: 100%; display: flex; }

/* 좌측 사이드바 */
.search-sidebar {
  width: 360px; min-width: 300px; padding: 16px; border-right: 1px solid #1A1A1A;
  overflow-y: auto; display: flex; flex-direction: column; gap: 6px;
}
.search-sidebar h3 { color: #E8E8E8; font-size: 15px; margin: 0 0 8px; }
.section { margin-bottom: 4px; }
.sec-label { color: #585858; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.sec-label.exclude { color: #E05252; }
.exclude-section { border: 1px solid #2a1515; border-radius: 6px; padding: 8px; }
.tip { color: #484848; font-size: 10px; margin: 2px 0 6px; }
.rating-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.chk { color: #B0B0B0; font-size: 12px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.chk input { accent-color: #E2B340; }
.field-grid { display: flex; flex-direction: column; gap: 4px; }
.field { display: flex; flex-direction: column; gap: 2px; }
.flabel { color: #484848; font-size: 10px; font-weight: 600; }
.finput {
  background: #131313; border: none; border-radius: 4px; padding: 7px 10px;
  color: #E8E8E8; font-size: 12px; outline: none; width: 100%;
}
.finput:focus { background: #1A1A1A; }
.btn-search {
  padding: 12px; background: #4CAF50; border: none; border-radius: 6px;
  color: #fff; font-weight: 700; font-size: 14px; cursor: pointer; margin-top: 8px;
}
.btn-search:disabled { opacity: 0.4; cursor: not-allowed; }
.status { color: #E2B340; font-size: 11px; text-align: center; font-weight: 600; }
.focus-row { display: flex; gap: 4px; margin-top: 4px; }
.focus-row .finput { flex: 1; }
.btn-sm {
  padding: 6px 12px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer; white-space: nowrap;
}
.btn-sm:hover { background: #222; color: #E8E8E8; }

/* 우측 결과 */
.result-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #484848; font-size: 14px; }
.nav-bar {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 10px; border-bottom: 1px solid #1A1A1A;
}
.nav-btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.nav-btn:hover { background: #222; color: #E8E8E8; }
.nav-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.nav-idx { color: #585858; font-size: 12px; min-width: 80px; text-align: center; }

.preview-card { flex: 1; padding: 16px; overflow-y: auto; }
.tag-section { margin-bottom: 12px; }
.tag-row { font-size: 13px; color: #B0B0B0; padding: 4px 0; border-bottom: 1px solid #111; }
.tag-cat {
  display: inline-block; min-width: 50px; font-size: 11px; font-weight: 700; margin-right: 8px;
}
.tag-cat.copyright { color: #9b59b6; }
.tag-cat.character { color: #2ecc71; }
.tag-cat.artist { color: #e74c3c; }
.tag-cat.rating { color: #E2B340; }
.general-tags { margin-bottom: 16px; }
.general-text {
  font-size: 12px; color: #787878; line-height: 1.6; max-height: 200px;
  overflow-y: auto; padding: 8px; background: #111; border-radius: 4px;
  word-break: break-all;
}
.card-actions { display: flex; gap: 8px; }
.btn-action {
  flex: 1; padding: 10px; border: none; border-radius: 6px; font-weight: 700;
  font-size: 13px; cursor: pointer;
}
.btn-action.apply { background: #E2B340; color: #000; }
.btn-action.apply:hover { background: #F0C850; }
.btn-action.queue { background: #181818; color: #787878; }
.btn-action.queue:hover { background: #222; color: #E8E8E8; }
</style>
