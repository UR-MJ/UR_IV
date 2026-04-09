<template>
  <div class="prompt-panel">
    <!-- 1. FINAL OUTPUT PROMPT -->
    <div class="glass-card highlight">
      <div class="card-header">
        FINAL OUTPUT PROMPT
        <span class="token-info">{{ tokenCount }} tokens</span>
      </div>
      <!-- 블록 모드: 전체 프롬프트 -->
      <div class="tag-block-view" v-if="tagBlockMode">
        <div class="tag-blocks">
          <button v-for="(tb, ti) in totalBlocks" :key="ti"
            class="tag-block" :class="{ disabled: tb.off }"
            @click="toggleTotalBlock(ti)">{{ tb.text }}</button>
        </div>
      </div>
      <textarea v-else ref="totalPromptRef" v-model="widgets.total_prompt_display"
        class="total-prompt auto-grow" placeholder="인물수, 캐릭터, 작품, 작가, 선행, 메인, 후행 순서로 종합됩니다"
        @input="autoGrow($event.target)"></textarea>
      <div class="prompt-actions">
        <button class="optimize-btn" @click="optimizePrompt">🧹 OPTIMIZE</button>
        <span class="opt-result" v-if="optResult">{{ optResult }}</span>
      </div>
      <div class="conflicts" v-if="promptConflicts.length > 0">
        <div v-for="c in promptConflicts" :key="c.group" class="conflict-item">
          ⚠ {{ c.group }}: {{ c.tags.join(', ') }}
        </div>
      </div>
      <div class="neg-section">
        <label class="danger-label">NEGATIVE</label>
        <div class="tag-block-view neg" v-if="tagBlockMode">
          <div class="tag-blocks">
            <button v-for="(tb, ti) in negBlocks" :key="ti"
              class="tag-block neg-block" :class="{ disabled: tb.off }"
              @click="toggleNegBlock(ti)">{{ tb.text }}</button>
          </div>
        </div>
        <textarea v-else ref="negRef" v-model="widgets.neg_prompt_text"
          class="neg-prompt auto-grow" placeholder="Negative prompt..."
          @input="autoGrow($event.target)"></textarea>
      </div>
    </div>

    <!-- 2. CHARACTER & MODEL -->
    <div class="glass-card">
      <div class="card-header">CHARACTER & MODEL</div>
      <div class="input-group">
        <label>Char Count</label>
        <input type="text" v-model="widgets.char_count_input" placeholder="e.g. 1girl, 2girls..." />
      </div>
      <div class="input-group autocomplete-wrap">
        <label>Character</label>
        <div class="row">
          <input type="text" v-model="widgets.character_input" placeholder="e.g. hatsune miku"
            @input="onFieldInput($event, 'character_input')" @keydown="onFieldKey($event, 'character_input')"
            @blur="loadCharTags" />
          <button class="small-btn" @click="requestAction('open_character_preset'); loadCharTags()">PRESET</button>
        </div>
        <!-- 캐릭터 인사이트 카드 -->
        <div class="char-insight" v-if="charInsight.tags.length > 0">
          <div class="insight-header">
            <span class="insight-label">📖 Official Tags</span>
            <button class="insight-apply" @click="applyOfficialTags">APPLY ALL</button>
          </div>
          <div class="insight-tags">
            <button v-for="tag in charInsight.tags" :key="tag" class="char-tag-chip"
              @click="insertCharTag(tag)">{{ tag.replace(/_/g, ' ') }}</button>
          </div>
        </div>
        <div class="ac-popup" v-if="fieldAcTarget === 'character_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item"
            :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'character_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group autocomplete-wrap">
        <label>Copyright</label>
        <input type="text" v-model="widgets.copyright_input" placeholder="Copyright / Series..."
          @input="onFieldInput($event, 'copyright_input')" @keydown="onFieldKey($event, 'copyright_input')" />
        <div class="ac-popup" v-if="fieldAcTarget === 'copyright_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item"
            :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'copyright_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <div class="row label-row">
          <label>Artist</label>
          <button class="lock-btn" :class="{ locked: artistLocked }" @click="toggleArtistLock">
            {{ artistLocked ? '🔒' : '🔓' }}
          </button>
        </div>
        <textarea ref="artistRef" v-model="widgets.artist_input" class="auto-grow" placeholder="Artist tags..."
          @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Checkpoint</label>
        <CustomSelect v-model="widgets.model_combo" :options="modelItems" placeholder="Select model..." />
      </div>
    </div>

    <!-- 3. PROMPT BLOCKS -->
    <details class="glass-card" open>
      <summary class="card-header">PROMPT BLOCKS</summary>
      <div class="input-group autocomplete-wrap">
        <div class="row label-row">
          <label>Main Tags</label>
          <div class="ai-btns">
            <button class="ai-btn" :class="{ active: tagBlockMode }" @click="toggleBlockMode" title="블록/텍스트 전환">{{ tagBlockMode ? '📝' : '🧩' }}</button>
            <button class="ai-btn" @click="ollamaMode = 'expand'; runOllama()" :disabled="ollamaLoading" title="태그 확장">✨</button>
            <button class="ai-btn" @click="showNlInput = !showNlInput" title="자연어→태그">💬</button>
            <button class="ai-btn" @click="ollamaMode = 'suggest'; runOllama()" :disabled="ollamaLoading" title="유사 태그">🔄</button>
          </div>
        </div>
        <!-- 자연어 입력 -->
        <div class="nl-input-row" v-if="showNlInput">
          <input v-model="nlPrompt" placeholder="이미지를 자연어로 설명하세요..." @keydown.enter="ollamaMode = 'nl2tags'; runOllama()" class="nl-input" />
          <button class="ai-btn go" @click="ollamaMode = 'nl2tags'; runOllama()" :disabled="ollamaLoading">GO</button>
        </div>
        <div class="ai-loading" v-if="ollamaLoading">🤖 AI 처리 중...</div>
        <!-- 블록 모드 -->
        <div class="tag-block-view" v-if="tagBlockMode">
          <div class="tag-blocks">
            <button v-for="(tb, ti) in mainTagBlocks" :key="ti"
              class="tag-block" :class="{ disabled: tb.off }"
              @click="toggleTagBlock(ti)"
              @contextmenu.prevent="removeTagBlock(ti)">{{ tb.text }}</button>
          </div>
          <div class="tag-block-add">
            <input v-model="newBlockTag" placeholder="태그 추가..." @keydown.enter="addTagBlock" class="block-input" />
          </div>
        </div>
        <!-- 텍스트 모드 -->
        <textarea v-else ref="mainRef" v-model="widgets.main_prompt_text" class="auto-grow" placeholder="메인 태그..."
          @input="onMainInput($event)" @keydown="onAutoKey($event)" rows="3"></textarea>
        <div class="ac-popup" v-if="fieldAcTarget === 'main_prompt_text' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item"
            :class="{ selected: acIdx === i }" @mousedown.prevent="acceptSuggestion(tag)">{{ tag }}</div>
        </div>
      </div>
      <div class="grid-2">
        <div class="input-group"><label>Prefix</label>
          <textarea ref="prefixRef" v-model="widgets.prefix_prompt_text" class="auto-grow" placeholder="선행..." @input="autoGrow($event.target)"></textarea>
        </div>
        <div class="input-group"><label>Suffix</label>
          <textarea ref="suffixRef" v-model="widgets.suffix_prompt_text" class="auto-grow" placeholder="후행..." @input="autoGrow($event.target)"></textarea>
        </div>
      </div>
      <div class="input-group">
        <label>Exclude (Local)</label>
        <input type="text" v-model="widgets.exclude_prompt_local_input" placeholder="제외 태그..." />
      </div>
    </details>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useWidgetStore, requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'
