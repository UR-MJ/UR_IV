<template>
  <div class="search-view">
    <div class="search-form">
      <h3>Danbooru Search</h3>
      <div class="rating-row">
        <label v-for="r in ratings" :key="r.key" class="chk">
          <input type="checkbox" v-model="r.checked" /> {{ r.label }}
        </label>
      </div>
      <div class="field" v-for="f in fields" :key="f.key">
        <label class="flabel">{{ f.label }}</label>
        <input class="finput" v-model="f.include" :placeholder="'포함: ' + f.label" />
        <input class="finput exclude" v-model="f.exclude" :placeholder="'제외'" />
      </div>
      <button class="btn-search" @click="search" :disabled="searching">
        {{ searching ? '검색 중...' : '검색' }}
      </button>
      <div class="status">{{ statusText }}</div>
    </div>
    <div class="results-panel">
      <div v-if="results.length === 0" class="empty">검색 결과가 없습니다</div>
      <div v-for="(r, i) in results" :key="i" class="result-card" @click="applyResult(r)">
        <div class="tag-line"><span class="tag-cat">캐릭터</span> {{ r.character || '-' }}</div>
        <div class="tag-line"><span class="tag-cat">작품</span> {{ r.copyright || '-' }}</div>
        <div class="tag-line"><span class="tag-cat">작가</span> {{ r.artist || '-' }}</div>
        <div class="tag-line general">{{ (r.general || '').substring(0, 120) }}...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const ratings = reactive([
  { key: 'g', label: 'General', checked: true },
  { key: 's', label: 'Sensitive', checked: false },
  { key: 'q', label: 'Questionable', checked: false },
  { key: 'e', label: 'Explicit', checked: false },
])
const fields = reactive([
  { key: 'copyright', label: '작품', include: '', exclude: '' },
  { key: 'character', label: '캐릭터', include: '', exclude: '' },
  { key: 'artist', label: '작가', include: '', exclude: '' },
  { key: 'general', label: '일반 태그', include: '', exclude: '' },
])
const results = ref([])
const searching = ref(false)
const statusText = ref('')

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
          statusText.value = `${data.length}개 결과`
        } else {
          statusText.value = data.error || '검색 실패'
        }
      } catch { statusText.value = '파싱 오류' }
      searching.value = false
    })
  }
}

function applyResult(r) {
  requestAction('apply_search_result', r)
}
</script>

<style scoped>
.search-view { height: 100%; display: flex; }
.search-form {
  width: 320px; padding: 16px; border-right: 1px solid #1A1A1A;
  overflow-y: auto; display: flex; flex-direction: column; gap: 8px;
}
.search-form h3 { color: #E8E8E8; font-size: 14px; margin: 0 0 8px; }
.rating-row { display: flex; gap: 10px; flex-wrap: wrap; }
.chk { color: #B0B0B0; font-size: 12px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.chk input { accent-color: #E2B340; }
.field { display: flex; flex-direction: column; gap: 3px; }
.flabel { color: #585858; font-size: 11px; font-weight: 600; }
.finput {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; outline: none;
}
.finput:focus { background: #1A1A1A; }
.finput.exclude { font-size: 11px; color: #787878; }
.btn-search {
  padding: 10px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer; margin-top: 8px;
}
.btn-search:disabled { opacity: 0.4; cursor: not-allowed; }
.status { color: #585858; font-size: 11px; text-align: center; }
.results-panel { flex: 1; overflow-y: auto; padding: 8px; }
.empty { color: #484848; text-align: center; padding: 60px; font-size: 14px; }
.result-card {
  padding: 10px; border: 1px solid #1A1A1A; border-radius: 6px; margin-bottom: 6px;
  cursor: pointer; transition: border-color 0.15s;
}
.result-card:hover { border-color: #E2B340; }
.tag-line { font-size: 12px; color: #B0B0B0; margin: 2px 0; }
.tag-cat { color: #E2B340; font-weight: 600; font-size: 11px; margin-right: 6px; }
.general { color: #585858; font-size: 11px; margin-top: 4px; }
</style>
