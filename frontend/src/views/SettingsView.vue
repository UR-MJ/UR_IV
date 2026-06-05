<template>
  <div class="settings-workspace" @keydown.ctrl.f.prevent="focusSearch">
    <!-- Left: Sub-navigation -->
    <aside class="settings-nav">
      <div class="nav-header">PREFERENCES</div>
      <div class="settings-search-wrap">
        <input ref="searchInputRef" v-model="settingsSearch" class="settings-search"
          placeholder="🔍 설정 검색 (Ctrl+F)" />
        <button v-if="settingsSearch" class="search-clear" @click="settingsSearch = ''" title="지우기">✕</button>
      </div>
      <button v-for="tab in filteredSubTabs" :key="tab.id"
        class="nav-item" :class="{ active: currentTab === tab.id }"
        @click="currentTab = tab.id"
      >
        <span class="icon">{{ tab.icon }}</span>
        <span class="label">{{ tab.label }}</span>
      </button>
      <div v-if="settingsSearch && filteredSubTabs.length === 0" class="nav-empty">
        검색 결과 없음
      </div>
    </aside>

    <!-- Right: Content Area -->
    <main class="settings-body">
      <div class="settings-content">
        <!-- 1. General & Backend -->
        <div v-show="currentTab === 'general'" class="section-fade">
          <div class="glass-card">
            <label>SYSTEM STATUS</label>
            <div class="info-row">
              <span class="desc">CORE VERSION</span>
              <span class="val-badge">v2.0.0 PRO</span>
            </div>
            <div class="info-row mt-12">
              <span class="desc">API ORCHESTRATOR</span>
              <button class="btn-pill" @click="act('show_api_manager')">MANAGE BACKENDS</button>
            </div>
          </div>
        </div>

        <!-- 2. Network & API -->
        <div v-show="currentTab === 'api'" class="section-fade">
          <div class="glass-card">
            <label>API CONFIGURATION</label>
            <div class="input-stack">
              <div class="input-unit">
                <span class="unit-label">STABLE DIFFUSION WEBUI</span>
                <input v-model="webuiUrl" placeholder="http://127.0.0.1:7860" />
              </div>
              <div class="input-unit mt-12">
                <span class="unit-label">COMFYUI (NODE-BASED)</span>
                <input v-model="comfyUrl" placeholder="http://127.0.0.1:8188" />
              </div>
            </div>
            <button class="btn-pill primary mt-16" @click="act('show_api_manager')">TEST CONNECTIVITY</button>
          </div>
        </div>

        <!-- 3. Prompt Logic -->
        <div v-show="currentTab === 'prompt'" class="section-fade">
          <div class="glass-card">
            <label>PROMPT AUTOMATION</label>
            <div class="toggle-grid">
              <label class="toggle-row">
                <span>Auto-clean Duplicates</span>
                <input type="checkbox" v-model="cleanDuplicates" />
              </label>
              <label class="toggle-row">
                <span>Sanitize Whitespaces</span>
                <input type="checkbox" v-model="cleanSpaces" />
              </label>
              <label class="toggle-row">
                <span>Convert Underscores</span>
                <input type="checkbox" v-model="cleanUnderscore" />
              </label>
              <label class="toggle-row">
                <span>Tag Block Mode</span>
                <input type="checkbox" v-model="defaultBlockMode" @change="setBlockMode" />
              </label>
              <label class="toggle-row">
                <span>Gallery Metadata Panel</span>
                <input type="checkbox" v-model="galleryMetadata" @change="window.localStorage.setItem('galleryShowMetadata', String(galleryMetadata))" />
              </label>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>DATA PERSISTENCE</label>
            <div class="btn-row-2">
              <button class="btn-pill" @click="act('save_settings')">SAVE GLOBAL</button>
              <button class="btn-pill" @click="act('show_prompt_history')">OPEN HISTORY</button>
            </div>
          </div>
        </div>

        <!-- 4. Tab Layout (Drag & Drop) -->
        <div v-show="currentTab === 'tabs'" class="section-fade">
          <div class="glass-card">
            <label>CUSTOM WORKSPACE ORDER</label>
            <div class="drag-list">
              <div v-for="(tab, i) in tabOrder" :key="tab"
                class="drag-item"
                draggable="true"
                @dragstart="dragStart(i)" @dragover.prevent @drop="dragDrop(i)"
              >
                <span class="handle">⠿</span>
                <span class="name">{{ tab }}</span>
              </div>
            </div>
            <div class="btn-row-2 mt-16">
              <button class="btn-pill primary" @click="applyTabOrder">APPLY LAYOUT</button>
              <button class="btn-pill" @click="resetTabOrder">RESET DEFAULT</button>
            </div>
          </div>
        </div>

        <!-- 5. Shortcuts -->
        <div v-show="currentTab === 'shortcuts'" class="section-fade">
          <div class="hint-banner">
            ℹ️ 같은 단축키도 <strong>현재 활성 탭</strong>에 따라 동작이 달라집니다.
            예: <kbd>Ctrl+Z</kbd>는 Editor 탭에서는 편집 Undo, T2I/I2I/Inpaint에서는 프롬프트 Undo.
            전역 키는 모든 탭에서 동일.
          </div>
          <div class="glass-card">
            <label>전역 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>설정 저장</span><kbd>Ctrl + S</kbd></div>
              <div class="s-row"><span>이미지 생성</span><kbd>Ctrl + G</kbd></div>
              <div class="s-row"><span>모달/패널 닫기</span><kbd>Esc</kbd></div>
              <div class="s-row"><span>히스토리 새로고침</span><kbd>F5</kbd></div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>HISTORY 네비게이션</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>이전 / 다음 이미지</span><kbd>↑ ↓</kbd></div>
              <div class="s-row">
                <span>최상단 / 최하단으로 점프 (보조키 + ↑↓)</span>
                <select v-model="historyJumpModifier" @change="window.localStorage.setItem('historyJumpModifier', historyJumpModifier)" class="hjm-select">
                  <option value="shiftKey">Shift</option>
                  <option value="ctrlKey">Ctrl</option>
                  <option value="altKey">Alt</option>
                </select>
              </div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>EDITOR 탭 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>파일 열기</span><kbd>Ctrl + O</kbd></div>
              <div class="s-row"><span>클립보드 붙여넣기</span><kbd>Ctrl + V</kbd></div>
              <div class="s-row"><span>저장 (원본 덮어쓰기)</span><kbd>Ctrl + S</kbd></div>
              <div class="s-row"><span>다른 이름으로 저장</span><kbd>Ctrl + Shift + S</kbd></div>
              <div class="s-row"><span>편집 Undo</span><kbd>Ctrl + Z</kbd></div>
              <div class="s-row"><span>편집 Redo</span><kbd>Ctrl + Y</kbd></div>
              <div class="s-row"><span>선택 해제</span><kbd>Esc</kbd></div>
              <div class="s-row"><span>이미지 확대/축소</span><kbd>마우스 휠</kbd></div>
              <div class="s-row"><span>이미지 회전 (5°)</span><kbd>Shift + 휠</kbd></div>
              <div class="s-row"><span>확대/회전/위치 초기화</span><kbd>Ctrl 빠르게 2회</kbd></div>
              <div class="s-row"><span>화면 이동 (팬)</span><kbd>Alt + 드래그</kbd></div>
              <div class="s-row"><span>변환 초기화 (대체)</span><kbd>Alt + 더블클릭</kbd></div>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>프롬프트 편집 단축키</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>프롬프트 Undo</span><kbd>Ctrl + Z</kbd></div>
              <div class="s-row"><span>프롬프트 Redo</span><kbd>Ctrl + Y / Ctrl + Shift + Z</kbd></div>
              <div class="s-row"><span>자동완성 이동</span><kbd>↑ ↓</kbd></div>
              <div class="s-row"><span>자동완성 선택</span><kbd>Tab / Enter</kbd></div>
              <div class="s-row"><span>자동완성 닫기</span><kbd>Esc</kbd></div>
            </div>
          </div>
        </div>

        <!-- 6. 기본값 설정 (탭별) -->
        <div v-show="currentTab === 'defaults'" class="section-fade">
          <!-- 자동화 / 세션 -->
          <div class="glass-card">
            <label>자동화 · 세션 복구</label>
            <label class="toggle-row">
              <input type="checkbox" v-model="autoResumeOnStart" @change="onAutoResumeChange" />
              <span>🔄 앱 재시작 시 자동화 자동 재시작 (기본 ON)</span>
            </label>
            <p class="def-hint">
              자동화 도중 앱을 끄면 큐가 자동 저장되고, 다시 켜면 1.5초 후 자동으로 ▶ 시작합니다.<br>
              끄면 큐는 복구되지만 시작 버튼을 직접 눌러야 합니다.
            </p>
          </div>

          <!-- UI 크기 조절 -->
          <div class="glass-card mt-16">
            <label>UI 크기 (전역 zoom)</label>
            <div class="def-field-wide">
              <span>{{ Math.round(uiScale * 100) }}% — 폰트·아이콘·패딩 비례 확대</span>
              <input type="range" min="0.8" max="1.5" step="0.05" v-model.number="uiScale"
                @input="onUiScaleChange" class="w-slider" />
              <div class="scale-presets">
                <button v-for="p in [0.9, 1.0, 1.1, 1.2, 1.3]" :key="p"
                  class="scale-btn"
                  :class="{ active: Math.abs(uiScale - p) < 0.025 }"
                  @click="uiScale = p; onUiScaleChange()">
                  {{ Math.round(p * 100) }}%
                </button>
              </div>
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>T2I 기본값 <span class="sync-badge" v-if="t2iSynced">SYNCED</span></label>
            <div class="defaults-grid">
              <div class="def-field"><span>Steps</span><input type="number" v-model.number="defaults.steps" /></div>
              <div class="def-field"><span>CFG Scale</span><input type="number" v-model.number="defaults.cfg" step="0.5" /></div>
              <div class="def-field"><span>Width</span><input type="number" v-model.number="defaults.width" /></div>
              <div class="def-field"><span>Height</span><input type="number" v-model.number="defaults.height" /></div>
              <div class="def-field"><span>Seed</span><input type="text" v-model="defaults.seed" /></div>
              <div class="def-field"><span>Denoising (I2I)</span><input type="number" v-model.number="defaults.denoising" step="0.05" /></div>
              <div class="def-field"><span>Sampler</span>
                <CustomSelect v-model="defaults.sampler" :options="['', ...samplerList]" placeholder="Auto" />
              </div>
              <div class="def-field"><span>Scheduler</span>
                <CustomSelect v-model="defaults.scheduler" :options="['', ...schedulerList]" placeholder="Auto" />
              </div>
            </div>
            <button class="btn-pill mt-12" @click="syncFromT2I">SYNC FROM T2I</button>
          </div>

          <div class="glass-card mt-16">
            <label>EDITOR 기본값</label>
            <div class="defaults-grid">
              <div class="def-field"><span>Brush Size</span><input type="number" v-model.number="defaults.brushSize" /></div>
              <div class="def-field"><span>Effect Strength</span><input type="number" v-model.number="defaults.effectStrength" /></div>
              <div class="def-field"><span>YOLO Confidence</span><input type="number" v-model.number="defaults.yoloConf" step="0.05" /></div>
              <div class="def-field"><span>Snap Radius</span><input type="number" v-model.number="defaults.snapRadius" /></div>
            </div>
            <div class="def-field-wide mt-12">
              <span>사이드 패널 너비 ({{ editorSidePanelWidth }}px)</span>
              <input type="range" min="200" max="500" step="10" v-model.number="editorSidePanelWidth"
                @input="onSidePanelWidthChange" class="w-slider" />
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>SEARCH 기본값</label>
            <div class="defaults-grid">
              <div class="def-field"><span>Default Rating</span>
                <CustomSelect v-model="defaults.defaultRating" :options="['g', 's', 'q', 'e']" placeholder="Rating" />
              </div>
            </div>
          </div>

          <div class="glass-card mt-16">
            <label>확장 기본값</label>
            <div class="toggle-grid">
              <label class="toggle-row"><input type="checkbox" v-model="defaults.hires_enabled" /><span>Hires.fix 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.ad_enabled" /><span>ADetailer 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.sam3_enabled" /><span>SAM3 기본 활성화</span></label>
              <label class="toggle-row"><input type="checkbox" v-model="defaults.negpip_enabled" /><span>NegPiP 기본 활성화</span></label>
            </div>
          </div>
          <div class="btn-row-2 mt-16">
            <button class="btn-pill primary" @click="saveDefaults">SAVE DEFAULTS</button>
            <button class="btn-pill" @click="resetDefaults">RESET TO FACTORY</button>
          </div>
        </div>

        <!-- 7. AI Assist (Ollama) -->
        <div v-show="currentTab === 'ollama'" class="section-fade">
          <div class="glass-card">
            <label>OLLAMA CONFIGURATION</label>
            <div class="input-stack">
              <div class="input-unit">
                <span class="unit-label">SERVER URL</span>
                <input v-model="ollamaUrl" @change="saveOllamaSettings" placeholder="http://localhost:11434" />
              </div>
              <div class="input-unit mt-12">
                <span class="unit-label">MODEL</span>
                <CustomSelect v-if="ollamaModels.length" v-model="ollamaModel" :options="ollamaModels" placeholder="모델 선택..." @update:modelValue="saveOllamaSettings" />
                <input v-else v-model="ollamaModel" @change="saveOllamaSettings" placeholder="llama3.1, gemma3 등" />
              </div>
              <label class="ollama-unload-row mt-12">
                <input type="checkbox" v-model="ollamaUnloadOnGen" @change="saveOllamaSettings" />
                <span>이미지 생성 시 LLM 언로드 (VRAM 확보) — 12B 등 큰 모델 + SD 공유 시 권장</span>
              </label>
            </div>
            <div class="btn-row-2 mt-16">
              <button class="btn-pill primary" @click="testOllama">TEST CONNECTION</button>
              <button class="btn-pill" @click="loadOllamaModels">REFRESH MODELS</button>
            </div>
            <div class="info-row mt-12" v-if="ollamaModels.length">
              <span class="desc">AVAILABLE MODELS ({{ ollamaModels.length }})</span>
              <span class="val-badge">{{ ollamaModel }}</span>
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>RECOMMENDED MODELS</label>
            <div class="recommend-grid">
              <div class="rec-item best">
                <span class="rec-name">gemma3:4b</span>
                <span class="rec-desc">가장 추천 — 빠르고 태그 품질 우수, VRAM 3GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">llama3.1:8b</span>
                <span class="rec-desc">범용 고품질, 영어 태그 강점, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">mistral:7b</span>
                <span class="rec-desc">빠른 응답, 창의적 태그 변형에 강함, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">phi4-mini:3.8b</span>
                <span class="rec-desc">초경량, VRAM 부족 시 대안, VRAM 2.5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">qwen3:8b</span>
                <span class="rec-desc">다국어+태그 강점, thinking 모드, VRAM 5GB</span>
              </div>
              <div class="rec-item">
                <span class="rec-name">gemma3:12b</span>
                <span class="rec-desc">최고 품질, 여유 VRAM 시 추천, VRAM 8GB</span>
              </div>
            </div>
            <div class="rec-note mt-12">
              SD 이미지 생성과 동시 사용 시 VRAM을 공유하므로 4b 이하 경량 모델 권장.<br/>
              <code>ollama pull gemma3:4b</code> 로 설치
            </div>
          </div>
          <div class="glass-card mt-16">
            <label>USAGE</label>
            <div class="shortcut-grid">
              <div class="s-row"><span>✨ Expand Tags</span><span>기존 태그를 고품질 태그로 확장</span></div>
              <div class="s-row"><span>💬 Natural Language</span><span>자연어 설명을 태그로 변환</span></div>
              <div class="s-row"><span>🔄 Suggest Similar</span><span>유사하지만 다른 태그 추천</span></div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { requestAction, useWidgetStore } from '../stores/widgetStore.js'