import CustomSelect from './CustomSelect.vue'

const emit = defineEmits(['toggle-extend'])

const store = useWidgetStore()
const widgets = store.widgets

// artistLocked는 proxy 'btn_lock_artist' 값과 동기화
const artistLocked = computed({
  get: () => widgets.btn_lock_artist === 'true',
  set: (v) => { widgets.btn_lock_artist = v ? 'true' : 'false' }
})
const totalPromptRef = ref(null)
const negRef = ref(null)
const artistRef = ref(null)
const prefixRef = ref(null)
const mainRef = ref(null)
const suffixRef = ref(null)

// ── 태그 블록 모드 ──
const tagBlockMode = ref(false)
const mainTagBlocks = ref([])
const totalBlocks = ref([])
const negBlocks = ref([])
const newBlockTag = ref('')

function parseBlocks(text) {
  return (text || '').split(',').map(t => t.trim()).filter(Boolean).map(t => ({ text: t, off: false }))
}

function toggleBlockMode() {
  tagBlockMode.value = !tagBlockMode.value
  if (tagBlockMode.value) {
    mainTagBlocks.value = parseBlocks(widgets.main_prompt_text)
    totalBlocks.value = parseBlocks(widgets.total_prompt_display)
    negBlocks.value = parseBlocks(widgets.neg_prompt_text)
  } else {
    syncBlocksToText()
  }
}

