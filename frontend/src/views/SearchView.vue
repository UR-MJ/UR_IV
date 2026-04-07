<template>
  <div class="search-workspace">
    <!-- Left Sidebar: Filters -->
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <div class="sidebar-header">
          <span class="icon">🔍</span>
          <h3>TAG EXPLORER</h3>
        </div>

        <div class="glass-card">
          <label>Rating Filter</label>
          <div class="chip-grid-2">
            <button v-for="r in ratings" :key="r.key"
              class="mini-chip" :class="{ active: r.checked }"
              @click="r.checked = !r.checked"
            >{{ r.label }}</button>
          </div>
        </div>

        <div class="glass-card">
          <label>Include Tags</label>
          <div class="field-stack">
            <div class="input-unit" v-for="f in fields" :key="f.key">
              <span class="unit-label">{{ f.label }}</span>
              <input v-model="f.include" :placeholder="f.placeholder" @keydown.enter="search" />
            </div>
          </div>
        </div>

        <div class="glass-card danger">
          <label class="danger">Exclude Tags</label>
          <div class="field-stack">
            <div class="input-unit" v-for="f in fields" :key="'ex-'+f.key">
              <input v-model="f.exclude" :placeholder="'No ' + f.label + '...'" @keydown.enter="search" />
            </div>
          </div>
        </div>

        <div class="glass-card info-box">
          <label>Search Syntax</label>
          <div class="syntax-info">
            <div>쉼표(,) = AND 조건</div>
            <div>[A|B] = OR (A 또는 B)</div>
            <div>제외: 해당 태그 포함 결과 제거</div>
          </div>
        </div>
      </div>

      <div class="sidebar-footer">
        <button class="btn-search" @click="search" :disabled="searching">
          <span v-if="!searching">RUN ENGINE</span>
          <span v-else>SEARCHING...</span>
        </button>
        <div class="search-progress" v-if="searching">
          <div class="search-progress-bar"><div class="search-progress-fill" :style="{ width: searchProgress + '%' }"></div></div>
        </div>
        <div class="status-msg">{{ statusText }}</div>
        <!-- .parquet 저장/불러오기 -->
        <div class="io-row" v-if="results.length > 0">
          <button class="io-btn" @click="exportResults">📥 EXPORT</button>
          <button class="io-btn" @click="importResults">📤 IMPORT</button>
        </div>
      </div>
    </aside>

    <!-- Center: Results List + Preview -->
    <section class="result-area">
      <div v-if="results.length === 0 && !searching" class="empty-state">
        <div class="empty-icon">🗂</div>
        <h2>READY TO DISCOVER</h2>
        <p>좌측에서 검색 조건을 입력하고 RUN ENGINE을 클릭하세요</p>
      </div>

      <template v-else-if="results.length > 0">
        <!-- 상단 컨트롤 -->
        <div class="result-toolbar">
          <div class="nav-controls">
            <button class="nav-btn" @click="prevResult" :disabled="previewIdx <= 0">◀ PREV</button>
            <span class="idx-display"><b>{{ previewIdx + 1 }}</b> / {{ filteredResults.length }}</span>
            <button class="nav-btn" @click="nextResult" :disabled="previewIdx >= filteredResults.length - 1">NEXT ▶</button>
            <button class="nav-btn accent" @click="randomResult">🎲 RANDOM</button>
          </div>
          <div class="focus-controls">
            <input v-model="focusInclude" placeholder="Focus include..." @keydown.enter="applyFocus" class="focus-input" />
            <input v-model="focusExclude" placeholder="Focus exclude..." @keydown.enter="applyFocus" class="focus-input" />
            <button class="nav-btn" @click="applyFocus">FILTER</button>
          </div>
        </div>

        <div class="result-body">
          <!-- 좌측: 결과 목록 (스크롤) -->
          <div class="result-list">
            <div v-for="(r, i) in filteredResults" :key="i" class="list-item"
              :class="{ active: previewIdx === i }" @click="previewIdx = i"
            >
              <span class="list-idx">{{ i + 1 }}</span>
              <span class="list-char">{{ r.character || 'GENERIC' }}</span>
              <span class="list-copy">{{ r.copyright || '' }}</span>
            </div>
          </div>

          <!-- 우측: 상세 프리뷰 -->
          <div class="preview-card" v-if="currentResult">
            <div class="meta-grid">
              <div class="meta-cell"><label>Project</label><div class="meta-val">{{ currentResult.copyright || 'ORIGINAL' }}</div></div>
              <div class="meta-cell"><label>Artist</label><div class="meta-val highlight">{{ currentResult.artist || 'UNKNOWN' }}</div></div>
              <div class="meta-cell"><label>Character</label><div class="meta-val character">{{ currentResult.character || 'GENERIC' }}</div></div>
            </div>
            <div class="tag-cloud-section">
              <label>General Tags</label>
              <div class="tag-cloud">
                <span v-for="tag in currentTags" :key="tag" class="tag-chip">{{ tag }}</span>
              </div>
            </div>
            <div class="action-bar">
              <button class="main-action apply" @click="applyResult">USE AS PROMPT</button>
              <button class="main-action queue" @click="addToQueue">ADD TO QUEUE</button>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const ratings = reactive([
  { key: 'g', label: 'GEN', checked: true },
  { key: 's', label: 'SENS', checked: false },
  { key: 'q', label: 'QUES', checked: false },
  { key: 'e', label: 'EXPL', checked: false },
])
const fields = reactive([
  { key: 'copyright', label: 'PROJECT', placeholder: 'e.g. genshin', include: '', exclude: '' },
  { key: 'character', label: 'CHAR', placeholder: 'e.g. raiden_shogun', include: '', exclude: '' },
  { key: 'artist', label: 'ARTIST', placeholder: 'Artist name...', include: '', exclude: '' },
  { key: 'general', label: 'TAGS', placeholder: '1boy, blue_hair...', include: '', exclude: '' },
])
const results = ref([])
const filteredResults = ref([])
const previewIdx = ref(0)
const searching = ref(false)
const statusText = ref('READY')
const searchProgress = ref(0)
const focusInclude = ref('')
const focusExclude = ref('')
let progressTimer = null

