<template>
  <div class="prompt-panel">
    <!-- 최종 프롬프트 (접이식) -->
    <button class="toggle-btn" @click="showFinal = !showFinal">
      {{ showFinal ? '▼' : '▶' }} 최종 프롬프트
    </button>
    <div v-show="showFinal" class="collapsible">
      <textarea
        class="input-area final-prompt"
        :value="get('total_prompt_display')"
        @input="set('total_prompt_display', $event.target.value)"
        placeholder="Final output prompt..."
        rows="3"
      />
      <div class="token-count">TOKENS: {{ tokenCount }}</div>
    </div>

    <!-- 인물 수 -->
    <label class="field-label">인물 수</label>
    <input
      class="input-field"
      :value="get('char_count_input')"
      @input="set('char_count_input', $event.target.value)"
      placeholder="예: 1girl, 2boys"
    />

    <!-- 캐릭터 -->
    <label class="field-label">캐릭터</label>
    <input
      class="input-field"
      :value="get('character_input')"
      @input="set('character_input', $event.target.value)"
      placeholder="캐릭터 이름"
    />

    <!-- 작품명 -->
    <label class="field-label">작품명</label>
    <input
      class="input-field"
      :value="get('copyright_input')"
      @input="set('copyright_input', $event.target.value)"
      placeholder="작품 (Copyright)"
    />

    <!-- 작가 + 고정 -->
    <div class="artist-row">
      <label class="field-label">작가</label>
      <button
        class="lock-btn"
        :class="{ active: get('btn_lock_artist') === 'true' }"
        @click="toggle('btn_lock_artist')"
      >🔒</button>
    </div>
    <textarea
      class="input-area"
      :value="get('artist_input')"
      @input="set('artist_input', $event.target.value)"
      placeholder="작가 태그..."
      rows="2"
    />

    <!-- 선행 프롬프트 -->
    <label class="field-label">선행 프롬프트</label>
    <textarea
      class="input-area"
      :value="get('prefix_prompt_text')"
      @input="set('prefix_prompt_text', $event.target.value)"
      placeholder="year 2025, masterpiece, best quality, ..."
      rows="2"
    />

    <!-- 메인 프롬프트 (자동완성) -->
    <label class="field-label">메인 프롬프트</label>
    <div class="autocomplete-wrap">
      <textarea
        class="input-area main-prompt"
        :value="get('main_prompt_text')"
        @input="onMainInput($event)"
        @keydown="onAutoKey($event)"
        placeholder="메인 태그 입력..."
        rows="4"
        ref="mainPromptRef"
      />
      <div v-if="autoSuggestions.length" class="auto-popup">
        <div v-for="(s, i) in autoSuggestions" :key="s"
          class="auto-item" :class="{ active: autoIdx === i }"
          @mousedown.prevent="applyAutoComplete(s)"
        >{{ s }}</div>
      </div>
    </div>

    <!-- 후행 프롬프트 -->
    <label class="field-label">후행 프롬프트</label>
    <textarea
      class="input-area"
      :value="get('suffix_prompt_text')"
      @input="set('suffix_prompt_text', $event.target.value)"
      placeholder="후행 고정 태그..."
      rows="2"
    />

    <!-- 네거티브 프롬프트 -->
    <label class="field-label negative">네거티브 프롬프트</label>
    <textarea
      class="input-area"
      :value="get('neg_prompt_text')"
      @input="set('neg_prompt_text', $event.target.value)"
      placeholder="lowres, bad quality, ..."
      rows="2"
    />

    <!-- 즐겨찾기 태그바 -->
    <div class="fav-tags" v-if="favTags.length">
      <button v-for="tag in favTags" :key="tag" class="fav-tag"
        @click="insertFavTag(tag)" @contextmenu.prevent="removeFavTag(tag)"
      >{{ tag }}</button>
      <button class="fav-tag add-tag" @click="addFavTag">+</button>
    </div>
    <div v-else class="fav-tags-empty">
      <button class="fav-tag add-tag" @click="addFavTag">+ 즐겨찾기 태그 추가</button>
    </div>

    <!-- 제외 프롬프트 (접이식) -->
    <button class="toggle-btn" @click="showExclude = !showExclude">
      {{ showExclude ? '▼' : '▶' }} 제외 프롬프트
    </button>
    <div v-show="showExclude" class="collapsible">
      <textarea
        class="input-area"
        :value="get('exclude_prompt_local_input')"
        @input="set('exclude_prompt_local_input', $event.target.value)"
        placeholder="예: arms up, __hair, ~blue hair"
        rows="2"
      />
    </div>

    <!-- 태그 제거 옵션 (접이식) -->
    <button class="toggle-btn" @click="showRemove = !showRemove">
      {{ showRemove ? '▼' : '▶' }} 태그 제거 옵션
    </button>
    <div v-show="showRemove" class="collapsible remove-opts">
      <label class="chk-row" v-for="opt in removeOptions" :key="opt.id">
        <input type="checkbox"
          :checked="get(opt.id) === 'true'"
          @change="set(opt.id, $event.target.checked ? 'true' : 'false')"
        />
        <span>{{ opt.label }}</span>
      </label>
    </div>

    <!-- LoRA (접이식) -->
    <button class="toggle-btn" @click="showLora = !showLora">
      {{ showLora ? '▼' : '▶' }} LoRA
    </button>
    <div v-show="showLora" class="collapsible">
      <button class="small-btn" @click="action('open_lora_manager')">LoRA 관리</button>
      <button class="small-btn" @click="action('open_tag_weight_editor')">⚖ 가중치 편집</button>
    </div>

    <!-- 생성 설정 (접이식) -->
    <button class="toggle-btn settings-toggle" @click="showSettings = !showSettings">
      {{ showSettings ? '▼' : '▶' }} 생성 설정
    </button>
    <SettingsPanel v-show="showSettings" />

    <!-- 하단 고정 영역 -->
    <div class="bottom-fixed">
      <!-- 자동화 -->
      <button
        class="auto-toggle"
        :class="{ active: autoOn }"
        @click="autoOn = !autoOn; action('toggle_automation', { checked: autoOn })"
      >
        AUTOMATION: {{ autoOn ? 'ON' : 'OFF' }}
      </button>

      <!-- 생성 버튼 -->
      <button
        class="generate-btn"
        @click="action('generate')"
      >
        {{ autoOn ? '자동화 시작' : '이미지 생성' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { state, getValue, setValue, requestAction } from '../stores/widgetStore.js'
import SettingsPanel from './SettingsPanel.vue'

const showFinal = ref(false)
const showExclude = ref(false)
const showRemove = ref(false)
const showLora = ref(false)
const showSettings = ref(false)
const autoOn = ref(false)

const removeOptions = [
  { id: 'chk_remove_artist', label: '작가명 제거' },
  { id: 'chk_remove_copyright', label: '작품명 제거' },
  { id: 'chk_remove_character', label: '캐릭터 제거' },
  { id: 'chk_remove_meta', label: '메타 제거' },
  { id: 'chk_remove_censorship', label: '검열 제거' },
  { id: 'chk_remove_text', label: '텍스트 제거' },
]

const tokenCount = computed(() => {
  const text = getValue('total_prompt_display')
  if (!text) return '0 / 75'
  const count = text.split(',').filter(t => t.trim()).length
  return `${count} / 75`
})

function get(id) {
  return state.values[id] ?? ''
}

function set(id, value) {
  setValue(id, value)
}

function toggle(id) {
  const cur = get(id) === 'true'
  set(id, cur ? 'false' : 'true')
}

// 태그 자동완성
const autoSuggestions = ref([])
const autoIdx = ref(-1)
const mainPromptRef = ref(null)
let autoTimer = null

async function onMainInput(e) {
  set('main_prompt_text', e.target.value)
  // 마지막 태그 추출
  const text = e.target.value
  const lastComma = text.lastIndexOf(',')
  const currentWord = text.substring(lastComma + 1).trim()
  if (currentWord.length < 2) { autoSuggestions.value = []; return }

  clearTimeout(autoTimer)
  autoTimer = setTimeout(async () => {
    const { getBackend } = await import('../bridge.js')
    const backend = await getBackend()
    if (backend.getTagSuggestions) {
      backend.getTagSuggestions(currentWord, (json) => {
        try { autoSuggestions.value = JSON.parse(json).slice(0, 8) } catch {}
      })
    }
  }, 150)
}

function onAutoKey(e) {
  if (!autoSuggestions.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); autoIdx.value = Math.min(autoIdx.value + 1, autoSuggestions.value.length - 1) }
  if (e.key === 'ArrowUp') { e.preventDefault(); autoIdx.value = Math.max(autoIdx.value - 1, 0) }
  if (e.key === 'Enter' && autoIdx.value >= 0) {
    e.preventDefault()
    applyAutoComplete(autoSuggestions.value[autoIdx.value])
  }
  if (e.key === 'Escape') { autoSuggestions.value = []; autoIdx.value = -1 }
}

function applyAutoComplete(tag) {
  const text = get('main_prompt_text')
  const lastComma = text.lastIndexOf(',')
  const before = lastComma >= 0 ? text.substring(0, lastComma + 1) + ' ' : ''
  set('main_prompt_text', before + tag + ', ')
  autoSuggestions.value = []
  autoIdx.value = -1
}

// 즐겨찾기 태그
const favTags = ref([])

async function loadFavTags() {
  try {
    const resp = localStorage.getItem('favorite_tags')
    if (resp) favTags.value = JSON.parse(resp)
  } catch {}
}
function saveFavTags() {
  localStorage.setItem('favorite_tags', JSON.stringify(favTags.value))
}
function insertFavTag(tag) {
  const cur = get('main_prompt_text')
  const newVal = cur ? cur + ', ' + tag : tag
  set('main_prompt_text', newVal)
}
function removeFavTag(tag) {
  favTags.value = favTags.value.filter(t => t !== tag)
  saveFavTags()
}
function addFavTag() {
  const tag = prompt('추가할 태그:')
  if (tag && tag.trim()) {
    favTags.value.push(tag.trim())
    saveFavTags()
  }
}

// 초기 로드
onMounted(loadFavTags)

function action(name, payload = {}) {
  requestAction(name, payload)
}
</script>

<style scoped>
.prompt-panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}