function toggleTotalBlock(idx) {
  totalBlocks.value[idx].off = !totalBlocks.value[idx].off
  // total은 읽기 전용이므로 off만 시각적 표시
}
function toggleNegBlock(idx) {
  negBlocks.value[idx].off = !negBlocks.value[idx].off
  widgets.neg_prompt_text = negBlocks.value.filter(b => !b.off).map(b => b.text).join(', ')
}

function syncBlocksToText() {
  const active = mainTagBlocks.value.filter(b => !b.off).map(b => b.text)
  widgets.main_prompt_text = active.join(', ')
}

function toggleTagBlock(idx) {
  mainTagBlocks.value[idx].off = !mainTagBlocks.value[idx].off
  syncBlocksToText()
}

function removeTagBlock(idx) {
  mainTagBlocks.value.splice(idx, 1)
  syncBlocksToText()
}

function addTagBlock() {
  const tag = newBlockTag.value.trim()
  if (tag) {
    mainTagBlocks.value.push({ text: tag, off: false })
    newBlockTag.value = ''
    syncBlocksToText()
  }
}

// 텍스트 변경 시 블록 동기화
function syncWatcher(widgetKey, blocksRef) {
  watch(() => widgets[widgetKey], (newVal) => {
    if (tagBlockMode.value && newVal) {
      const tags = newVal.split(',').map(t => t.trim()).filter(Boolean)
      const offSet = new Set(blocksRef.value.filter(b => b.off).map(b => b.text.toLowerCase()))
      blocksRef.value = tags.map(t => ({ text: t, off: offSet.has(t.toLowerCase()) }))
    }
  })
}
syncWatcher('main_prompt_text', mainTagBlocks)
syncWatcher('total_prompt_display', totalBlocks)
syncWatcher('neg_prompt_text', negBlocks)

// 딥 프롬프트 클리너
const optResult = ref('')
const promptConflicts = ref([])
async function optimizePrompt() {
  const backend = await getBackend()
  if (!backend.deepCleanPrompt) return
  const prompt = widgets.total_prompt_display || ''
  backend.deepCleanPrompt(JSON.stringify({ prompt }), (json) => {
    try {
      const d = JSON.parse(json)
      if (d.error) { optResult.value = d.error; return }
      if (d.optimized) widgets.main_prompt_text = d.optimized
      promptConflicts.value = d.conflicts || []
      optResult.value = `${d.removed}개 중복 제거, ${d.tag_count}개 태그`
      setTimeout(() => { optResult.value = '' }, 5000)
      nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
    } catch {}
  })
}

