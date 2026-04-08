<template>
  <div class="search-workspace">
    <!-- Left: Search Panel (넓은 폼) -->
    <aside class="search-panel">
      <div class="panel-scroll">
        <div class="panel-header">
          <span class="icon">🔍</span>
          <h3>TAG EXPLORER</h3>
        </div>

        <!-- Rating -->
        <div class="card">
          <label>Rating</label>
          <div class="chip-row">
            <button v-for="r in ratings" :key="r.key" class="chip"
              :class="{ active: r.checked }" @click="r.checked = !r.checked">{{ r.label }}</button>
          </div>
        </div>

        <!-- Include -->
        <div class="card">
          <label>Include Tags</label>
          <div class="field-grid">
            <div class="field" v-for="f in fields" :key="f.key">
              <span class="field-label">{{ f.label }}</span>
              <input v-model="f.include" :placeholder="f.placeholder" @keydown.enter="search" />
            </div>
          </div>
        </div>

        <!-- Exclude -->
        <div class="card danger-border">
          <label class="danger">Exclude Tags</label>
          <div class="field-grid">
            <div class="field" v-for="f in fields" :key="'ex-'+f.key">
              <span class="field-label danger">{{ f.label }}</span>
              <input v-model="f.exclude" :placeholder="'제외...'" @keydown.enter="search" />
            </div>
          </div>
        </div>

        <!-- 심층검색 (결과 내 재검색) -->
        <div class="card accent-border" v-if="results.length > 0">
          <label>심층 검색 (결과 내 필터)</label>
          <div class="field-grid">
            <div class="field">
              <span class="field-label">포함</span>
              <input v-model="deepInclude" placeholder="포함할 태그 (쉼표 구분)" @keydown.enter="applyDeepSearch" />
            </div>
            <div class="field">
              <span class="field-label danger">제외</span>
              <input v-model="deepExclude" placeholder="제외할 태그 (쉼표 구분)" @keydown.enter="applyDeepSearch" />
            </div>
          </div>
          <div class="btn-row">
            <button class="action-btn" @click="applyDeepSearch">DEEP FILTER</button>
            <button class="action-btn ghost" @click="resetDeepSearch">RESET</button>
          </div>
        </div>

        <!-- 검색 조건 안내 -->
        <div class="card info">
          <div class="syntax">쉼표(,) = AND · [A|B] = OR · 제외 필드는 해당 태그 포함 결과 제거</div>
        </div>
      </div>

      <!-- Footer: 검색 버튼 + IO -->
      <div class="panel-footer">
        <button class="btn-search" @click="search" :disabled="searching">
          {{ searching ? 'SEARCHING...' : 'RUN ENGINE' }}
        </button>
        <div class="progress-bar" v-if="searching">
          <div class="progress-fill" :style="{ width: searchProgress + '%' }"></div>
        </div>
        <div class="status">{{ statusText }}</div>
        <div class="io-row" v-if="results.length > 0">
          <button class="io-btn" @click="exportResults">📥 EXPORT</button>
          <button class="io-btn" @click="importResults">📤 IMPORT</button>
        </div>
      </div>
    </aside>

    <!-- Center: Results -->
    <section class="results-area">
      <!-- 검색 전: 중앙 큰 검색 UI -->
      <div v-if="results.length === 0 && !searching" class="welcome-search">
        <div class="ws-header">
          <div class="ws-icon">🔍</div>
          <h1>TAG EXPLORER</h1>
          <p>Danbooru 데이터베이스에서 프롬프트를 검색합니다</p>
        </div>
        <div class="ws-quick-form">
          <div class="ws-row">
            <div class="ws-field">
              <label>Character</label>
              <input v-model="fields[1].include" placeholder="e.g. hatsune_miku, raiden_shogun" @keydown.enter="search" />
            </div>
            <div class="ws-field">
              <label>Copyright</label>
              <input v-model="fields[0].include" placeholder="e.g. genshin_impact" @keydown.enter="search" />
            </div>
          </div>
          <div class="ws-row">
            <div class="ws-field">
              <label>General Tags</label>
              <input v-model="fields[3].include" placeholder="e.g. 1girl, blue_hair, sword, outdoors" @keydown.enter="search" />
            </div>
            <div class="ws-field narrow">
              <label>Artist</label>
              <input v-model="fields[2].include" placeholder="Artist..." @keydown.enter="search" />
            </div>
          </div>
          <div class="ws-row center">
            <div class="ws-ratings">
              <button v-for="r in ratings" :key="r.key" class="ws-chip"
                :class="{ active: r.checked }" @click="r.checked = !r.checked">{{ r.label }}</button>
            </div>
            <button class="ws-go" @click="search" :disabled="searching">
              {{ searching ? 'SEARCHING...' : '🚀 RUN ENGINE' }}
            </button>
          </div>
        </div>
        <div class="ws-hints">
          <span>쉼표(,) = AND</span>
          <span>[A|B] = OR</span>
          <span>좌측 패널에서 제외 조건 설정 가능</span>
        </div>
      </div>

      <!-- 검색 중 -->
      <div v-else-if="results.length === 0 && searching" class="empty">
        <div class="search-spinner"></div>
        <h2>SEARCHING...</h2>
        <p>{{ statusText }}</p>
      </div>

      <template v-else-if="filteredResults.length > 0">
        <!-- 상단 네비게이션 -->
        <div class="toolbar">
          <div class="toolbar-left">
            <button class="tb-btn" @click="viewMode = 'single'" :class="{ active: viewMode === 'single' }">📄 Single</button>
            <button class="tb-btn" @click="viewMode = 'list'" :class="{ active: viewMode === 'list' }">📋 List</button>
            <span class="tb-sep">|</span>
            <button class="tb-btn" @click="prevResult" :disabled="previewIdx <= 0">◀</button>
            <span class="tb-idx"><b>{{ previewIdx + 1 }}</b> / {{ filteredResults.length }}</span>
            <button class="tb-btn" @click="nextResult" :disabled="previewIdx >= filteredResults.length - 1">▶</button>
            <button class="tb-btn accent" @click="randomResult">🎲 RANDOM</button>
          </div>
          <div class="toolbar-right">
            <span class="result-count">{{ filteredResults.length }} results</span>
          </div>
        </div>

        <!-- Single View (한 개씩 상세) -->
        <div v-if="viewMode === 'single'" class="single-view">
          <div class="detail-card" v-if="currentResult">
            <div class="detail-meta">
              <div class="meta-pill"><span class="meta-label">PROJECT</span>{{ currentResult.copyright || 'ORIGINAL' }}</div>
              <div class="meta-pill artist"><span class="meta-label">ARTIST</span>{{ currentResult.artist || 'UNKNOWN' }}</div>
              <div class="meta-pill character"><span class="meta-label">CHAR</span>{{ currentResult.character || 'GENERIC' }}</div>
            </div>
            <div class="tag-section">
              <label>General Tags ({{ currentTags.length }})</label>
              <div class="tag-cloud">
                <span v-for="tag in currentTags" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </div>
            <div class="detail-actions">
              <button class="primary-btn" @click="applyResult">USE AS PROMPT</button>
              <button class="secondary-btn" @click="addToQueue">ADD TO QUEUE</button>
              <button class="secondary-btn" @click="randomResult">🎲 NEXT RANDOM</button>
            </div>
          </div>
        </div>

        <!-- List View (목록 보기) -->
        <div v-else class="list-view">
          <div class="list-header">
            <span class="lh-col idx">#</span>
            <span class="lh-col char">Character</span>
            <span class="lh-col copy">Copyright</span>
            <span class="lh-col artist">Artist</span>
            <span class="lh-col tags">Tags</span>
            <span class="lh-col act">Action</span>
          </div>
          <div class="list-scroll">
            <div v-for="(r, i) in pagedResults" :key="i" class="list-row"
              :class="{ active: previewIdx === listPage * listPageSize + i }"
              @click="previewIdx = listPage * listPageSize + i; viewMode = 'single'"
            >
              <span class="lr-col idx">{{ listPage * listPageSize + i + 1 }}</span>
              <span class="lr-col char">{{ r.character || '-' }}</span>
              <span class="lr-col copy">{{ r.copyright || '-' }}</span>
              <span class="lr-col artist">{{ r.artist || '-' }}</span>
              <span class="lr-col tags">{{ (r.general || '').substring(0, 80) }}...</span>
              <span class="lr-col act">
                <button class="mini-btn" @click.stop="previewIdx = listPage * listPageSize + i; applyResult()">USE</button>
              </span>
            </div>
          </div>
          <div class="list-pager">
            <button class="tb-btn" @click="listPage = Math.max(0, listPage - 1)" :disabled="listPage <= 0">◀ Prev</button>
            <span class="pager-info">{{ listPage + 1 }} / {{ totalListPages }}</span>
            <button class="tb-btn" @click="listPage = Math.min(totalListPages - 1, listPage + 1)" :disabled="listPage >= totalListPages - 1">Next ▶</button>
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
  { key: 'copyright', label: 'PROJECT', placeholder: 'e.g. genshin_impact', include: '', exclude: '' },
  { key: 'character', label: 'CHAR', placeholder: 'e.g. raiden_shogun', include: '', exclude: '' },
  { key: 'artist', label: 'ARTIST', placeholder: 'Artist name...', include: '', exclude: '' },
  { key: 'general', label: 'TAGS', placeholder: '1girl, blue_hair, sword...', include: '', exclude: '' },
])