import CustomSelect from '../components/CustomSelect.vue'

const subTabs = [
  // keywords: 사용자 검색 시 라벨 외에도 매칭할 한/영 키워드들
  { id: 'general',   label: 'GENERAL',   icon: '⚙️', keywords: 'general 일반 시스템 코어 버전' },
  { id: 'api',       label: 'NETWORK',   icon: '🌐', keywords: 'network api 네트워크 webui comfy url 백엔드 연결' },
  { id: 'prompt',    label: 'LOGIC',     icon: '📝', keywords: 'logic 로직 프롬프트 와일드카드 wildcard 제외 exclude 조건부' },
  { id: 'tabs',      label: 'WORKSPACE', icon: '🗂️', keywords: 'workspace 워크스페이스 탭 순서 tab order layout' },
  { id: 'shortcuts', label: 'HOTKEYS',   icon: '⌨️', keywords: 'hotkeys shortcuts 단축키 키보드 ctrl shift z y s g' },
  { id: 'defaults',  label: 'DEFAULTS',  icon: '🎛️', keywords: 'defaults 기본값 t2i i2i inpaint 해상도 steps cfg sampler 시드' },
  { id: 'ollama',    label: 'AI ASSIST', icon: '🧠', keywords: 'ollama ai assist 어시스트 자동완성 번역' },
]
const currentTab = ref('general')
const settingsSearch = ref('')
const searchInputRef = ref(null)
const filteredSubTabs = computed(() => {
  const q = settingsSearch.value.trim().toLowerCase()
  if (!q) return subTabs
  return subTabs.filter(t =>
    t.label.toLowerCase().includes(q) ||
    (t.keywords || '').toLowerCase().includes(q)
  )
})
// 검색 결과가 1개면 자동 선택
watch(filteredSubTabs, (val) => {
  if (settingsSearch.value && val.length === 1 && currentTab.value !== val[0].id) {
    currentTab.value = val[0].id
  }
})
function focusSearch() {
  searchInputRef.value?.focus()
  searchInputRef.value?.select()
}
const webuiUrl = ref('http://127.0.0.1:7860')
const comfyUrl = ref('http://127.0.0.1:8188')
const cleanDuplicates = ref(true)
const cleanSpaces = ref(true)
const cleanUnderscore = ref(true)
const defaultBlockMode = ref(window.localStorage.getItem('tagBlockMode') === 'true')
const galleryMetadata = ref(window.localStorage.getItem('galleryShowMetadata') !== 'false')
const historyJumpModifier = ref(window.localStorage.getItem('historyJumpModifier') || 'shiftKey')