// 캐릭터 인사이트 카드
const charInsight = ref({ tags: [], raw: '' })
async function loadCharTags() {
  const char = widgets.character_input
  if (!char || char.length < 2) { charInsight.value = { tags: [], raw: '' }; return }
  const backend = await getBackend()
  if (backend.getCharacterInsight) {
    backend.getCharacterInsight(char, (json) => {
      try {
        const data = JSON.parse(json)
        charInsight.value = { tags: data.tags || [], raw: data.raw || '' }
      } catch { charInsight.value = { tags: [], raw: '' } }
    })
  }
}
function insertCharTag(tag) {
  const cur = widgets.main_prompt_text || ''
  if (!cur.toLowerCase().includes(tag.toLowerCase())) {
    widgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
  }
}
function applyOfficialTags() {
  if (charInsight.value.raw) {
    widgets.main_prompt_text = charInsight.value.raw
    nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
  }
}

// Ollama
const ollamaLoading = ref(false)
const ollamaMode = ref('expand')
const showNlInput = ref(false)
const nlPrompt = ref('')

async function runOllama() {
  ollamaLoading.value = true
  const backend = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; return }
  const tags = widgets.main_prompt_text || ''
  const extra = { prompt: nlPrompt.value }
  backend.ollamaEnhance(tags, ollamaMode.value, JSON.stringify(extra))
}

// 결과 수신은 onMounted에서

const modelItems = computed(() => store.getProperty('model_combo', 'items') || [])
const samplerItems = computed(() => store.getProperty('sampler_combo', 'items') || [])
const schedulerItems = computed(() => store.getProperty('scheduler_combo', 'items') || [])
const tokenCount = computed(() => {
  const t = widgets.total_prompt_display
  return t ? t.split(',').filter(s => s.trim()).length : 0
})

function toggleArtistLock() {
  artistLocked.value = !artistLocked.value
  requestAction('set_artist_locked', { locked: artistLocked.value })
}

// 태그 자동완성
const acItems = ref([])
const acIdx = ref(0)
const fieldAcTarget = ref('')
let acTimer = null

// 범용 필드 자동완성 (Character, Copyright 등)
function onFieldInput(e, fieldId) {
  fieldAcTarget.value = fieldId
  const text = e.target.value
  const lastComma = text.lastIndexOf(',')
  const prefix = (lastComma >= 0 ? text.substring(lastComma + 1) : text).trim()
  if (prefix.length < 2) { acItems.value = []; return }
  clearTimeout(acTimer)
  acTimer = setTimeout(async () => {
    const backend = await getBackend()
    if (backend.getTagSuggestions) {
      backend.getTagSuggestions(prefix, (json) => {
        try { acItems.value = JSON.parse(json).slice(0, 10); acIdx.value = 0 } catch { acItems.value = [] }
      })
    }
  }, 300)
}
function onFieldKey(e, fieldId) {
  if (fieldAcTarget.value !== fieldId || !acItems.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); acIdx.value = Math.min(acIdx.value + 1, acItems.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); acIdx.value = Math.max(0, acIdx.value - 1) }
  else if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); acceptFieldSuggestion(acItems.value[acIdx.value], fieldId) }
  else if (e.key === 'Escape') { acItems.value = []; fieldAcTarget.value = '' }
}
function acceptFieldSuggestion(tag, fieldId) {
  const text = widgets[fieldId] || ''
  const lastComma = text.lastIndexOf(',')
  widgets[fieldId] = (lastComma >= 0 ? text.substring(0, lastComma + 1) + ' ' : '') + tag + ', '
  acItems.value = []; fieldAcTarget.value = ''
}

