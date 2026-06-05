<template>
  <div class="prompt-panel">
    <!-- 1. FINAL OUTPUT PROMPT -->
    <div class="glass-card highlight">
      <div class="card-header">
        FINAL OUTPUT PROMPT
        <span class="token-info">{{ tokenCount }} tokens</span>
      </div>
      <TagBlockField v-if="tagBlockMode" :model-value="widgets.total_prompt_display" :color-fn="blockColorClass" placeholder=""
        @update:model-value="onTotalBlockChange" @open-wildcard="(n) => emit('open-wildcard', n)" />
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
        <summary class="danger-label neg-toggle">
          NEGATIVE ▾
          <button class="ai-btn neg-ai" @click.prevent.stop="runSmartNegative()" :disabled="ollamaLoading" title="AI 네거티브 자동 생성">🤖</button>
        </summary>
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
          <label>Character <span v-if="sectionTokens.character" class="tk-badge" :class="tokenBadgeClass(sectionTokens.character)">{{ sectionTokens.character }}t</span></label>
          <button class="small-btn" @click="openCharPresetModal(); loadCharTags()">PRESET</button>
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
        <label>Copyright <span v-if="sectionTokens.copyright" class="tk-badge" :class="tokenBadgeClass(sectionTokens.copyright)">{{ sectionTokens.copyright }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.copyright_input" :color-fn="() => ''" placeholder="작품..." />
        <input v-else type="text" v-model="widgets.copyright_input" placeholder="Copyright / Series..."
          @input="onFieldInput($event, 'copyright_input')" @keydown="onFieldKey($event, 'copyright_input')" />
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'copyright_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'copyright_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <div class="row label-row">
          <label>Artist <span v-if="sectionTokens.artist" class="tk-badge" :class="tokenBadgeClass(sectionTokens.artist)">{{ sectionTokens.artist }}t</span></label>
          <button class="lock-btn" :class="{ locked: artistLocked }" @click="toggleArtistLock">{{ artistLocked ? '🔒' : '🔓' }}</button>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.artist_input" :color-fn="() => ''" placeholder="작가..." />
        <textarea v-else ref="artistRef" v-model="widgets.artist_input" class="auto-grow" placeholder="Artist tags..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Checkpoint</label>
        <CustomSelect v-model="widgets.model_combo" :options="modelItems" placeholder="Select model..." />
      </div>
      <div class="input-group">
        <label>VAE <span class="hint">(ANIMA 등 외부 VAE)</span></label>
        <CustomSelect v-model="widgets.vae_main_combo" :options="vaeItems" placeholder="(체크포인트 기본 사용)" />
      </div>
      <div class="input-group">
        <label>Text Encoder <span class="hint">(드롭다운에서 추가 · 칩 클릭으로 제거)</span></label>
        <CustomSelect :modelValue="''" @update:modelValue="addTeFile"
          :options="teUnselectedItems"
          :placeholder="teItems.length === 0 ? '(text_encoder 폴더 비어있음)' : '+ TE 파일 추가...'" />
        <div v-if="teSelectedList.length > 0" class="te-chips">
          <button v-for="f in teSelectedList" :key="f" type="button"
            class="te-chip active" @click="removeTeFile(f)">
            {{ f }} <span class="te-chip-x">×</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 3. PROMPT BLOCKS -->
    <details class="glass-card" open>
      <summary class="card-header">
        <span>PROMPT BLOCKS</span>
        <span class="undo-btns" @click.stop>
          <button class="undo-btn" :disabled="undoStack.length < 2" @click="performUndo" title="실행 취소 (Ctrl+Z)">↶</button>
          <button class="undo-btn" :disabled="redoStack.length === 0" @click="performRedo" title="다시 실행 (Ctrl+Y)">↷</button>
        </span>
      </summary>
      <div class="input-group autocomplete-wrap">
        <div class="row label-row">
          <label>Main Tags <span v-if="sectionTokens.main" class="tk-badge" :class="tokenBadgeClass(sectionTokens.main)">{{ sectionTokens.main }}t</span></label>
          <div class="ai-btns">
            <button class="ai-btn" @click="ollamaMode = 'expand'; runOllama()" :disabled="ollamaLoading" title="태그 확장">✨</button>
            <button class="ai-btn" @click="showNlInput = !showNlInput" title="자연어 입력 (→태그 / →장면)">💬</button>
            <button class="ai-btn" @click="ollamaMode = 'suggest'; runOllama()" :disabled="ollamaLoading" title="유사 태그">🔄</button>
            <button class="ai-btn" @click="ollamaMode = 'nl_caption'; runOllama()" :disabled="ollamaLoading" title="태그 → 자연어 캡션">📝</button>
            <button class="ai-btn" @click="ollamaMode = 'translate'; runOllama()" :disabled="ollamaLoading" title="한↔영 번역">🌐</button>
            <button class="ai-btn" @click="ollamaMode = 'creative'; runOllama()" :disabled="ollamaLoading" title="캐릭터 기반 창의 생성 (태그+자연어, 비어도 OK)">💡</button>
          </div>
        </div>
        <div class="nl-input-row" v-if="showNlInput">
          <input v-model="nlPrompt" placeholder="자연어 설명 또는 키워드..." @keydown.enter="ollamaMode = 'nl2tags'; runOllama()" class="nl-input" />
          <button class="ai-btn go" @click="ollamaMode = 'nl2tags'; runOllama()" :disabled="ollamaLoading" title="자연어 → 태그">→태그</button>
          <button class="ai-btn go" @click="ollamaMode = 'nl_scene'; runOllama()" :disabled="ollamaLoading" title="키워드 → 영문 장면묘사">→장면</button>
        </div>
        <div class="ai-loading" v-if="ollamaLoading">🤖 AI 처리 중...</div>
        <div class="nl-result" v-if="nlResult">
          <textarea :value="nlResult" readonly class="nl-result-text" rows="4"></textarea>
          <div class="nl-result-btns">
            <button class="ai-btn go" @click="copyNlResult" title="복사">복사</button>
            <button class="ai-btn go" @click="useNlAsMain" title="메인 프롬프트에 넣기">메인에 넣기</button>
            <button class="ai-btn" @click="nlResult = ''" title="닫기">✕</button>
          </div>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.main_prompt_text" :color-fn="blockColorClass" placeholder="태그 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="mainRef" v-model="widgets.main_prompt_text" class="auto-grow" placeholder="메인 태그..."
          @input="onMainInput($event)" @keydown="onAutoKey($event)" rows="3"></textarea>
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'main_prompt_text' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptSuggestion(tag)">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <label>Prefix <span v-if="sectionTokens.prefix" class="tk-badge" :class="tokenBadgeClass(sectionTokens.prefix)">{{ sectionTokens.prefix }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.prefix_prompt_text" :color-fn="blockColorClass" placeholder="선행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="prefixRef" v-model="widgets.prefix_prompt_text" class="auto-grow" placeholder="선행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Suffix <span v-if="sectionTokens.suffix" class="tk-badge" :class="tokenBadgeClass(sectionTokens.suffix)">{{ sectionTokens.suffix }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.suffix_prompt_text" :color-fn="blockColorClass" placeholder="후행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="suffixRef" v-model="widgets.suffix_prompt_text" class="auto-grow" placeholder="후행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <details class="input-group exclude-section">
        <summary class="exclude-toggle">EXCLUDE (LOCAL) ▾ <button class="excl-mgr-btn" @click.prevent.stop="showExcludeManager = true">🔍 MANAGER</button></summary>
        <div class="exclude-help">
          <span>단어 → 포함하는 모든 태그 제외 (short → short hair, very short hair)</span>
          <span>*단어 → 완전 일치만 제외 (*blue hair → blue hair만)</span>
          <span>_단어 → 앞에 붙는 태그 제외 (_short → very short, too short)</span>
          <span>단어_ → 뒤에 붙는 태그 제외 (short_ → short hair, short pants)</span>
          <span>_단어_ → 포함 (단어와 동일, 명시적)</span>
          <span>~단어 → 예외 완전일치 유지</span>
          <span>~_단어 → 예외 접미 유지 (~_tank top → tank top 유지)</span>
          <span>~단어_ → 예외 접두 유지 (~tank_ → tank top 유지)</span>
          <span>~_단어_ → 예외 포함 유지 (~_tank top_ → blue tank top 등 유지)</span>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.exclude_prompt_local_input" :color-fn="excludeColorFn" placeholder="제외 규칙 추가..." />
        <textarea v-else v-model="widgets.exclude_prompt_local_input" class="auto-grow exclude-textarea" placeholder="제외 규칙 (쉼표 구분)..." rows="2"></textarea>
      </details>
    </details>

    <!-- Exclude Manager Modal -->
    <transition name="fade">
      <div v-if="showExcludeManager" class="em-overlay" @click.self="showExcludeManager = false">
        <div class="em-modal">
          <div class="em-header">
            <h3>EXCLUDE MANAGER</h3>
            <span class="em-desc">제외 규칙별 매칭 태그 미리보기</span>
            <button class="close-btn" @click="showExcludeManager = false">✕</button>
          </div>
          <div class="em-body">
            <!-- 좌측: 규칙 목록 + 추가 -->
            <div class="em-rules">
              <div v-for="(rule, ri) in excludeRules" :key="ri" class="em-rule-item"
                :class="[excludeColorFn(rule), { active: selectedExRule === ri }]"
                @click="selectedExRule = ri; loadExcludeMatches(rule)">
                <!-- 편집 모드 -->
                <input v-if="editingExRule === ri" class="em-rule-edit" v-model="editExRuleText"
                  @blur="finishEditExRule(ri)" @keydown.enter="finishEditExRule(ri)" @keydown.escape="editingExRule = -1"
                  @click.stop ref="exRuleEditRef" />
                <!-- 표시 모드 -->
                <span v-else class="em-rule-text" @dblclick.stop="startEditExRule(ri)">{{ rule }}</span>
                <span class="em-match-count">{{ excludeMatches[ri]?.length || '...' }}</span>
                <button class="em-rule-rm" @click.stop="removeExcludeRule(ri)">✕</button>
              </div>
              <div v-if="excludeRules.length === 0" class="em-empty-sm">제외 규칙 없음</div>
              <div class="em-add-row">
                <input v-model="newExcludeRule" placeholder="규칙 추가..." class="em-add-input" @keydown.enter="addExcludeRule" />
                <button class="em-add-btn" @click="addExcludeRule">+</button>
              </div>
            </div>
            <!-- 우측: 매칭 태그 목록 -->
            <div class="em-matches">
              <template v-if="selectedExRule >= 0 && currentExMatches.length > 0">
                <div class="em-match-header">
                  "{{ excludeRules[selectedExRule] }}" — {{ currentExMatches.length }}개 매칭
                </div>
                <div class="em-match-list">
                  <button v-for="tag in currentExMatches" :key="tag" class="em-tag"
                    :class="{ excepted: isExcepted(tag) }"
                    @click="toggleException(tag)"
                    @contextmenu.prevent="addExactExclude(tag)">
                    {{ tag.replace(/_/g, ' ') }}
                  </button>
                </div>
              </template>
              <div v-else class="em-empty">좌측에서 규칙을 선택하세요</div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useWidgetStore, requestAction } from '../stores/widgetStore.js'
import { openCharPresetModal } from '../composables/uiModals.js'
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
  // Undo/Redo 키보드 단축키 + 초기 스냅 (현재 상태)
  window.addEventListener('keydown', onKeyDownGlobal)
  // 초기 스냅은 약간 지연 (widgets 초기 로드 후)
  setTimeout(pushUndoSnapshot, 800)
})
onUnmounted(() => {
  if (_blockModeTimer) clearInterval(_blockModeTimer)
  window.removeEventListener('keydown', onKeyDownGlobal)
  if (debounceTimer) clearTimeout(debounceTimer)
  // UNDO watch들 일괄 해제
  for (const stop of _undoWatchStops) {
    try { stop() } catch {}
  }
  _undoWatchStops.length = 0
})

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
const vaeItems = computed(() => store.getProperty('vae_main_combo', 'items') || [])
const teItems = computed(() => store.getProperty('te_main_input', 'items') || [])
const teSelectedList = computed(() => {
  const raw = widgets.te_main_input || ''
  return raw.split(',').map(s => s.trim()).filter(Boolean)
})
const teUnselectedItems = computed(() => {
  const selected = new Set(teSelectedList.value)
  return teItems.value.filter(f => !selected.has(f))
})
function _serializeTe(list) {
  widgets.te_main_input = list.join(', ')
}
function addTeFile(name) {
  if (!name) return
  const cur = teSelectedList.value
  if (cur.includes(name)) return
  // teItems 정렬 순서 유지
  const next = teItems.value.filter(f => cur.includes(f) || f === name)
  _serializeTe(next)
}
function removeTeFile(name) {
  _serializeTe(teSelectedList.value.filter(f => f !== name))
}
// 토큰 카운트 헬퍼 — SD/CLIP 근사 (실제 토크나이저보다 약간 보수적)
// 규칙: 각 태그(쉼표 구분) → 단어 수 합산 + 쉼표 수
function approxTokens(text) {
  if (!text || !String(text).trim()) return 0
  const chunks = String(text).split(',').map(s => s.trim()).filter(Boolean)
  let total = 0
  for (const c of chunks) {
    const words = c.split(/\s+/).filter(Boolean)
    total += words.length
  }
  return total + Math.max(0, chunks.length - 1) // 쉼표
}
const tokenCount = computed(() => approxTokens(widgets.total_prompt_display))