// API에서 sampler/scheduler 목록 가져오기
const wStore = useWidgetStore()
const samplerList = computed(() => wStore.getProperty('sampler_combo', 'items') || [])
const schedulerList = computed(() => wStore.getProperty('scheduler_combo', 'items') || [])

// UI prefs 로드 시 동기화
import { onBackendEvent, getBackend } from '../bridge.js'
onMounted(async () => {
  // defaults 로드
  const bk = await getBackend()
  if (bk.getTabDefaults) {
    bk.getTabDefaults((json) => {
      try { const d = JSON.parse(json); Object.assign(defaults, d) } catch {}
    })
  }
  onBackendEvent('uiPrefsLoaded', (json) => {
    try {
      const prefs = JSON.parse(json)
      if (typeof prefs.tagBlockMode === 'boolean') { defaultBlockMode.value = prefs.tagBlockMode; window.localStorage.setItem('tagBlockMode', String(prefs.tagBlockMode)) }
      if (typeof prefs.cleanDuplicates === 'boolean') cleanDuplicates.value = prefs.cleanDuplicates
      if (typeof prefs.cleanSpaces === 'boolean') cleanSpaces.value = prefs.cleanSpaces
      if (typeof prefs.cleanUnderscore === 'boolean') cleanUnderscore.value = prefs.cleanUnderscore
      if (typeof prefs.galleryShowMetadata === 'boolean') { galleryMetadata.value = prefs.galleryShowMetadata; window.localStorage.setItem('galleryShowMetadata', String(prefs.galleryShowMetadata)) }
      if (Array.isArray(prefs.tabOrder) && prefs.tabOrder.length > 0) {
        tabOrder.value = [...prefs.tabOrder]
        window.localStorage.setItem('tabOrder', JSON.stringify(prefs.tabOrder))
      }
      // Ollama 설정 복원
      if (prefs.ollamaUrl) { ollamaUrl.value = prefs.ollamaUrl; window.localStorage.setItem('ollamaUrl', prefs.ollamaUrl) }
      if (prefs.ollamaModel) { ollamaModel.value = prefs.ollamaModel; window.localStorage.setItem('ollamaModel', prefs.ollamaModel) }
      if (typeof prefs.ollamaUnloadOnGen === 'boolean') { ollamaUnloadOnGen.value = prefs.ollamaUnloadOnGen; window.localStorage.setItem('ollamaUnloadOnGen', String(prefs.ollamaUnloadOnGen)) }
    } catch {}
  })
})
function setBlockMode() {
  window.localStorage.setItem('tagBlockMode', String(defaultBlockMode.value))
  console.log('[Settings] Block mode set to:', defaultBlockMode.value)
}

