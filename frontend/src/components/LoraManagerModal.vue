<template>
  <div class="lm-overlay" @click.self="close">
    <div class="lm-modal">
      <div class="lm-header">
        <div>
          <h3>LoRA 매니저</h3>
          <span class="lm-sub">설치된 LoRA를 검색해서 스택에 추가합니다</span>
        </div>
        <button class="lm-close" @click="close">✕</button>
      </div>

      <div class="lm-searchbar">
        <input ref="searchEl" v-model="query" class="lm-search" placeholder="LoRA 이름 검색..." />
        <button class="lm-refresh" @click="load('force')" :disabled="loading" title="목록 다시 스캔">{{ loading ? '…' : '🔄' }}</button>
      </div>

      <div class="lm-list">
        <div v-if="loading" class="lm-empty">로딩 중...</div>
        <div v-else-if="!filtered.length" class="lm-empty">
          {{ loras.length ? '검색 결과 없음' : '설치된 LoRA가 없습니다 (백엔드 연결 확인)' }}
        </div>
        <div v-for="l in filtered" :key="l.name" class="lm-item">
          <div class="lm-item-main">
            <div class="lm-name">{{ l.name }}</div>
            <div class="lm-triggers" v-if="l.triggerWords && l.triggerWords.length">
              <span v-for="tw in l.triggerWords.slice(0, 8)" :key="tw" class="lm-tw">{{ tw }}</span>
            </div>
          </div>
          <input type="number" v-model.number="l._w" step="0.05" min="-2" max="3" class="lm-weight" title="가중치" />
          <button class="lm-add" @click="add(l)">+ 추가</button>
        </div>
      </div>

      <!-- 일괄 붙여넣기 (<lora:name:weight> 텍스트) -->
      <details class="lm-batch">
        <summary>일괄 붙여넣기 (&lt;lora:이름:가중치&gt;)</summary>
        <textarea v-model="batchText" class="lm-batch-text" rows="3"
          placeholder="<lora:my_style:0.8>, <lora:char_a:1.0> ..."></textarea>
        <button class="lm-batch-btn" @click="applyBatch">붙여넣은 LoRA 추가</button>
      </details>

      <div class="lm-footer">
        <span class="lm-count">{{ filtered.length }} / {{ loras.length }} LoRA</span>
        <div class="lm-foot-spacer"></div>
        <button class="lm-done" @click="close">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getBackend } from '../bridge.js'

const emit = defineEmits(['close', 'add'])

const loras = ref([])
const query = ref('')
const loading = ref(false)
const batchText = ref('')
const searchEl = ref(null)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? loras.value.filter(l => l.name.toLowerCase().includes(q)) : loras.value
})

async function load(mode = '') {
  loading.value = true
  const backend = await getBackend()
  if (!backend || !backend.getLoras) { loading.value = false; return }
  backend.getLoras(mode, (json) => {
    loading.value = false
    try {
      const d = JSON.parse(json)
      if (Array.isArray(d)) loras.value = d.map(l => ({ ...l, _w: 1.0 }))
    } catch {}
  })
}

function add(l) {
  emit('add', { name: l.name, weight: (typeof l._w === 'number' ? l._w : 1.0), triggerWords: l.triggerWords || [] })
}

function applyBatch() {
  const re = /<lora:([^:>]+):([-\d.]+)>/gi
  let m, n = 0
  while ((m = re.exec(batchText.value)) !== null) {
    const name = m[1].trim()
    const w = parseFloat(m[2]) || 1.0
    if (name) { emit('add', { name, weight: w, triggerWords: [] }); n++ }
  }
  if (n) batchText.value = ''
}

function close() { emit('close') }
function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close() } }

onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  load()
  if (searchEl.value) searchEl.value.focus()
})
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
</script>

<style scoped>
.lm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 2200; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.lm-modal { width: min(840px, 94vw); height: min(840px, 92vh); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-card); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.lm-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.lm-header h3 { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.lm-sub { font-size: 11px; color: var(--text-muted); }
.lm-close { width: 30px; height: 30px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.lm-close:hover { color: var(--text-primary); border-color: var(--accent); }
.lm-searchbar { display: flex; gap: 8px; padding: 12px 20px; }
.lm-search { flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-base); padding: 9px 12px; color: var(--text-primary); font-size: 13px; }
.lm-search:focus { outline: none; border-color: var(--accent); }
.lm-refresh { width: 38px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.lm-refresh:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.lm-list { flex: 1; overflow-y: auto; padding: 4px 16px; }
.lm-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
.lm-item { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-bottom: 1px solid var(--border); }
.lm-item-main { flex: 1; min-width: 0; }
.lm-name { font-size: 12px; font-weight: 700; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lm-triggers { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.lm-tw { font-size: 9px; padding: 1px 6px; border-radius: 7px; background: var(--bg-button); color: var(--text-muted); }
.lm-weight { width: 64px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 5px 6px; color: var(--text-primary); font-size: 12px; text-align: center; }
.lm-add { background: var(--accent); color: #000; border: none; border-radius: 6px; font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; white-space: nowrap; }
.lm-add:hover { background: var(--accent-hover); }
.lm-batch { margin: 4px 20px; border: 1px solid var(--border); border-radius: var(--radius-base); }
.lm-batch > summary { padding: 8px 12px; font-size: 11px; font-weight: 700; color: var(--text-secondary); cursor: pointer; }
.lm-batch-text { width: calc(100% - 24px); margin: 0 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; color: var(--text-primary); font-size: 11px; resize: vertical; }
.lm-batch-btn { margin: 8px 12px; background: var(--bg-button); border: 1px solid var(--accent); border-radius: 6px; color: var(--accent); font-size: 11px; font-weight: 700; padding: 5px 12px; cursor: pointer; }
.lm-footer { display: flex; align-items: center; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
.lm-count { font-size: 11px; color: var(--text-muted); }
.lm-foot-spacer { flex: 1; }
.lm-done { background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 12px; font-weight: 700; padding: 9px 16px; cursor: pointer; }
.lm-done:hover { color: var(--text-primary); border-color: var(--accent); }
</style>