// 섹션별 토큰 — 블록모드에서도 동작 (widgets 값은 join된 문자열)
const sectionTokens = computed(() => ({
  character: approxTokens(widgets.character_input),
  copyright: approxTokens(widgets.copyright_input),
  artist:    approxTokens(widgets.artist_input),
  main:      approxTokens(widgets.main_prompt_text),
  prefix:    approxTokens(widgets.prefix_prompt_text),
  suffix:    approxTokens(widgets.suffix_prompt_text),
}))
// 75 = CLIP 1청크 한계, 150 = 2청크(BREAK), 225 = 3청크
// 0=숨김, <75=녹색, <150=노랑, ≥150=빨강
function tokenBadgeClass(n) {
  if (!n) return ''
  if (n < 75) return 'tk-ok'
  if (n < 150) return 'tk-warn'
  return 'tk-over'
}

// ── Undo/Redo ──
// 추적 필드: 6개 프롬프트 입력 + 캐릭터/저작권/작가
const UNDO_KEYS = [
  'character_input', 'copyright_input', 'artist_input',
  'main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text',
  'neg_prompt_text',
  'exclude_prompt_local_input',
]
const undoStack = ref([])    // 과거 스냅샷
const redoStack = ref([])    // 미래 (Ctrl+Y용)
const MAX_UNDO = 50
let applying = false         // undo 적용 중에는 watch 다시 push 안 함
let debounceTimer = null     // 빠른 타이핑 묶기