const defaultOrder = ['T2I','I2I','Inpaint','Event Gen','Search','Batch / Upscale','Gallery','XYZ Plot','PNG Info','Favorites','Settings']
function _loadTabOrder() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0) return saved
  } catch {}
  return [...defaultOrder]
}
const tabOrder = ref(_loadTabOrder())
let dragIdx = -1

function dragStart(i) { dragIdx = i }
function persistTabOrder() {
  window.localStorage.setItem('tabOrder', JSON.stringify(tabOrder.value))
  requestAction('save_ui_prefs', { tabOrder: tabOrder.value })
  requestAction('set_tab_order', { order: tabOrder.value })
  // TabBar에게 즉시 알림 — storage event는 같은 창 변경엔 발생 안 하므로 커스텀 이벤트 사용
  try { window.dispatchEvent(new CustomEvent('tabOrderChanged')) } catch {}
}
function dragDrop(i) {
  if (dragIdx < 0) return
  const item = tabOrder.value.splice(dragIdx, 1)[0]
  tabOrder.value.splice(i, 0, item)
  dragIdx = -1
  persistTabOrder()
}
const applyTabOrder = () => {
  persistTabOrder()
  requestAction('show_toast', { type: 'success', msg: '탭 순서가 적용되었습니다' })
}
const resetTabOrder = () => {
  tabOrder.value = [...defaultOrder]
  persistTabOrder()
}
const act = (name) => {
  // SAVE GLOBAL 시 localStorage 설정도 함께 저장
  if (name === 'save_settings') {
    requestAction('save_ui_prefs', {
      tagBlockMode: defaultBlockMode.value,
      cleanDuplicates: cleanDuplicates.value,
      cleanSpaces: cleanSpaces.value,
      cleanUnderscore: cleanUnderscore.value,
      galleryShowMetadata: galleryMetadata.value,
      tabOrder: tabOrder.value,
      // Ollama
      ollamaUrl: ollamaUrl.value,
      ollamaModel: ollamaModel.value,
      ollamaUnloadOnGen: ollamaUnloadOnGen.value,
    })
  }
  requestAction(name)
}

