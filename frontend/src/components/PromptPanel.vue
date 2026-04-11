<template>
  <div class="prompt-panel">
    <!-- 1. FINAL OUTPUT PROMPT -->
    <div class="glass-card highlight">
      <div class="card-header">
        FINAL OUTPUT PROMPT
        <span class="token-info">{{ tokenCount }} tokens</span>
      </div>
      <TagBlockField v-if="tagBlockMode" :model-value="widgets.total_prompt_display" :color-fn="blockColorClass" placeholder="" @open-wildcard="(n) => emit('open-wildcard', n)" />
      <textarea v-else ref="totalPromptRef" v-model="widgets.total_prompt_display"
        class="total-prompt auto-grow" placeholder="최종 프롬프트" @input="autoGrow($event.target)"></textarea>
      <div class="prompt-actions">
        <button class="optimize-btn" @click="optimizePrompt">🧹 OPTIMIZE</button>
        <span class="opt-result" v-if="optResult">{{ optResult }}</span>
      </div>
      <div class="conflicts" v-if="promptConflicts.length > 0">
        <div v-for="c in promptConflicts" :key="c.group" class="conflict-item">⚠ {{ c.group }}: {{ c.tags.join(', ') }}</div>
      </div>
      <details class="neg-section">
        <summary class="danger-label neg-toggle">NEGATIVE ▾</summary>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.neg_prompt_text" :color-fn="() => 'neg'" class="neg" placeholder="네거티브 추가..." />
        <textarea v-else ref="negRef" v-model="widgets.neg_prompt_text" class="neg-prompt auto-grow" placeholder="Negative prompt..." @input="autoGrow($event.target)"></textarea>
      </details>
    </div>

    <!-- 2. CHARACTER & MODEL -->
    <div class="glass-card">
      <div class="card-header">CHARACTER & MODEL</div>
      <div class="input-group">
        <label>Char Count</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.char_count_input" :color-fn="() => 'bc-count'" placeholder="인물수..." />
        <input v-else type="text" v-model="widgets.char_count_input" placeholder="e.g. 1girl, 2girls..." />
      </div>
      <div class="input-group autocomplete-wrap">
        <div class="row label-row">
          <label>Character</label>
          <button class="small-btn" @click="requestAction('open_character_preset'); loadCharTags()">PRESET</button>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.character_input" :color-fn="() => 'bc-count'" placeholder="캐릭터..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <input v-else type="text" v-model="widgets.character_input" placeholder="e.g. hatsune miku"
          @input="onFieldInput($event, 'character_input')" @keydown="onFieldKey($event, 'character_input')" @blur="loadCharTags" />
        <div class="char-insight" v-if="charInsight.tags.length > 0">
          <div class="insight-header">
            <span class="insight-label">📖 Official Tags</span>
            <button class="insight-apply" @click="applyOfficialTags">APPLY ALL</button>
          </div>
          <div class="insight-tags">
            <button v-for="tag in charInsight.tags" :key="tag" class="char-tag-chip" @click="insertCharTag(tag)">{{ tag.replace(/_/g, ' ') }}</button>
          </div>
        </div>
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'character_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'character_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group autocomplete-wrap">
        <label>Copyright</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.copyright_input" :color-fn="() => ''" placeholder="작품..." />
        <input v-else type="text" v-model="widgets.copyright_input" placeholder="Copyright / Series..."
          @input="onFieldInput($event, 'copyright_input')" @keydown="onFieldKey($event, 'copyright_input')" />
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'copyright_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'copyright_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <div class="row label-row">
          <label>Artist</label>
          <button class="lock-btn" :class="{ locked: artistLocked }" @click="toggleArtistLock">{{ artistLocked ? '🔒' : '🔓' }}</button>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.artist_input" :color-fn="() => ''" placeholder="작가..." />
        <textarea v-else ref="artistRef" v-model="widgets.artist_input" class="auto-grow" placeholder="Artist tags..." @input="autoGrow($event.target)"></textarea>
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
            <button class="ai-btn" @click="ollamaMode = 'expand'; runOllama()" :disabled="ollamaLoading" title="태그 확장">✨</button>
            <button class="ai-btn" @click="showNlInput = !showNlInput" title="자연어→태그">💬</button>
            <button class="ai-btn" @click="ollamaMode = 'suggest'; runOllama()" :disabled="ollamaLoading" title="유사 태그">🔄</button>
          </div>
        </div>
        <div class="nl-input-row" v-if="showNlInput">
          <input v-model="nlPrompt" placeholder="이미지를 자연어로 설명하세요..." @keydown.enter="ollamaMode = 'nl2tags'; runOllama()" class="nl-input" />
          <button class="ai-btn go" @click="ollamaMode = 'nl2tags'; runOllama()" :disabled="ollamaLoading">GO</button>
        </div>
        <div class="ai-loading" v-if="ollamaLoading">🤖 AI 처리 중...</div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.main_prompt_text" :color-fn="blockColorClass" placeholder="태그 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="mainRef" v-model="widgets.main_prompt_text" class="auto-grow" placeholder="메인 태그..."
          @input="onMainInput($event)" @keydown="onAutoKey($event)" rows="3"></textarea>
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'main_prompt_text' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptSuggestion(tag)">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <label>Prefix</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.prefix_prompt_text" :color-fn="blockColorClass" placeholder="선행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="prefixRef" v-model="widgets.prefix_prompt_text" class="auto-grow" placeholder="선행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Suffix</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.suffix_prompt_text" :color-fn="blockColorClass" placeholder="후행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="suffixRef" v-model="widgets.suffix_prompt_text" class="auto-grow" placeholder="후행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Exclude (Local)</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.exclude_prompt_local_input" :color-fn="() => 'bc-nsfw'" placeholder="제외 추가..." />
        <input v-else type="text" v-model="widgets.exclude_prompt_local_input" placeholder="제외 태그..." />
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useWidgetStore, requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'
import CustomSelect from './CustomSelect.vue'
import TagBlockField from './TagBlockField.vue'