function _snap() {
  const s = {}
  for (const k of UNDO_KEYS) s[k] = widgets[k] || ''
  return s
}
function _eq(a, b) {
  for (const k of UNDO_KEYS) if ((a[k] || '') !== (b[k] || '')) return false
  return true
}
function pushUndoSnapshot() {
  const cur = _snap()
  const last = undoStack.value[undoStack.value.length - 1]
  if (last && _eq(last, cur)) return
  undoStack.value.push(cur)
  if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
  redoStack.value = []  // 새 변경 시 redo 초기화
}
function applySnapshot(snap) {
  applying = true
  for (const k of UNDO_KEYS) {
    if (widgets[k] !== snap[k]) widgets[k] = snap[k]
  }
  nextTick(() => { applying = false })
}
function performUndo() {
  if (undoStack.value.length < 2) return  // 첫 스냅(현재) 외에 없으면 안 함
  const cur = undoStack.value.pop()       // 현재 상태
  redoStack.value.push(cur)
  const prev = undoStack.value[undoStack.value.length - 1]
  applySnapshot(prev)
}
function performRedo() {
  if (redoStack.value.length === 0) return
  const next = redoStack.value.pop()
  undoStack.value.push(next)
  applySnapshot(next)
}

// 디바운스 watch — 빠른 타이핑이 끝나면 스냅샷 (500ms)
// 메모리 누수 방지: stop 함수를 모아 onUnmounted에서 일괄 해제
const _undoWatchStops = []
for (const k of UNDO_KEYS) {
  _undoWatchStops.push(watch(() => widgets[k], () => {
    if (applying) return
    clearTimeout(debounceTimer)
    debounceTimer = setTimeout(pushUndoSnapshot, 500)
  }))
}

