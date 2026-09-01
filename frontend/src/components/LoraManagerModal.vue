<template>
  <div class="lm-overlay" @mousedown.self="close">
    <div class="lm-modal">
      <div class="lm-header">
        <div>
          <h3>LoRA 매니저</h3>
          <span class="lm-sub">
            {{ extMode ? 'sam-extra 임베드 매니저 (civitai 다운로드 · 메타데이터 · 레시피)'
                       : '설치된 LoRA를 검색해서 스택에 추가합니다' }}
          </span>
        </div>
        <div class="lm-head-actions">
          <button class="lm-modetab" :class="{ active: !extMode }" @click="extMode = false">간편</button>
          <button class="lm-modetab" :class="{ active: extMode }" @click="openExtManager">확장 매니저</button>
          <button class="lm-close" @click="close"><Icon name="close" /></button>
        </div>
      </div>

      <!-- sam-extra 임베드 LoRA Manager (워크플로 4) -->
      <div v-if="extMode" class="lm-ext">
        <div v-if="extLoading" class="lm-empty">LoRA Manager 서버를 여는 중…</div>
        <div v-else-if="extError" class="lm-empty lm-error">
          {{ extError }}
          <button class="lm-refresh mt-8" @click="openExtManager">다시 시도</button>
        </div>
        <iframe v-else-if="extUrl" :src="extUrl" class="lm-iframe"
          referrerpolicy="no-referrer" />
      </div>

      <template v-else>
      <div class="lm-searchbar">
        <input ref="searchEl" v-model="query" class="lm-search" placeholder="LoRA 이름 검색..." />
        <button class="lm-refresh" @click="load('force')" :disabled="loading" title="목록 다시 스캔"><Icon v-if="!loading" name="refresh" /><template v-else>…</template></button>
      </div>

      <div class="lm-list">
        <div v-if="loading" class="lm-empty">로딩 중...</div>
        <div v-else-if="!filtered.length" class="lm-empty">
          {{ loras.length ? '검색 결과 없음' : '설치된 LoRA가 없습니다 (백엔드 연결 확인)' }}
        </div>
        <div v-if="unavailableCount" class="lm-availability-note">
          현재 실행 백엔드에서 보이지 않는 {{ unavailableCount }}개 항목은 확인만 가능하며 추가할 수 없습니다.
        </div>
        <section v-for="section in filteredSections" :key="section.key" class="lm-section">
          <header class="lm-section-header">
            <div>
              <strong>{{ section.label }}</strong>
              <span>{{ section.description }}</span>
            </div>
            <span class="lm-section-count">{{ section.items.length }}</span>
          </header>
          <div v-for="l in section.items" :key="l.id || `${l.source || 'main'}:${l.runtimeName || l.name}`"
            class="lm-item" :class="{ unavailable: l.backendAvailable === false }">
            <div class="lm-item-main">
              <div class="lm-name-row">
                <div class="lm-name" :title="l.runtimeName || l.name">{{ l.label || l.name }}</div>
                <span v-if="isPrimaryLora(l)" class="lm-source-badge main">MAIN</span>
                <span v-if="l.source" class="lm-source-badge">{{ l.sourceName || sourceLabel(l.source) }}</span>
                <span v-if="l.group && !isPrimaryLora(l)" class="lm-source-badge secondary">{{ groupLabel(l.group) }}</span>
                <span v-if="l.nameConflict" class="lm-source-badge conflict">NAME CONFLICT</span>
              </div>
              <div v-if="l.backendAvailable === false" class="lm-unavailable">
                현재 실행 백엔드에서는 이 LoRA 경로를 사용할 수 없습니다.
              </div>
              <div class="lm-triggers" v-if="l.triggerWords && l.triggerWords.length">
                <span v-for="tw in l.triggerWords.slice(0, 8)" :key="tw" class="lm-tw">{{ tw }}</span>
              </div>
            </div>
            <input type="number" v-model.number="l._w" step="0.05" min="-2" max="3" class="lm-weight"
              title="가중치" :disabled="l.backendAvailable === false" />
            <button class="lm-add" :disabled="l.backendAvailable === false"
              :title="l.backendAvailable === false ? '현재 백엔드에서 사용할 수 없습니다' : `${l.runtimeName || l.name} 추가`"
              @click="add(l)">+ 추가</button>
          </div>
        </section>
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
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'