const emit = defineEmits(['toggle-extend', 'open-wildcard'])
const store = useWidgetStore()
const widgets = store.widgets

// 블록 모드 (Settings에서 제어)
const tagBlockMode = ref(window.localStorage.getItem('tagBlockMode') === 'true')
watch(tagBlockMode, v => window.localStorage.setItem('tagBlockMode', String(v)))

// 같은 SPA 내 변경 감지 (keep-alive 환경)
let _blockModeTimer = null
onMounted(() => {
  _blockModeTimer = setInterval(() => {
    const stored = window.localStorage.getItem('tagBlockMode') === 'true'
    if (stored !== tagBlockMode.value) {
      tagBlockMode.value = stored
      console.log('[PromptPanel] Block mode synced:', stored)
    }
  }, 300)
})
onUnmounted(() => { if (_blockModeTimer) clearInterval(_blockModeTimer) })

const artistLocked = computed({
  get: () => widgets.btn_lock_artist === 'true',
  set: (v) => { widgets.btn_lock_artist = v ? 'true' : 'false' }
})
function toggleArtistLock() { artistLocked.value = !artistLocked.value; requestAction('set_artist_locked', { locked: artistLocked.value }) }

const totalPromptRef = ref(null)
const negRef = ref(null)
const artistRef = ref(null)
const prefixRef = ref(null)
const mainRef = ref(null)
const suffixRef = ref(null)

const modelItems = computed(() => store.getProperty('model_combo', 'items') || [])
const tokenCount = computed(() => { const t = widgets.total_prompt_display; return t ? t.split(',').filter(s => s.trim()).length : 0 })

// 블록 색상 분류
const countPattern = /^(\d+)?(girl|boy|other)s?$|^solo$|^multiple_/
const blockColorCache = ref({})

function blockColorClass(text) {
  if (text.includes('__') && /__[^_]+__/.test(text)) return 'wc-block'
  let t = text.trim().toLowerCase().replace(/ /g, '_').replace(/^\(+/, '').replace(/[\):.\d]+$/, '').trim()
  if (countPattern.test(t)) return 'bc-count'
  return blockColorCache.value[t] ? 'bc-' + blockColorCache.value[t] : ''
}

// 태그 분류 요청
async function classifyVisibleTags() {
  const allTags = new Set()
  for (const key of ['main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text', 'total_prompt_display']) {
    const text = widgets[key] || ''
    for (const t of text.split(',')) {
      let tag = t.trim().replace(/ /g, '_').replace(/^\(+/, '').replace(/[\):.\d]+$/, '').trim()
      if (tag && !countPattern.test(tag.toLowerCase()) && !blockColorCache.value[tag.toLowerCase()] && !/__[^_]+__/.test(tag)) allTags.add(tag)
    }
  }
  if (allTags.size === 0) return
  const backend = await getBackend()
  if (backend.classifyTags) {
    backend.classifyTags(JSON.stringify([...allTags]), (json) => {
      try {
        const r = JSON.parse(json)
        if (!r.error) {
          const m = { sexual:'nsfw', body_parts:'body', clothing:'clothing', pose:'action', expression:'expression', background:'bg', composition:'bg', effect:'effect', objects:'objects', color:'color', character_trait:'trait' }
          for (const [tag, cat] of Object.entries(r)) blockColorCache.value[tag.toLowerCase()] = m[cat] || ''
        }
      } catch {}
    })
  }
}
watch(tagBlockMode, v => { if (v) setTimeout(classifyVisibleTags, 200) })

// 딥 프롬프트 클리너
const optResult = ref('')
const promptConflicts = ref([])
async function optimizePrompt() {
  const backend = await getBackend()
  if (!backend.deepCleanPrompt) return
  backend.deepCleanPrompt(JSON.stringify({ prompt: widgets.total_prompt_display || '' }), (json) => {
    try {
      const d = JSON.parse(json)
      if (d.error) { optResult.value = d.error; return }
      if (d.optimized) widgets.main_prompt_text = d.optimized
      promptConflicts.value = d.conflicts || []
      optResult.value = `${d.removed}개 중복 제거, ${d.tag_count}개 태그`
      setTimeout(() => { optResult.value = '' }, 5000)
    } catch {}
  })
}