// 기본값 설정
const FACTORY_DEFAULTS = { steps: 20, cfg: 7, width: 1024, height: 1024, seed: '-1', denoising: 0.75, sampler: '', scheduler: '', brushSize: 20, effectStrength: 15, yoloConf: 0.25, snapRadius: 12, defaultRating: 'g', hires_enabled: false, ad_enabled: false, sam3_enabled: false, negpip_enabled: false }
const defaults = reactive({ ...FACTORY_DEFAULTS })

function saveDefaults() {
  requestAction('save_tab_defaults', { ...defaults })
}

// defaults 변경 감시 → 자동 저장 알림
let defaultsTimer = null
watch(defaults, () => {
  clearTimeout(defaultsTimer)
  defaultsTimer = setTimeout(() => {
    requestAction('save_tab_defaults', { ...defaults })
  }, 1500)
}, { deep: true })
function resetDefaults() { Object.assign(defaults, FACTORY_DEFAULTS) }

// 사이드 패널 너비 — localStorage 직접 (EditorView가 호출하는 같은 키)
const editorSidePanelWidth = ref(parseInt(window.localStorage.getItem('editorSidePanelWidth') || '280'))

// UI 크기 (전역 zoom) — App.vue가 _applyUiScale로 적용
const uiScale = ref(parseFloat(window.localStorage.getItem('ui.scale') || '1.0') || 1.0)
function onUiScaleChange() {
  const v = Math.max(0.8, Math.min(1.5, uiScale.value))
  uiScale.value = v
  try { window.localStorage.setItem('ui.scale', String(v)) } catch {}
  // 같은 창에서 즉시 반영
  try { window.dispatchEvent(new CustomEvent('uiScaleChanged', { detail: { value: v } })) } catch {}
}