const results = ref([])
const filteredResults = ref([])
const previewIdx = ref(0)
const searching = ref(false)
const statusText = ref('READY')
const searchProgress = ref(0)
const viewMode = ref('single')
const deepInclude = ref('')
const deepExclude = ref('')
const listPage = ref(0)
const listPageSize = 50
let progressTimer = null

const currentResult = computed(() => filteredResults.value[previewIdx.value] || null)
const currentTags = computed(() => {
  const g = currentResult.value?.general || ''
  return g.split(/[\s,]+/).filter(Boolean).map(t => t.replace(/_/g, ' '))
})
const totalListPages = computed(() => Math.max(1, Math.ceil(filteredResults.value.length / listPageSize)))
const pagedResults = computed(() => {
  const start = listPage.value * listPageSize
  return filteredResults.value.slice(start, start + listPageSize)
})

async function search() {
  searching.value = true; statusText.value = 'EXPLORING...'
  searchProgress.value = 0
  progressTimer = setInterval(() => { if (searchProgress.value < 90) searchProgress.value += Math.random() * 12 }, 500)
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
        statusText.value = `${data.length} MATCHES`
        deepInclude.value = ''; deepExclude.value = ''
      } else statusText.value = 'FAILED'
    } catch { statusText.value = 'PARSE ERROR' }
    searching.value = false; searchProgress.value = 100
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
  })
  onBackendEvent('searchStatus', (msg) => { statusText.value = msg.toUpperCase() })
})