// 키보드 단축키 (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z)
function onKeyDownGlobal(e) {
  if (!(e.ctrlKey || e.metaKey)) return
  // 입력 요소 안에서도 동작 — input 자체 undo는 우회됨 (덜 자주 쓰임)
  // 단, contenteditable이나 textarea의 native undo는 그대로 (이건 우리가 못 막음)
  const key = e.key.toLowerCase()
  if (key === 'z' && !e.shiftKey) {
    e.preventDefault()
    performUndo()
  } else if (key === 'y' || (key === 'z' && e.shiftKey)) {
    e.preventDefault()
    performRedo()
  }
}

// 블록 색상 분류
const countPattern = /^(\d+)?(girl|boy|other)s?$|^solo$|^multiple_/
const blockColorCache = ref({})

// ── Exclude Manager ──
const showExcludeManager = ref(false)
const selectedExRule = ref(-1)
const excludeMatches = ref({})  // {ruleIdx: [tags]}

const excludeRules = computed(() => {
  const text = widgets.exclude_prompt_local_input || ''
  return text.split(',').map(t => t.trim()).filter(Boolean)
})

const currentExMatches = computed(() => {
  return excludeMatches.value[selectedExRule.value] || []
})

async function loadExcludeMatches(rule) {
  const backend = await getBackend()
  if (!backend.getExcludeMatches) return
  backend.getExcludeMatches(rule, (json) => {
    try {
      const tags = JSON.parse(json)
      if (Array.isArray(tags)) {
        excludeMatches.value = { ...excludeMatches.value, [selectedExRule.value]: tags }
      }
    } catch {}
  })
}