// 자동화 자동 재시작 — QueuePanel에서 이쪽으로 이전
const autoResumeOnStart = ref(window.localStorage.getItem('queue.autoResumeOnStart') !== 'false')
function onAutoResumeChange() {
  try {
    window.localStorage.setItem('queue.autoResumeOnStart',
      autoResumeOnStart.value ? 'true' : 'false')
  } catch {}
}
function onSidePanelWidthChange() {
  window.localStorage.setItem('editorSidePanelWidth', String(editorSidePanelWidth.value))
  // EditorView가 storage 이벤트 듣고 즉시 반영
}

const t2iSynced = ref(false)
async function syncFromT2I() {
  const { useWidgetStore } = await import('../stores/widgetStore.js')
  const store = useWidgetStore()
  const w = store.widgets
  defaults.steps = parseInt(w.steps_input) || defaults.steps
  defaults.cfg = parseFloat(w.cfg_input) || defaults.cfg
  defaults.width = parseInt(w.width_input) || defaults.width
  defaults.height = parseInt(w.height_input) || defaults.height
  defaults.seed = w.seed_input || defaults.seed
  defaults.sampler = w.sampler_combo || defaults.sampler
  defaults.scheduler = w.scheduler_combo || defaults.scheduler
  t2iSynced.value = true
  setTimeout(() => { t2iSynced.value = false }, 3000)
}