.field-label {
  font-size: 11px;
  color: #585858;
  font-weight: 600;
  margin-top: 6px;
  padding: 0;
}
.field-label.negative {
  color: #E05252;
}

.input-field {
  width: 100%;
  background: #131313;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  color: #E8E8E8;
  font-size: 13px;
  outline: none;
  transition: background 0.2s;
}
.input-field:focus {
  background: #1A1A1A;
}

.input-area {
  width: 100%;
  background: #131313;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  color: #E8E8E8;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  min-height: 40px;
  transition: background 0.2s;
}
.input-area:focus {
  background: #1A1A1A;
}
.input-area.main-prompt {
  min-height: 80px;
}
.input-area.final-prompt {
  min-height: 60px;
  color: #787878;
  font-size: 12px;
}

.artist-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.lock-btn {
  background: #181818;
  border: none;
  border-radius: 6px;
  color: #585858;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}
.lock-btn.active {
  background: #E2B340;
  color: #0A0A0A;
}

.toggle-btn {
  background: transparent;
  border: none;
  color: #484848;
  font-size: 11px;
  text-align: left;
  padding: 6px 0;
  cursor: pointer;
  transition: color 0.2s;
}
.toggle-btn:hover {
  color: #787878;
}
.toggle-btn.settings-toggle {
  background: #161616;
  border: 1px solid #1A1A1A;
  border-radius: 6px;
  padding: 8px 12px;
  margin-top: 8px;
  font-weight: 600;
}

.collapsible {
  padding: 4px 0;
}

.token-count {
  text-align: right;
  font-size: 10px;
  color: #484848;
  padding: 2px 0;
}

.bottom-fixed {
  margin-top: auto;
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.auto-toggle {
  width: 100%;
  padding: 8px;
  background: #181818;
  border: none;
  border-radius: 6px;
  color: #787878;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.auto-toggle.active {
  background: #4CAF50;
  color: #000;
}

.generate-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(90deg, #E2B340, #D4882A);
  border: none;
  border-radius: 10px;
  color: #000;
  font-weight: 800;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.2s;
}
.generate-btn:hover {
  background: linear-gradient(90deg, #F0C850, #E09030);
}
.remove-opts {
  display: grid; grid-template-columns: 1fr 1fr; gap: 2px;
}
.chk-row {
  display: flex; align-items: center; gap: 6px;
  color: #B0B0B0; font-size: 11px; padding: 3px 0; cursor: pointer;
}
.chk-row input { accent-color: #E2B340; }
.small-btn {
  padding: 5px 10px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer; margin: 2px;
}
.small-btn:hover { background: #222; color: #E8E8E8; }

/* 즐겨찾기 태그바 */
.fav-tags, .fav-tags-empty {
  display: flex; flex-wrap: wrap; gap: 3px; padding: 4px 0;
}
.fav-tag {
  padding: 3px 8px; background: #1A1A1A; border: none; border-radius: 4px;
  color: #E2B340; font-size: 10px; cursor: pointer; white-space: nowrap;
}
.fav-tag:hover { background: #222; }
.fav-tag.add-tag { color: #585858; }

/* 자동완성 */
.autocomplete-wrap { position: relative; }
.auto-popup {
  position: absolute; left: 0; right: 0; bottom: 100%;
  background: #1A1A1A; border-radius: 6px; padding: 4px;
  z-index: 100; max-height: 200px; overflow-y: auto;
  box-shadow: 0 -4px 12px rgba(0,0,0,0.5);
}
.auto-item {
  padding: 5px 10px; font-size: 12px; color: #B0B0B0;
  cursor: pointer; border-radius: 3px;
}
.auto-item:hover, .auto-item.active {
  background: #222; color: #E2B340;
}
</style>