interface LoraItem {
  name: string
  label?: string
  triggerWords: string[]
  source?: string
  sourceName?: string
  group?: string
  primary?: boolean
  backendAvailable?: boolean
  runtimeName?: string
  nameConflict?: boolean
  _w?: number
  [k: string]: any
}

interface LoraSection {
  key: string
  label: string
  description: string
  items: LoraItem[]
}

const emit = defineEmits<{
  close: []
  add: [payload: { name: string; weight: number; triggerWords: string[] }]
}>()

const loras = ref<LoraItem[]>([])
const query = ref('')
const loading = ref(false)
const batchText = ref('')
const searchEl = ref<HTMLInputElement | null>(null)

// ── sam-extra 임베드 LoRA Manager (워크플로 4) ──────────────────────────────
// 확장이 Forge FastAPI에 등록한 /sam3-lora/spawn 이 aiohttp 서버를 lazy spawn 하고
// URL을 돌려준다. 그 URL을 iframe으로 띄우면 civitai 다운로드·메타데이터 편집·
// 트리거워드·레시피가 그대로 들어온다 — 앱에서 새로 만들 게 없다.
const extMode = ref(false)
const extUrl = ref('')
const extLoading = ref(false)
const extError = ref('')
let disconnectExtUrlReady: (() => void) | null = null

async function openExtManager() {
  extMode.value = true
  if (extUrl.value) return          // 이미 열어둔 서버 재사용
  extLoading.value = true
  extError.value = ''
  try {
    const backend: any = await getBackend()
    if (!backend?.requestLoraManagerUrl) {
      extError.value = 'LoRA Manager 임베드를 지원하지 않는 백엔드입니다'
      extLoading.value = false
      return
    }
    backend.requestLoraManagerUrl()
  } catch (e) {
    extError.value = String(e)
    extLoading.value = false
  }
}

function onExtUrlReady(json: string) {
  extLoading.value = false
  try {
    const r = JSON.parse(json)
    if (r.url) { extUrl.value = r.url; extError.value = '' }
    else extError.value = r.message || 'LoRA Manager를 열 수 없습니다'
  } catch {
    extError.value = 'LoRA Manager 응답을 해석하지 못했습니다'
  }
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? loras.value.filter(l => [l.label, l.name, l.runtimeName, l.source, l.sourceName, l.group, ...(l.triggerWords || [])]
    .some(value => String(value || '').toLowerCase().includes(q))) : loras.value
})

function isPrimaryLora(lora: LoraItem) {
  const group = String(lora.group || '').toLowerCase()
  return Boolean(lora.primary || ['main', 'primary', 'shared'].includes(group))
}

function sourceLabel(source: string) {
  const normalized = source.toLowerCase()
  if (normalized === 'forge') return 'FORGE NEO'
  if (normalized === 'comfyui' || normalized === 'comfy') return 'COMFYUI'
  return source.toUpperCase()
}

function groupLabel(group: string) {
  const normalized = group.toLowerCase().replace(/[_-]+/g, ' ')
  if (normalized.includes('unique') || normalized.includes('secondary')) return 'UNIQUE'
  return group.toUpperCase()
}