// 심층 검색 (결과 내 재필터)
function applyDeepSearch() {
  const inc = deepInclude.value.toLowerCase().trim()
  const exc = deepExclude.value.toLowerCase().trim()
  const base = results.value  // 항상 원본 기준
  filteredResults.value = base.filter(r => {
    const all = `${r.copyright} ${r.character} ${r.artist} ${r.general}`.toLowerCase()
    if (inc) { for (const t of inc.split(',')) { if (t.trim() && !all.includes(t.trim())) return false } }
    if (exc) { for (const t of exc.split(',')) { if (t.trim() && all.includes(t.trim())) return false } }
    return true
  })
  previewIdx.value = 0; listPage.value = 0
  statusText.value = `DEEP: ${filteredResults.value.length} / ${results.value.length}`
}
function resetDeepSearch() {
  deepInclude.value = ''; deepExclude.value = ''
  filteredResults.value = results.value
  previewIdx.value = 0; listPage.value = 0
  statusText.value = `${results.value.length} MATCHES`
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

/* ═══ Search Panel (Left) ═══ */
.search-panel {
  width: 380px; display: flex; flex-direction: column;
  background: var(--bg-secondary); border-right: 1px solid var(--border);
}
.panel-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.panel-header { display: flex; align-items: center; gap: 10px; }
.panel-header .icon { font-size: 20px; }
.panel-header h3 { font-size: 13px; letter-spacing: 2px; color: var(--text-secondary); }

.card {
  background: rgba(255,255,255,0.02); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 14px;
}
.card.danger-border { border-color: rgba(248, 113, 113, 0.15); }
.card.accent-border { border-color: var(--accent-dim); background: rgba(250,204,21,0.02); }
.card.info { padding: 10px; }
.syntax { font-size: 10px; color: var(--text-muted); line-height: 1.6; }

.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.field { display: flex; flex-direction: column; gap: 2px; }
.field-label { font-size: 8px; font-weight: 900; color: var(--text-muted); letter-spacing: 0.5px; }
.field-label.danger { color: #f87171; }

.chip-row { display: flex; gap: 4px; }
.chip {
  flex: 1; height: 28px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer;
}
.chip.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }

.btn-row { display: flex; gap: 6px; margin-top: 8px; }
.action-btn {
  flex: 1; padding: 7px; background: var(--accent); border: none; border-radius: 6px;
  color: #000; font-size: 10px; font-weight: 800; cursor: pointer;
}
.action-btn.ghost { background: transparent; border: 1px solid var(--border); color: var(--text-secondary); }

.panel-footer { padding: 14px; background: var(--bg-card); border-top: 1px solid var(--border); }
.btn-search {
  width: 100%; height: 42px; background: var(--accent); border: none;
  border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 12px; letter-spacing: 1px; cursor: pointer;
}
.progress-bar { width: 100%; height: 3px; background: var(--bg-input); border-radius: 2px; overflow: hidden; margin-top: 6px; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.4s; }
.status { font-size: 9px; font-weight: 800; color: var(--text-muted); text-align: center; margin-top: 6px; letter-spacing: 1px; }
.io-row { display: flex; gap: 4px; margin-top: 8px; }
.io-btn { flex: 1; padding: 6px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 9px; font-weight: 700; cursor: pointer; }

/* ═══ Results Area ═══ */
.results-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
/* Welcome Search (중앙 큰 검색) */
.welcome-search { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; gap: 30px; }
.ws-header { text-align: center; }
.ws-icon { font-size: 48px; margin-bottom: 12px; opacity: 0.6; }
.ws-header h1 { font-size: 24px; letter-spacing: 8px; color: var(--text-secondary); font-weight: 900; }
.ws-header p { font-size: 13px; color: var(--text-muted); margin-top: 8px; }
.ws-quick-form { width: 100%; max-width: 680px; display: flex; flex-direction: column; gap: 12px; }
.ws-row { display: flex; gap: 10px; }
.ws-row.center { justify-content: center; align-items: center; gap: 16px; }
.ws-field { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.ws-field.narrow { max-width: 200px; }
.ws-field label { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 0.5px; }
.ws-field input { padding: 12px 16px; font-size: 14px; }
.ws-ratings { display: flex; gap: 4px; }
.ws-chip {
  padding: 6px 16px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-pill); color: var(--text-muted); font-size: 11px; font-weight: 800; cursor: pointer;
}
.ws-chip.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.ws-go {
  padding: 12px 36px; background: var(--accent); border: none; border-radius: var(--radius-pill);
  color: #000; font-weight: 900; font-size: 14px; cursor: pointer; letter-spacing: 1px;
  transition: var(--transition);
}
.ws-go:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(250, 204, 21, 0.3); }
.ws-hints { display: flex; gap: 16px; }
.ws-hints span { font-size: 10px; color: var(--text-muted); background: var(--bg-card); padding: 4px 12px; border-radius: 4px; }

.empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 12px; }
.search-spinner {
  width: 40px; height: 40px; border: 3px solid #222; border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.empty h2 { color: var(--text-muted); letter-spacing: 4px; }

/* Toolbar */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px; background: var(--bg-secondary); border-bottom: 1px solid var(--border);
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 6px; }
.tb-btn {
  padding: 5px 10px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-muted); font-size: 10px; font-weight: 700; cursor: pointer;
}
.tb-btn:hover:not(:disabled) { color: var(--text-primary); border-color: var(--text-muted); }
.tb-btn.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.tb-btn.accent { border-color: var(--accent-dim); color: var(--accent); }
.tb-btn:disabled { opacity: 0.3; }
.tb-sep { color: #333; }
.tb-idx { font-family: monospace; font-size: 12px; color: var(--text-secondary); }
.tb-idx b { color: var(--accent); font-size: 16px; }
.result-count { font-size: 10px; color: var(--text-muted); font-weight: 700; }

/* ═══ Single View ═══ */
.single-view { flex: 1; overflow-y: auto; padding: 24px; display: flex; justify-content: center; }
.detail-card { max-width: 700px; width: 100%; display: flex; flex-direction: column; gap: 20px; }
.detail-meta { display: flex; gap: 10px; flex-wrap: wrap; }
.meta-pill {
  padding: 10px 16px; background: rgba(255,255,255,0.02); border: 1px solid var(--border);
  border-radius: 10px; font-size: 14px; font-weight: 800; color: var(--text-primary);
  display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 150px;
}
.meta-pill.artist { color: var(--accent); }
.meta-pill.character { color: #4ade80; }
.meta-label { font-size: 9px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; }

.tag-section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.tag-section label { font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; margin-bottom: 10px; display: block; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 5px; max-height: 300px; overflow-y: auto; }
.tag { padding: 4px 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: #787878; font-size: 10px; }

.detail-actions { display: flex; gap: 10px; }
.primary-btn {
  flex: 2; height: 48px; background: var(--accent); border: none; border-radius: var(--radius-pill);
  color: #000; font-weight: 900; font-size: 13px; letter-spacing: 1px; cursor: pointer;
}
.secondary-btn {
  flex: 1; height: 48px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-pill); color: var(--text-secondary); font-weight: 800; font-size: 11px; cursor: pointer;
}
.primary-btn:hover, .secondary-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }

/* ═══ List View ═══ */
.list-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.list-header {
  display: flex; padding: 8px 16px; background: var(--bg-secondary);
  border-bottom: 1px solid var(--border); font-size: 9px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px;
}
.lh-col.idx { width: 40px; }
.lh-col.char { width: 160px; }
.lh-col.copy { width: 120px; }
.lh-col.artist { width: 100px; }
.lh-col.tags { flex: 1; }
.lh-col.act { width: 50px; text-align: center; }

.list-scroll { flex: 1; overflow-y: auto; }
.list-row {
  display: flex; align-items: center; padding: 7px 16px; font-size: 11px;
  border-bottom: 1px solid rgba(255,255,255,0.02); cursor: pointer; transition: 0.1s;
}
.list-row:hover { background: rgba(255,255,255,0.02); }
.list-row.active { background: var(--accent-dim); }
.lr-col.idx { width: 40px; color: var(--text-muted); font-family: monospace; font-size: 10px; }
.lr-col.char { width: 160px; color: #4ade80; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lr-col.copy { width: 120px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lr-col.artist { width: 100px; color: var(--accent); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lr-col.tags { flex: 1; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }
.lr-col.act { width: 50px; text-align: center; }
.mini-btn { padding: 3px 8px; background: var(--accent); border: none; border-radius: 3px; color: #000; font-size: 9px; font-weight: 800; cursor: pointer; }

.list-pager { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 8px; border-top: 1px solid var(--border); }
.pager-info { font-size: 11px; color: var(--text-muted); font-family: monospace; }

label.danger { color: #f87171; }
</style>