const currentResult = computed(() => filteredResults.value[previewIdx.value] || null)
const currentTags = computed(() => {
  const g = currentResult.value?.general || ''
  return g.split(/[\s,]+/).filter(Boolean).map(t => t.replace(/_/g, ' '))
})

async function search() {
  searching.value = true; statusText.value = 'EXPLORING...'
  searchProgress.value = 0
  progressTimer = setInterval(() => { if (searchProgress.value < 90) searchProgress.value += Math.random() * 15 }, 500)
  const backend = await getBackend()
  const query = {
    ratings: ratings.filter(r => r.checked).map(r => r.key),
    queries: Object.fromEntries(fields.map(f => [f.key, f.include])),
    excludes: Object.fromEntries(fields.map(f => [f.key, f.exclude])),
  }
  if (backend.searchDanbooru) backend.searchDanbooru(JSON.stringify(query))
}

onMounted(() => {
  onBackendEvent('searchResultsReady', (json) => {
    try {
      const data = JSON.parse(json)
      if (Array.isArray(data)) {
        results.value = data; filteredResults.value = data; previewIdx.value = 0
        statusText.value = `${data.length} MATCHES FOUND`
      } else { statusText.value = 'SEARCH FAILED' }
    } catch { statusText.value = 'PARSE ERROR' }
    searching.value = false; searchProgress.value = 100
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
  })
  onBackendEvent('searchStatus', (msg) => { statusText.value = msg.toUpperCase() })
})

function applyFocus() {
  const inc = focusInclude.value.toLowerCase().trim()
  const exc = focusExclude.value.toLowerCase().trim()
  filteredResults.value = results.value.filter(r => {
    const all = `${r.copyright} ${r.character} ${r.artist} ${r.general}`.toLowerCase()
    if (inc && !inc.split(',').every(t => all.includes(t.trim()))) return false
    if (exc && exc.split(',').some(t => all.includes(t.trim()))) return false
    return true
  })
  previewIdx.value = 0
  statusText.value = `FILTERED: ${filteredResults.value.length} / ${results.value.length}`
}

function prevResult() { if (previewIdx.value > 0) previewIdx.value-- }
function nextResult() { if (previewIdx.value < filteredResults.value.length - 1) previewIdx.value++ }
function randomResult() { if (filteredResults.value.length > 1) previewIdx.value = Math.floor(Math.random() * filteredResults.value.length) }
function applyResult() { if (currentResult.value) requestAction('apply_search_result', currentResult.value) }
function addToQueue() { if (currentResult.value) requestAction('add_search_to_queue', currentResult.value) }
function exportResults() { requestAction('export_search_results', { count: results.value.length }) }
function importResults() { requestAction('import_search_results') }
</script>