const filteredSections = computed<LoraSection[]>(() => {
  const main = filtered.value.filter(isPrimaryLora)
  const secondary = filtered.value.filter(lora => !isPrimaryLora(lora))
  const sections: LoraSection[] = []
  if (main.length) {
    sections.push({
      key: 'main', label: 'MAIN LIBRARY',
      description: '기본 모델 라이브러리에서 공유되는 LoRA', items: main,
    })
  }
  const bySource = new Map<string, LoraItem[]>()
  for (const lora of secondary) {
    const source = String(lora.source || lora.group || 'secondary')
    const entries = bySource.get(source) || []
    entries.push(lora)
    bySource.set(source, entries)
  }
  for (const [source, items] of bySource) {
    const displaySource = items[0]?.sourceName || sourceLabel(source)
    sections.push({
      key: `secondary:${source}`, label: `${displaySource} UNIQUE`,
      description: '메인 라이브러리와 중복되지 않는 백엔드 전용 LoRA', items,
    })
  }
  return sections
})

const unavailableCount = computed(() => filtered.value.filter(lora => lora.backendAvailable === false).length)

async function load(mode = '') {
  loading.value = true
  const backend: any = await getBackend()   // QWebChannel 백엔드 — 동적 타입
  if (!backend || !backend.getLoras) { loading.value = false; return }
  backend.getLoras(mode, (json: string) => {
    loading.value = false
    try {
      const d = JSON.parse(json)
      if (Array.isArray(d)) loras.value = d.map((l: any) => ({ ...l, _w: 1.0 }))
    } catch {}
  })
}

function add(l: LoraItem) {
  if (l.backendAvailable === false) return
  emit('add', { name: l.runtimeName || l.name, weight: (typeof l._w === 'number' ? l._w : 1.0), triggerWords: l.triggerWords || [] })
}

function applyBatch() {
  const re = /<lora:([^:>]+):([-\d.]+)>/gi
  let m: RegExpExecArray | null = null
  let n = 0
  while ((m = re.exec(batchText.value)) !== null) {
    const name = m[1].trim()
    const w = parseFloat(m[2]) || 1.0
    if (name) { emit('add', { name, weight: w, triggerWords: [] }); n++ }
  }
  if (n) batchText.value = ''
}

function close() { emit('close') }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') { e.stopPropagation(); close() } }

onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  disconnectExtUrlReady = onBackendEvent('loraManagerUrlReady', onExtUrlReady)
  load()
  if (searchEl.value) searchEl.value.focus()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey, true)
  disconnectExtUrlReady?.()
  disconnectExtUrlReady = null
})
</script>