const newExcludeRule = ref('')
const editingExRule = ref(-1)
const editExRuleText = ref('')
const exRuleEditRef = ref(null)

function startEditExRule(idx) {
  editingExRule.value = idx
  editExRuleText.value = excludeRules.value[idx]
  nextTick(() => { if (exRuleEditRef.value?.[0]) exRuleEditRef.value[0].focus() })
}

function finishEditExRule(idx) {
  if (editingExRule.value !== idx) return
  const newText = editExRuleText.value.trim()
  editingExRule.value = -1
  if (!newText) { removeExcludeRule(idx); return }
  const rules = excludeRules.value.slice()
  rules[idx] = newText
  widgets.exclude_prompt_local_input = rules.join(', ')
  // 매칭 갱신
  selectedExRule.value = idx
  loadExcludeMatches(newText)
}

function addExcludeRule() {
  const rule = newExcludeRule.value.trim()
  if (!rule) return
  const cur = widgets.exclude_prompt_local_input || ''
  widgets.exclude_prompt_local_input = cur ? cur + ', ' + rule : rule
  newExcludeRule.value = ''
}

function removeExcludeRule(idx) {
  const rules = excludeRules.value.slice()
  rules.splice(idx, 1)
  widgets.exclude_prompt_local_input = rules.join(', ')
  if (selectedExRule.value >= rules.length) selectedExRule.value = -1
}

function isExcepted(tag) {
  const cur = (widgets.exclude_prompt_local_input || '').toLowerCase()
  return cur.includes('~' + tag.toLowerCase())
}

function addExactExclude(tag) {
  // 우클릭: *완전일치 제외 규칙 추가
  const cur = widgets.exclude_prompt_local_input || ''
  const rule = '*' + tag
  if (!cur.includes(rule)) {
    widgets.exclude_prompt_local_input = cur ? cur + ', ' + rule : rule
  }
}

function toggleException(tag) {
  const cur = widgets.exclude_prompt_local_input || ''
  const exception = '~' + tag
  if (isExcepted(tag)) {
    // 예외 해제 — ~tag 제거
    const rules = cur.split(',').map(r => r.trim()).filter(r => r.toLowerCase() !== exception.toLowerCase())
    widgets.exclude_prompt_local_input = rules.join(', ')
  } else {
    // 예외 추가
    widgets.exclude_prompt_local_input = cur ? cur + ', ' + exception : exception
  }
}

// 최종 프롬프트 블록 변경 시 → 원본 필드에서 태그 제거
function onTotalBlockChange(newVal) {
  const newTags = new Set(newVal.split(',').map(t => t.trim().toLowerCase()).filter(Boolean))
  // 각 필드에서 없어진 태그 제거
  for (const key of ['main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text']) {
    const cur = widgets[key] || ''
    const filtered = cur.split(',').map(t => t.trim()).filter(t => {
      return t && newTags.has(t.toLowerCase())
    })
    const result = filtered.join(', ')
    if (result !== cur.trim()) widgets[key] = result
  }
}