function onMainInput(e) {
  autoGrow(e.target)
  fieldAcTarget.value = 'main_prompt_text'
  const text = e.target.value
  const lastComma = text.lastIndexOf(',')
  const prefix = (lastComma >= 0 ? text.substring(lastComma + 1) : text).trim()
  if (prefix.length < 2) { acItems.value = []; return }
  clearTimeout(acTimer)
  acTimer = setTimeout(async () => {
    const backend = await getBackend()
    if (backend.getTagSuggestions) {
      backend.getTagSuggestions(prefix, (json) => {
        try { const tags = JSON.parse(json); acItems.value = Array.isArray(tags) ? tags.slice(0, 10) : []; acIdx.value = 0 } catch { acItems.value = [] }
      })
    }
  }, 300)
}

function onAutoKey(e) {
  if (acItems.value.length === 0) return
  if (e.key === 'ArrowDown') { e.preventDefault(); acIdx.value = Math.min(acIdx.value + 1, acItems.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); acIdx.value = Math.max(acIdx.value - 1, 0) }
  else if (e.key === 'Tab' || e.key === 'Enter') { if (acItems.value.length > 0) { e.preventDefault(); acceptSuggestion(acItems.value[acIdx.value]) } }
  else if (e.key === 'Escape') { acItems.value = [] }
}

function acceptSuggestion(tag) {
  const text = widgets.main_prompt_text || ''
  const lastComma = text.lastIndexOf(',')
  widgets.main_prompt_text = (lastComma >= 0 ? text.substring(0, lastComma + 1) + ' ' : '') + tag + ', '
  acItems.value = []
  nextTick(() => { if (mainRef.value) { mainRef.value.focus(); autoGrow(mainRef.value) } })
}

function autoGrow(el) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function growAll() {
  nextTick(() => {
    ;[totalPromptRef, negRef, artistRef, prefixRef, mainRef, suffixRef].forEach(r => { if (r.value) autoGrow(r.value) })
  })
}

onMounted(() => {
  setTimeout(growAll, 500); setTimeout(growAll, 1500)
  // Ollama 결과 수신
  onBackendEvent('ollamaResult', (json) => {
    ollamaLoading.value = false
    try {
      const d = JSON.parse(json)
      if (d.error) { alert('AI Error: ' + d.error); return }
      if (d.tags) {
        if (ollamaMode.value === 'suggest') {
          widgets.main_prompt_text = d.tags
        } else {
          // expand/nl2tags: 기존 태그에 추가 또는 교체
          widgets.main_prompt_text = d.tags
        }
        showNlInput.value = false; nlPrompt.value = ''
        nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
      }
    } catch {}
  })
})
watch(() => widgets.total_prompt_display, () => nextTick(() => { if (totalPromptRef.value) autoGrow(totalPromptRef.value) }))
watch(() => widgets.neg_prompt_text, () => nextTick(() => { if (negRef.value) autoGrow(negRef.value) }))
watch(() => widgets.artist_input, () => nextTick(() => { if (artistRef.value) autoGrow(artistRef.value) }))
watch(() => widgets.main_prompt_text, () => nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }))
</script>