<style scoped>
.search-workspace { height: 100%; display: flex; background: var(--bg-primary); }

.sidebar { width: 300px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); }
.sidebar-scroll { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.sidebar-header { display: flex; align-items: center; gap: 10px; padding-bottom: 4px; }
.sidebar-header .icon { font-size: 18px; }
.sidebar-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-secondary); }

.glass-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 12px; }
.glass-card.danger { border-color: rgba(248, 113, 113, 0.1); }
.info-box .syntax-info { font-size: 10px; color: var(--text-muted); line-height: 1.8; }
.chip-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
.mini-chip { height: 26px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; }
.mini-chip.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.field-stack { display: flex; flex-direction: column; gap: 6px; }
.input-unit { position: relative; }
.unit-label { position: absolute; left: 8px; top: -5px; background: var(--bg-secondary); padding: 0 3px; font-size: 8px; font-weight: 900; color: var(--text-muted); }

.sidebar-footer { padding: 12px; background: var(--bg-card); border-top: 1px solid var(--border); }
.btn-search { width: 100%; height: 40px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
.status-msg { font-size: 9px; font-weight: 800; color: var(--text-muted); text-align: center; margin-top: 6px; }
.search-progress { margin-top: 6px; }
.search-progress-bar { width: 100%; height: 3px; background: var(--bg-input); border-radius: 2px; overflow: hidden; }
.search-progress-fill { height: 100%; background: var(--accent); transition: width 0.4s; }
.io-row { display: flex; gap: 4px; margin-top: 6px; }
.io-btn { flex: 1; padding: 5px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 9px; font-weight: 700; cursor: pointer; }

/* Result Area */
.result-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0.2; text-align: center; }
.empty-icon { font-size: 64px; margin-bottom: 16px; }

.result-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; background: var(--bg-secondary); border-bottom: 1px solid var(--border); gap: 12px; flex-wrap: wrap; }
.nav-controls { display: flex; align-items: center; gap: 8px; }
.nav-btn { padding: 5px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 10px; font-weight: 700; cursor: pointer; }
.nav-btn:hover:not(:disabled) { border-color: var(--text-muted); color: var(--text-primary); }
.nav-btn.accent { border-color: var(--accent-dim); color: var(--accent); }
.nav-btn:disabled { opacity: 0.3; }
.idx-display { font-size: 12px; color: var(--text-secondary); font-family: monospace; }
.idx-display b { color: var(--accent); font-size: 16px; }
.focus-controls { display: flex; gap: 4px; align-items: center; }
.focus-input { width: 140px; padding: 5px 8px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: 10px; }

.result-body { flex: 1; display: flex; overflow: hidden; }

/* Result List (좌측 목록) */
.result-list { width: 280px; overflow-y: auto; border-right: 1px solid var(--border); flex-shrink: 0; }
.list-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.03); transition: 0.1s; }
.list-item:hover { background: rgba(255,255,255,0.02); }
.list-item.active { background: var(--accent-dim); border-left: 3px solid var(--accent); }
.list-idx { font-size: 10px; color: var(--text-muted); min-width: 28px; font-family: monospace; }
.list-char { font-size: 11px; color: var(--text-primary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list-copy { font-size: 9px; color: var(--text-muted); }

/* Preview Card (우측 상세) */
.preview-card { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.meta-cell { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.meta-cell label { font-size: 9px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; }
.meta-val { font-size: 14px; font-weight: 800; margin-top: 6px; color: var(--text-primary); }
.meta-val.highlight { color: var(--accent); }
.meta-val.character { color: #4ade80; }

.tag-cloud-section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.tag-cloud-section label { font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; margin-bottom: 10px; display: block; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 5px; }
.tag-chip { padding: 4px 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: #787878; font-size: 10px; }

.action-bar { display: flex; gap: 10px; margin-top: auto; }
.main-action { flex: 1; height: 46px; border-radius: var(--radius-pill); border: none; font-weight: 900; font-size: 12px; letter-spacing: 1px; cursor: pointer; transition: var(--transition); }
.main-action.apply { background: var(--accent); color: #000; }
.main-action.queue { background: var(--bg-button); color: var(--text-secondary); border: 1px solid var(--border); }
.main-action:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }

label.danger { color: #f87171; }
</style>