function excludeColorFn(text) {
  const t = text.trim()
  if (t.startsWith('~')) return 'bc-action'       // 예외 계열 (초록)
  if (t.startsWith('*')) return 'bc-expression'   // 완전 일치 (노랑)
  if (t.startsWith('_') && t.endsWith('_')) return 'bc-nsfw'
  if (t.startsWith('_')) return 'bc-body'         // 끝 매치 (주황)
  if (t.endsWith('_')) return 'bc-clothing'       // 시작 매치 (보라)
  return 'bc-nsfw'
}

function blockColorClass(text) {
  if (text.includes('__') && /__(.+?)__/.test(text)) return 'wc-block'
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
      if (tag && !countPattern.test(tag.toLowerCase()) && !blockColorCache.value[tag.toLowerCase()] && !/__(.+?)__/.test(tag)) allTags.add(tag)
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
const nlResult = ref('')
let ollamaTimer = null
async function runOllama() {
  const mode = ollamaMode.value
  const main = widgets.main_prompt_text || ''
  let contentArg = main
  let extraPrompt = ''
  if (mode === 'nl2tags') {
    if (!nlPrompt.value.trim()) { requestAction('show_toast', { type: 'info', msg: '자연어 설명을 입력하세요' }); return }
    extraPrompt = nlPrompt.value
  } else if (mode === 'nl_scene') {
    if (!nlPrompt.value.trim()) { requestAction('show_toast', { type: 'info', msg: '키워드를 입력하세요' }); return }
    contentArg = nlPrompt.value
  } else if (mode === 'creative') {
    // 캐릭터 + (있으면) 메인 태그를 힌트로. 완전 비어도 생성 허용.
    const ch = (widgets.character_input || '').trim()
    contentArg = [ch, main.trim()].filter(Boolean).join(', ')
  } else {
    if (!main.trim()) { requestAction('show_toast', { type: 'info', msg: '프롬프트를 먼저 입력하세요' }); return }
  }
  ollamaLoading.value = true
  // 타임아웃 안전장치
  clearTimeout(ollamaTimer)
  ollamaTimer = setTimeout(() => {
    if (ollamaLoading.value) {
      ollamaLoading.value = false
      requestAction('show_toast', { type: 'error', msg: 'AI 응답 시간 초과 — Ollama 서버 상태를 확인하세요' })
    }
  }, 65000)
  const backend = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; clearTimeout(ollamaTimer); return }
  const url = window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434'
  const model = window.localStorage.getItem('ollamaModel') || 'gemma3:4b'
  backend.ollamaEnhance(contentArg, mode, JSON.stringify({ prompt: extraPrompt, url, model }))
}

async function runSmartNegative() {
  const positivePrompt = widgets.total_prompt_display || widgets.main_prompt_text || ''
  if (!positivePrompt.trim()) {
    requestAction('show_toast', { type: 'info', msg: '포지티브 프롬프트를 먼저 입력하세요' })
    return
  }
  ollamaLoading.value = true
  clearTimeout(ollamaTimer)
  ollamaTimer = setTimeout(() => {
    if (ollamaLoading.value) {
      ollamaLoading.value = false
      requestAction('show_toast', { type: 'error', msg: 'AI 응답 시간 초과' })
    }
  }, 65000)
  const backend = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; clearTimeout(ollamaTimer); return }
  const url = window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434'
  const model = window.localStorage.getItem('ollamaModel') || 'gemma3:4b'
  backend.ollamaEnhance(positivePrompt, 'negative', JSON.stringify({ url, model }))
}