<style scoped>
.lm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 3200; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.lm-modal { width: min(840px, 94vw); height: min(840px, 92vh); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-card); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.lm-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.lm-header h3 { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.lm-sub { font-size: 11px; color: var(--text-muted); }
.lm-close { width: 30px; height: 30px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.lm-close:hover { color: var(--text-primary); border-color: var(--accent); }
.lm-head-actions { display: flex; align-items: center; gap: 6px; }
.lm-modetab {
  height: 30px; padding: 0 12px; font-size: var(--fs-label); font-weight: 800;
  background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-muted); cursor: pointer;
}
.lm-modetab:hover { color: var(--text-primary); }
.lm-modetab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.lm-ext { flex: 1; display: flex; min-height: 0; }
.lm-iframe { flex: 1; width: 100%; height: 100%; border: none; background: #fff; }
.lm-error { color: #f87171; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.mt-8 { margin-top: 8px; }
.lm-searchbar { display: flex; gap: 8px; padding: 12px 20px; }
.lm-search { flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-base); padding: 9px 12px; color: var(--text-primary); font-size: 13px; }
.lm-search:focus { outline: none; border-color: var(--accent); }
.lm-refresh { width: 38px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.lm-refresh:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.lm-list { flex: 1; overflow-y: auto; padding: 4px 16px; }
.lm-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
.lm-availability-note {
  margin: 4px 4px 10px; padding: 8px 10px; border: 1px solid rgba(251,191,36,.28);
  border-radius: 7px; background: rgba(251,191,36,.06); color: #d4b45f; font-size: var(--fs-label);
}
.lm-section { margin-bottom: 12px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.lm-section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 9px 11px; background: var(--bg-input); border-bottom: 1px solid var(--border);
}
.lm-section-header > div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.lm-section-header strong { color: var(--text-primary); font-size: var(--fs-label); letter-spacing: .8px; }
.lm-section-header span { color: var(--text-muted); font-size: var(--fs-label); }
.lm-section-count {
  flex-shrink: 0; min-width: 20px; padding: 2px 6px; border-radius: 8px;
  background: var(--bg-button); color: var(--text-secondary) !important; text-align: center; font-weight: 800;
}
.lm-item { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-bottom: 1px solid var(--border); }
.lm-item:last-child { border-bottom: none; }
.lm-item.unavailable { opacity: .58; }
.lm-item-main { flex: 1; min-width: 0; }
.lm-name-row { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; min-width: 0; }
.lm-name { min-width: 0; flex: 1; font-size: 12px; font-weight: 700; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lm-source-badge {
  flex-shrink: 0; padding: 2px 5px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-input); color: var(--text-muted); font-size: 7px; font-weight: 900; letter-spacing: .4px;
}
.lm-source-badge.main { border-color: rgba(96,165,250,.35); background: rgba(96,165,250,.1); color: #60a5fa; }
.lm-source-badge.secondary { border-color: rgba(34,211,238,.3); background: rgba(34,211,238,.08); color: #67e8f9; }
.lm-source-badge.conflict { border-color: rgba(248,113,113,.35); background: rgba(248,113,113,.1); color: #f87171; }
.lm-unavailable { margin-top: 3px; color: #d4b45f; font-size: var(--fs-label); }
.lm-triggers { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.lm-tw { font-size: var(--fs-label); padding: 1px 6px; border-radius: 7px; background: var(--bg-button); color: var(--text-muted); }
.lm-weight { width: 64px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 5px 6px; color: var(--text-primary); font-size: 12px; text-align: center; }
.lm-add { background: var(--accent); color: #000; border: none; border-radius: 6px; font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; white-space: nowrap; }
.lm-add:hover { background: var(--accent-hover); }
.lm-add:disabled, .lm-weight:disabled { opacity: .5; cursor: not-allowed; }
.lm-batch { margin: 4px 20px; border: 1px solid var(--border); border-radius: var(--radius-base); }
.lm-batch > summary { padding: 8px 12px; font-size: 11px; font-weight: 700; color: var(--text-secondary); cursor: pointer; }
.lm-batch-text { width: calc(100% - 24px); margin: 0 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; color: var(--text-primary); font-size: 11px; resize: vertical; }
.lm-batch-btn { margin: 8px 12px; background: var(--bg-button); border: 1px solid var(--accent); border-radius: 6px; color: var(--accent); font-size: 11px; font-weight: 700; padding: 5px 12px; cursor: pointer; }
.lm-footer { display: flex; align-items: center; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
.lm-count { font-size: 11px; color: var(--text-muted); }
.lm-foot-spacer { flex: 1; }
.lm-done { background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 12px; font-weight: 700; padding: 9px 16px; cursor: pointer; }
.lm-done:hover { color: var(--text-primary); border-color: var(--accent); }
@media (max-width: 520px) {
  .lm-header { align-items: flex-start; padding: 12px; }
  .lm-head-actions { flex-wrap: wrap; justify-content: flex-end; }
  .lm-searchbar, .lm-footer { padding-left: 12px; padding-right: 12px; }
  .lm-list { padding-left: 8px; padding-right: 8px; }
  .lm-item { align-items: flex-start; flex-wrap: wrap; gap: 7px; }
  .lm-item-main { flex: 0 0 100%; }
  .lm-weight { margin-left: auto; }
  .lm-batch { margin-left: 12px; margin-right: 12px; }
}
</style>