// Ollama
const ollamaUrl = ref(window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434')
const ollamaModel = ref(window.localStorage.getItem('ollamaModel') || 'gemma3:4b')
const ollamaModels = ref([])
const ollamaUnloadOnGen = ref(window.localStorage.getItem('ollamaUnloadOnGen') === 'true')

function saveOllamaSettings() {
  window.localStorage.setItem('ollamaUrl', ollamaUrl.value)
  window.localStorage.setItem('ollamaModel', ollamaModel.value)
  window.localStorage.setItem('ollamaUnloadOnGen', String(ollamaUnloadOnGen.value))
  // ui_prefs.json에도 즉시 반영 → Python start_generation이 읽어 언로드 판단
  requestAction('save_ui_prefs', {
    ollamaUrl: ollamaUrl.value,
    ollamaModel: ollamaModel.value,
    ollamaUnloadOnGen: ollamaUnloadOnGen.value,
  })
}

async function testOllama() {
  const { getBackend } = await import('../bridge.js')
  const backend = await getBackend()
  if (backend.ollamaListModels) {
    backend.ollamaListModels(ollamaUrl.value, (json) => {
      try {
        const models = JSON.parse(json)
        ollamaModels.value = models
        if (models.length > 0) {
          requestAction('show_toast', { type: 'success', msg: `Ollama 연결 성공! ${models.length}개 모델 발견` })
          // 현재 선택 모델이 목록에 없으면 첫번째로 설정
          if (!models.includes(ollamaModel.value)) {
            ollamaModel.value = models[0]
            saveOllamaSettings()
          }
        } else {
          requestAction('show_toast', { type: 'info', msg: 'Ollama 연결됨 — 설치된 모델 없음' })
        }
      } catch {
        requestAction('show_toast', { type: 'error', msg: 'Ollama 연결 실패' })
      }
    })
  }
}
function loadOllamaModels() { testOllama() }
</script>

<style scoped>
.settings-workspace { height: 100%; display: flex; background: var(--bg-primary); }

/* Navigation */
.settings-nav {
  width: 240px; background: var(--bg-secondary); border-right: 1px solid var(--border);
  padding: 24px 12px; display: flex; flex-direction: column; gap: 4px;
}
.nav-header { font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 2px; padding: 0 12px 12px; }
.settings-search-wrap { position: relative; padding: 0 12px 12px; }
.settings-search {
  width: 100%; padding: 7px 28px 7px 10px;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); font-size: 11px; outline: none;
  font-family: inherit;
}
.settings-search:focus { border-color: var(--accent); }
.search-clear {
  position: absolute; right: 16px; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 12px; padding: 0 4px;
}
.search-clear:hover { color: #f87171; }
.nav-empty { padding: 12px; font-size: 11px; color: var(--text-muted); text-align: center; font-style: italic; }
.nav-item {
  height: 44px; padding: 0 16px; border: none; background: transparent;
  border-radius: var(--radius-base); display: flex; align-items: center; gap: 12px;
  cursor: pointer; transition: var(--transition);
}
.nav-item .icon { font-size: 16px; opacity: 0.5; transition: var(--transition); }
.nav-item .label { font-size: 11px; font-weight: 800; color: var(--text-muted); letter-spacing: 1px; }
.nav-item:hover { background: var(--bg-input); }
.nav-item.active { background: var(--accent-dim); }
.nav-item.active .icon { opacity: 1; }
.nav-item.active .label { color: var(--accent); }

/* Content Area */
.settings-body { flex: 1; overflow-y: auto; padding: 40px; }
.settings-content { max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }

.section-fade { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.glass-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 24px; }

.info-row { display: flex; justify-content: space-between; align-items: center; }
.desc { font-size: 12px; font-weight: 700; color: var(--text-secondary); }
.val-badge { background: var(--border); padding: 4px 12px; border-radius: var(--radius-pill); font-size: 10px; font-weight: 900; color: var(--accent); }

.input-stack { display: flex; flex-direction: column; gap: 16px; }
.input-unit { position: relative; }
.unit-label { position: absolute; left: 12px; top: -8px; background: var(--bg-primary); padding: 0 6px; font-size: 9px; font-weight: 900; color: var(--text-muted); letter-spacing: 1px; }

.toggle-grid { display: flex; flex-direction: column; gap: 8px; }
.toggle-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; background: var(--bg-input); border-radius: var(--radius-base);
  cursor: pointer; transition: var(--transition);
}
.toggle-row:hover { background: var(--bg-button); }
.toggle-row span { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.toggle-row input { width: 40px; height: 20px; accent-color: var(--accent); }

.btn-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.mt-16 { margin-top: 16px; }

.drag-list { display: flex; flex-direction: column; gap: 6px; }
.drag-item {
  display: flex; align-items: center; gap: 12px; padding: 12px 16px;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px;
  cursor: grab; transition: var(--transition);
}
.drag-item:active { cursor: grabbing; background: var(--bg-button); scale: 0.98; }
.drag-item .handle { color: var(--text-muted); }
.drag-item .name { font-size: 12px; font-weight: 800; letter-spacing: 1px; color: var(--text-primary); }

.shortcut-grid { display: flex; flex-direction: column; gap: 4px; }
.s-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 10px; border-radius: 6px;
  transition: background 0.15s;
}
.s-row:hover { background: rgba(255, 255, 255, 0.025); }
.s-row span { font-size: 13px; color: var(--text-secondary); }
.hjm-select { background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 12px; font-weight: 700; padding: 4px 10px; cursor: pointer; }
/* kbd 단축키 표시 — style.css의 .keycap 스타일 토큰을 그대로 사용
   (전역 일관성 위해 클래스 없이도 키캡 모양이 나오도록) */