function copyNlResult() {
  try { navigator.clipboard?.writeText(nlResult.value) } catch {}
  requestAction('show_toast', { type: 'info', msg: '복사됨' })
}
function useNlAsMain() {
  // 앞의 태그는 override하지 않고 맨 뒤에 추가
  const cur = (widgets.main_prompt_text || '').trim()
  const add = nlResult.value.trim()
  widgets.main_prompt_text = cur ? (cur.replace(/,?\s*$/, '') + ', ' + add) : add
  nlResult.value = ''
  nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
  requestAction('show_toast', { type: 'success', msg: '메인 프롬프트 끝에 추가' })
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
  // UI prefs 로드 (재시작 시 블록 모드 복원)
  onBackendEvent('uiPrefsLoaded', (json) => {
    try {
      const prefs = JSON.parse(json)
      if (typeof prefs.tagBlockMode === 'boolean') {
        window.localStorage.setItem('tagBlockMode', String(prefs.tagBlockMode))
        tagBlockMode.value = prefs.tagBlockMode
      }
      if (typeof prefs.galleryShowMetadata === 'boolean') window.localStorage.setItem('galleryShowMetadata', String(prefs.galleryShowMetadata))
    } catch {}
  })
  onBackendEvent('ollamaResult', (json) => {
    ollamaLoading.value = false
    clearTimeout(ollamaTimer)
    try {
      const d = JSON.parse(json)
      if (d.error) {
        const msg = d.error.includes('연결') ? 'Ollama 서버에 연결할 수 없습니다' :
                    d.error.includes('시간') || d.error.includes('Timeout') ? 'AI 응답 시간 초과' :
                    `AI 오류: ${d.error}`
        requestAction('show_toast', { type: 'error', msg })
        return
      }
      if (d.tags) {
        const NL = ['nl_caption', 'nl_scene', 'translate', 'creative']
        if (NL.includes(d.mode)) {
          nlResult.value = d.tags
          const label = d.mode === 'translate' ? '번역' : d.mode === 'nl_caption' ? '캡션'
                      : d.mode === 'creative' ? '창의 생성' : '장면묘사'
          requestAction('show_toast', { type: 'success', msg: `AI ${label} 완료` })
        } else if (d.mode === 'negative') {
          const existing = (widgets.neg_prompt_text || '').trim()
          widgets.neg_prompt_text = existing ? existing.replace(/,?\s*$/, '') + ', ' + d.tags : d.tags
          requestAction('show_toast', { type: 'success', msg: 'AI 네거티브 생성 완료' })
        } else {
          widgets.main_prompt_text = d.tags
          showNlInput.value = false
          nlPrompt.value = ''
          requestAction('show_toast', { type: 'success', msg: `AI ${d.mode === 'nl2tags' ? '변환' : d.mode === 'suggest' ? '추천' : '확장'} 완료` })
        }
      }
    } catch {}
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
.neg-toggle { cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; }
.neg-toggle::-webkit-details-marker { display: none; }
.neg-ai { font-size: 12px !important; padding: 2px 6px !important; opacity: 0.6; }
.neg-ai:hover { opacity: 1; }
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
.nl-result { margin: 4px 0; }
.nl-result-text { width: 100%; background: var(--bg-input); border: 1px solid var(--accent); border-radius: 6px; padding: 7px 9px; color: var(--text-primary); font-size: 12px; resize: vertical; line-height: 1.5; font-family: inherit; }
.nl-result-btns { display: flex; gap: 4px; margin-top: 4px; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.autocomplete-wrap { position: relative; }
.ac-popup { position: absolute; left: 0; right: 0; top: 100%; z-index: 100; background: #1A1A1A; border: 1px solid var(--border); border-radius: 6px; max-height: 200px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
.ac-item { padding: 6px 12px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.03); }
.ac-item:hover, .ac-item.selected { background: var(--accent-dim); color: var(--accent); }
label.danger { color: #f87171; }
.exclude-section { margin-bottom: 0; }
.exclude-toggle { font-size: 10px; font-weight: 800; color: #f87171; letter-spacing: 1px; cursor: pointer; list-style: none; }
.exclude-toggle::-webkit-details-marker { display: none; }
.exclude-help { display: flex; flex-direction: column; gap: 2px; margin: 6px 0; padding: 6px 8px; background: rgba(248,113,113,0.03); border: 1px solid rgba(248,113,113,0.1); border-radius: 4px; }
.exclude-help span { font-size: 9px; color: var(--text-muted); font-family: 'Consolas', monospace; }
.exclude-textarea { color: #f87171; border-color: rgba(248,113,113,0.2); font-size: 11px; }
.excl-mgr-btn { padding: 1px 8px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--text-muted); font-size: 8px; cursor: pointer; margin-left: 8px; }
.excl-mgr-btn:hover { border-color: #f87171; color: #f87171; }

/* Exclude Manager Modal */
.em-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 3000; display: flex; align-items: center; justify-content: center; }
.em-modal { width: 700px; height: 500px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.em-header { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.em-header h3 { font-size: 12px; letter-spacing: 2px; color: #f87171; }
.em-desc { font-size: 9px; color: var(--text-muted); flex: 1; }
.em-body { flex: 1; display: flex; overflow: hidden; }
.em-rules { width: 200px; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; }
.em-rule-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; font-size: 11px; cursor: pointer; border-radius: 4px; margin-bottom: 2px; border: 1px solid transparent; }
.em-rule-item:hover { background: var(--bg-input); }
.em-rule-item.active { border-color: #f87171; background: rgba(248,113,113,0.05); }
.em-rule-text { font-family: 'Consolas', monospace; }
.em-match-count { font-size: 9px; color: var(--text-muted); background: var(--bg-button); padding: 1px 6px; border-radius: 8px; }
.em-matches { flex: 1; overflow-y: auto; padding: 12px; }
.em-match-header { font-size: 10px; color: var(--text-muted); margin-bottom: 8px; }
.em-match-list { display: flex; flex-wrap: wrap; gap: 4px; }
.em-tag { padding: 3px 10px; background: rgba(248,113,113,0.05); border: 1px solid rgba(248,113,113,0.2); border-radius: 4px; color: #f87171; font-size: 10px; cursor: pointer; transition: all 0.12s; }
.em-tag:hover { border-color: rgba(248,113,113,0.5); }
.em-tag.excepted { background: rgba(74,222,128,0.1); border-color: rgba(74,222,128,0.3); color: #4ade80; text-decoration: line-through; opacity: 0.6; }
.em-tag.excepted:hover { opacity: 1; }
.em-rule-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 11px; flex-shrink: 0; }
.em-rule-edit { flex: 1; padding: 2px 6px; font-size: 11px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 3px; color: var(--text-primary); font-family: 'Consolas', monospace; }
.em-rule-text { cursor: default; }
.em-add-row { display: flex; gap: 4px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.em-add-input { flex: 1; padding: 4px 8px; font-size: 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); }
.em-add-btn { width: 28px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--accent); font-weight: 800; cursor: pointer; }
.em-empty-sm { padding: 8px; text-align: center; color: var(--text-muted); font-size: 10px; }
.em-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 12px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
input[type="number"] { -moz-appearance: textfield; }
input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }
/* neg block field */
.neg :deep(.tbf) { border-color: rgba(248,113,113,0.15); }
.neg :deep(.tbf-block) { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
.hint { font-size: 10px; color: rgba(255,255,255,0.4); font-weight: normal; margin-left: 4px; }
.tk-badge {
  display: inline-block; padding: 1px 6px; margin-left: 6px; font-size: 9px;
  font-weight: bold; border-radius: 8px; vertical-align: middle;
  border: 1px solid transparent;
}
.tk-badge.tk-ok    { background: rgba(74,222,128,0.12); color: #4ade80; border-color: rgba(74,222,128,0.3); }
.tk-badge.tk-warn  { background: rgba(251,191,36,0.12); color: #fbbf24; border-color: rgba(251,191,36,0.4); }
.tk-badge.tk-over  { background: rgba(248,113,113,0.18); color: #f87171; border-color: rgba(248,113,113,0.5); }

/* Undo/Redo 버튼 */
.undo-btns { float: right; display: inline-flex; gap: 4px; margin-left: auto; }
.undo-btn {
  width: 24px; height: 22px; padding: 0; font-size: 13px; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px; color: var(--text-primary);
}
.undo-btn:hover:not(:disabled) { background: rgba(96,165,250,0.18); color: #93c5fd; border-color: #60a5fa; }
.undo-btn:disabled { opacity: 0.3; cursor: not-allowed; }
summary.card-header { display: flex; align-items: center; }
.te-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.te-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  transition: all 0.15s;
}
.te-chip:hover { border-color: rgba(96,165,250,0.5); color: #fff; }
.te-chip.active {
  background: rgba(96,165,250,0.2);
  border-color: #60a5fa;
  color: #93c5fd;
}
.te-chip-x { margin-left: 4px; opacity: 0.6; }
.te-chip:hover .te-chip-x { opacity: 1; color: #f87171; }
</style>