<style scoped>
.prompt-panel { display: flex; flex-direction: column; gap: 12px; }
.glass-card { background: rgba(20, 20, 20, 0.6); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 14px; }
.glass-card.highlight { border-color: var(--accent-dim); background: rgba(250, 204, 21, 0.02); }
.glass-card:hover { border-color: #333; }
.card-header { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 1.5px; margin-bottom: 12px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; }
summary { list-style: none; outline: none; }
summary::-webkit-details-marker { display: none; }
.input-group { margin-bottom: 10px; }
.row { display: flex; gap: 6px; }
.label-row { align-items: center; margin-bottom: 4px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.small-btn { padding: 0 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.icon-btn { width: 36px; height: 36px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-primary); cursor: pointer; flex-shrink: 0; }
.lock-btn { background: none; border: none; cursor: pointer; font-size: 14px; padding: 0 4px; opacity: 0.5; }
.lock-btn.locked { opacity: 1; }
.total-prompt { min-height: 60px; font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.5; color: var(--accent); border-color: var(--accent-dim); }
.neg-section { margin-top: 8px; }
.danger-label { color: #f87171; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
.neg-prompt { min-height: 30px; color: #f87171; border-color: rgba(248,113,113,0.2); }
.auto-grow { resize: none; overflow: hidden; min-height: 32px; }
.token-info { font-size: 9px; color: var(--text-muted); }
.check-row { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.check-row input { accent-color: var(--accent); }
label.danger { color: #f87171; }
input[type="number"] { -moz-appearance: textfield; }
input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }

.prompt-actions { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.optimize-btn { padding: 3px 10px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 9px; font-weight: 700; cursor: pointer; }
.optimize-btn:hover { border-color: var(--accent); color: var(--accent); }
.opt-result { font-size: 9px; color: #4ade80; }
.conflicts { margin-top: 4px; }
.conflict-item { font-size: 9px; color: #fbbf24; padding: 2px 0; }

.char-insight { margin-top: 6px; background: rgba(45,212,191,0.03); border: 1px solid rgba(45,212,191,0.1); border-radius: 6px; padding: 8px; }
.insight-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.insight-label { font-size: 9px; font-weight: 800; color: #2dd4bf; }
.insight-apply { padding: 2px 8px; background: #2dd4bf; border: none; border-radius: 3px; color: #000; font-size: 9px; font-weight: 800; cursor: pointer; }
.insight-tags { display: flex; flex-wrap: wrap; gap: 3px; max-height: 80px; overflow-y: auto; }
.char-tag-chip { padding: 2px 8px; background: rgba(45,212,191,0.08); border: 1px solid rgba(45,212,191,0.2); border-radius: 4px; color: #2dd4bf; font-size: 9px; cursor: pointer; }
.char-tag-chip:hover { background: rgba(45,212,191,0.15); border-color: #2dd4bf; }

/* 태그 블록 모드 */
.tag-block-view { border: 1px solid var(--border); border-radius: var(--radius-base); padding: 8px; background: var(--bg-input); }
.tag-blocks { display: flex; flex-wrap: wrap; gap: 4px; min-height: 30px; }
.tag-block {
  padding: 4px 10px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: 11px; cursor: pointer;
  transition: all 0.15s; user-select: none;
}
.tag-block:hover { border-color: var(--accent); }
.tag-block.disabled { opacity: 0.3; text-decoration: line-through; color: var(--text-muted); background: transparent; }
.tag-block.neg-block { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
.tag-block-view.neg { border-color: rgba(248,113,113,0.15); }
.tag-block-add { margin-top: 6px; }
.block-input { width: 100%; padding: 5px 8px; font-size: 10px; background: var(--bg-card); border: 1px dashed var(--border); border-radius: 4px; color: var(--text-primary); }

.ai-btns { display: flex; gap: 3px; }
.ai-btn { width: 26px; height: 22px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.ai-btn:hover { border-color: var(--accent); color: var(--accent); }
.ai-btn.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.ai-btn:disabled { opacity: 0.3; }
.ai-btn.go { width: auto; padding: 0 8px; background: var(--accent); color: #000; border: none; font-weight: 700; font-size: 10px; }
.nl-input-row { display: flex; gap: 4px; margin-bottom: 6px; }
.nl-input { flex: 1; padding: 6px 10px; font-size: 11px; }
.ai-loading { font-size: 10px; color: var(--accent); margin-bottom: 4px; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

.autocomplete-wrap { position: relative; }
.ac-popup { position: absolute; left: 0; right: 0; top: 100%; z-index: 100; background: #1A1A1A; border: 1px solid var(--border); border-radius: 6px; max-height: 200px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
.ac-item { padding: 6px 12px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.03); }
.ac-item:hover, .ac-item.selected { background: var(--accent-dim); color: var(--accent); }
</style>