kbd {
  display: inline-block;
  min-width: 22px;
  padding: 4px 10px 5px;
  margin: 0 1px;
  background: var(--keycap-bg-grad);
  border: 1px solid var(--keycap-border);
  border-bottom-width: 2px;
  border-radius: 5px;
  box-shadow: var(--keycap-shadow);
  color: var(--keycap-color);
  font-family: 'Consolas', 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.5px;
  vertical-align: middle;
}
.hint-banner {
  background: rgba(96, 165, 250, 0.08); border: 1px solid rgba(96, 165, 250, 0.3);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 16px;
  font-size: 12px; line-height: 1.6; color: var(--text-secondary);
}
.hint-banner kbd { font-size: 10px; padding: 3px 7px 4px; }
.hint-banner strong { color: var(--accent); }

/* Defaults */
.defaults-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.def-field { display: flex; flex-direction: column; gap: 3px; }
.def-field-wide { display: flex; flex-direction: column; gap: 6px; }
.def-field-wide span { font-size: 11px; color: var(--text-secondary); font-weight: 700; }
.w-slider { width: 100%; accent-color: var(--accent); cursor: pointer; }

/* UI 크기 프리셋 버튼 */
.scale-presets { display: flex; gap: 6px; margin-top: 10px; }
.scale-btn {
  flex: 1; padding: 8px 6px; background: var(--bg-input);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-secondary); font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all 0.15s; font-family: 'Consolas', monospace;
}
.scale-btn:hover { background: var(--bg-button); color: var(--text-primary); border-color: var(--text-muted); }
.scale-btn.active {
  background: var(--accent-dim); border-color: var(--accent); color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-dim);
}
.def-field span { font-size: 10px; font-weight: 700; color: var(--text-muted); }
.sync-badge { background: #4ade80; color: #000; padding: 1px 6px; border-radius: 4px; font-size: 8px; font-weight: 900; margin-left: 8px; }
.def-field input, .def-field select { padding: 8px 10px; font-size: 12px; }
.ollama-unload-row { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: var(--text-secondary); cursor: pointer; line-height: 1.4; }
.ollama-unload-row input { margin-top: 2px; accent-color: var(--accent); }

/* Ollama */
.model-select { width: 100%; padding: 10px 12px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-primary); font-size: 13px; font-weight: 600; }
.model-select:focus { border-color: var(--accent); outline: none; }

.recommend-grid { display: flex; flex-direction: column; gap: 8px; }
.rec-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-base); transition: var(--transition);
}
.rec-item:hover { border-color: #444; }
.rec-item.best { border-color: var(--accent-dim); background: rgba(250, 204, 21, 0.03); }
.rec-name { font-size: 13px; font-weight: 800; color: var(--text-primary); min-width: 120px; font-family: 'Consolas', monospace; }
.rec-item.best .rec-name { color: var(--accent); }
.rec-desc { font-size: 11px; color: var(--text-muted); text-align: right; }
.rec-note { font-size: 11px; color: var(--text-muted); line-height: 1.6; }
.rec-note code { background: var(--bg-button); padding: 2px 8px; border-radius: 4px; font-size: 11px; color: var(--accent); }
</style>