// 캐릭터 인사이트
const charInsight = ref({ tags: [], raw: '' })
async function loadCharTags() {
  const char = widgets.character_input
  if (!char || char.length < 2) { charInsight.value = { tags: [], raw: '' }; return }
  const backend = await getBackend()
  if (backend.getCharacterInsight) {
    backend.getCharacterInsight(char, (json) => {
      try { const d = JSON.parse(json); charInsight.value = { tags: d.tags || [], raw: d.raw || '' } } catch { charInsight.value = { tags: [], raw: '' } }
    })
  }
}
function insertCharTag(tag) {
  const cur = widgets.main_prompt_text || ''
  if (!cur.toLowerCase().includes(tag.toLowerCase())) widgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
}
function applyOfficialTags() { if (charInsight.value.raw) { widgets.main_prompt_text = charInsight.value.raw; nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }) } }

// Ollama
const ollamaLoading = ref(false)
const ollamaMode = ref('expand')
const showNlInput = ref(false)
const nlPrompt = ref('')
async function runOllama() {
  ollamaLoading.value = true
  const backend = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; return }
  backend.ollamaEnhance(widgets.main_prompt_text || '', ollamaMode.value, JSON.stringify({ prompt: nlPrompt.value }))
}

// 자동완성
const acItems = ref([])
const acIdx = ref(0)
const fieldAcTarget = ref('')
let acTimer = null

function onFieldInput(e, fieldId) {
  fieldAcTarget.value = fieldId
  const text = e.target.value; const lastComma = text.lastIndexOf(',')
  const prefix = (lastComma >= 0 ? text.substring(lastComma + 1) : text).trim()
  if (prefix.length < 2) { acItems.value = []; return }
  clearTimeout(acTimer)
  acTimer = setTimeout(async () => {
    const backend = await getBackend()
    if (backend.getTagSuggestions) backend.getTagSuggestions(prefix, (json) => { try { acItems.value = JSON.parse(json).slice(0, 10); acIdx.value = 0 } catch { acItems.value = [] } })
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
  const text = widgets[fieldId] || ''; const lastComma = text.lastIndexOf(',')
  widgets[fieldId] = (lastComma >= 0 ? text.substring(0, lastComma + 1) + ' ' : '') + tag + ', '
  acItems.value = []; fieldAcTarget.value = ''
}
function onMainInput(e) { autoGrow(e.target); fieldAcTarget.value = 'main_prompt_text'; onFieldInput(e, 'main_prompt_text') }
function onAutoKey(e) { onFieldKey(e, 'main_prompt_text') }
function acceptSuggestion(tag) { acceptFieldSuggestion(tag, 'main_prompt_text'); nextTick(() => { if (mainRef.value) { mainRef.value.focus(); autoGrow(mainRef.value) } }) }

function autoGrow(el) { if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }
function growAll() { nextTick(() => { ;[totalPromptRef, negRef, artistRef, prefixRef, mainRef, suffixRef].forEach(r => { if (r.value) autoGrow(r.value) }) }) }

onMounted(() => {
  setTimeout(growAll, 500); setTimeout(growAll, 1500)
  onBackendEvent('ollamaResult', (json) => {
    ollamaLoading.value = false
    try { const d = JSON.parse(json); if (d.error) { alert('AI Error: ' + d.error); return }; if (d.tags) { widgets.main_prompt_text = d.tags; showNlInput.value = false; nlPrompt.value = '' } } catch {}
  })
})

watch(() => widgets.total_prompt_display, () => nextTick(() => { if (totalPromptRef.value) autoGrow(totalPromptRef.value) }))
watch(() => widgets.neg_prompt_text, () => nextTick(() => { if (negRef.value) autoGrow(negRef.value) }))
watch(() => widgets.artist_input, () => nextTick(() => { if (artistRef.value) autoGrow(artistRef.value) }))
watch(() => widgets.main_prompt_text, () => { nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }); if (tagBlockMode.value) classifyVisibleTags() })
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
.small-btn { padding: 0 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.lock-btn { background: none; border: none; cursor: pointer; font-size: 14px; padding: 0 4px; opacity: 0.5; }
.lock-btn.locked { opacity: 1; }
.total-prompt { min-height: 60px; font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.5; color: var(--accent); border-color: var(--accent-dim); }
.neg-section { margin-top: 8px; }
.neg-toggle { cursor: pointer; list-style: none; }
.neg-toggle::-webkit-details-marker { display: none; }
.danger-label { color: #f87171; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
.neg-prompt { min-height: 30px; color: #f87171; border-color: rgba(248,113,113,0.2); }
.auto-grow { resize: none; overflow: hidden; min-height: 32px; }
.token-info { font-size: 9px; color: var(--text-muted); }
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
.ai-btns { display: flex; gap: 3px; }
.ai-btn { width: 26px; height: 22px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.ai-btn:hover { border-color: var(--accent); color: var(--accent); }
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
label.danger { color: #f87171; }
input[type="number"] { -moz-appearance: textfield; }
input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }
/* neg block field */
.neg :deep(.tbf) { border-color: rgba(248,113,113,0.15); }
.neg :deep(.tbf-block) { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
</style>
