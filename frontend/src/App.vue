<template>
  <div class="app-container">
    <header class="app-header">
      <TabBar @tab-changed="onTabChanged" />
    </header>

    <main class="main-workspace">
      <!-- Left Panel -->
      <aside class="side-panel left" v-if="showLeftPanel">
        <div class="panel-scroll">
          <PromptPanel @toggle-extend="showExtendPanel = !showExtendPanel" />
          <div class="tool-card">
            <label>Studio Tools</label>
            <div class="tool-grid">
              <button class="tool-btn" @click="action('save_settings')">SAVE</button>
              <button class="tool-btn" @click="showPresetMenu = !showPresetMenu">PRESET</button>
              <button class="tool-btn" @click="showWeightManager = true">WEIGHT</button>
              <button class="tool-btn" @click="action('ab_test')">A/B TEST</button>
            </div>
            <!-- 프리셋 서브메뉴 -->
            <div class="preset-sub" v-if="showPresetMenu">
              <button class="tool-btn" @click="action('save_preset'); showPresetMenu = false">💾 SAVE</button>
              <button class="tool-btn" @click="action('load_preset'); showPresetMenu = false">📂 LOAD</button>
              <button class="tool-btn" @click="showWcManager = true" v-if="wildcards.length">WILDCARD</button>
            </div>
          </div>

        </div>
        <div class="gen-footer">
          <div class="gen-actions">
            <button class="action-btn" :class="{ active: autoMode }" @click="autoMode = !autoMode; action('toggle_automation', { checked: autoMode })">
              {{ autoMode ? '🔄 AUTO ON' : '⏸ AUTO OFF' }}
            </button>
            <button class="action-btn highlight" @click="action('random_prompt')">🎲 RANDOM</button>
          </div>
          <!-- 자동화 설정 (AUTO ON일 때만) -->
          <div class="auto-settings" v-if="autoMode">
            <div class="auto-row">
              <label>{{ autoSettings.mode === 'count' ? '횟수' : '시간(분)' }}</label>
              <input type="number" v-model.number="autoSettings.limit" min="1" class="auto-input" />
              <select v-model="autoSettings.mode" class="auto-select">
                <option value="count">횟수</option>
                <option value="timer">시간</option>
              </select>
            </div>
            <div class="auto-row">
              <label>반복</label>
              <input type="number" v-model.number="autoSettings.repeat" min="1" max="100" class="auto-input" />
              <label>대기(초)</label>
              <input type="number" v-model.number="autoSettings.delay" min="0" step="0.5" class="auto-input" />
            </div>
            <label class="auto-check"><input type="checkbox" v-model="autoSettings.allowDupes" /><span>중복 허용</span></label>
          </div>
          <button class="btn-generate" @click="doGenerate" :disabled="isGenerating">
            {{ isGenerating ? 'GENERATING...' : autoMode ? 'START AUTOMATION' : 'GENERATE IMAGE' }}
          </button>
        </div>
      </aside>

      <!-- 반달 화살표 (좌측 패널 옆, 항상 표시) -->
      <div class="half-moon" v-if="showLeftPanel" @click="showExtendPanel = !showExtendPanel"
        :class="{ open: showExtendPanel }">
        <span>{{ showExtendPanel ? '◀' : '▶' }}</span>
      </div>

      <!-- Extended Panel — 뷰어 위에 오버레이 -->
      <transition name="slide">
        <aside class="extend-overlay" v-if="showExtendPanel && showLeftPanel">
          <div class="extend-header">
            <h3>ADVANCED SETTINGS</h3>
            <button class="close-btn" @click="showExtendPanel = false">✕</button>
          </div>
          <div class="extend-scroll">
            <!-- Parameters (기본) -->
            <div class="ext-card">
              <div class="ext-title">PARAMETERS</div>
              <div class="ext-field">
                <label>Resolution</label>
                <div class="ext-res-row">
                  <input type="number" v-model="storeWidgets.width_input" />
                  <span>×</span>
                  <input type="number" v-model="storeWidgets.height_input" />
                  <button class="ext-mini-btn" @click="action('swap_resolution')">↔</button>
                </div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Sampler</label>
                  <CustomSelect v-model="storeWidgets.sampler_combo" :options="samplerItems" placeholder="Sampler..." />
                </div>
                <div class="ext-field"><label>Scheduler</label>
                  <CustomSelect v-model="storeWidgets.scheduler_combo" :options="schedulerItems" placeholder="Scheduler..." />
                </div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets.steps_input" min="1" max="150" /></div>
                <div class="ext-field"><label>CFG</label><input type="number" v-model="storeWidgets.cfg_input" step="0.5" /></div>
                <div class="ext-field"><label>Seed</label><input type="text" v-model="storeWidgets.seed_input" /></div>
              </div>
            </div>

            <!-- Hires.fix -->
            <details class="ext-card">
              <summary class="ext-title">HIRES.FIX</summary>
              <label class="ext-check-row"><input type="checkbox" v-model="hires_enabled" /><span>Hires.fix 활성화</span></label>
              <div class="ext-field">
                <label>Upscaler</label>
                <CustomSelect v-model="storeWidgets.upscaler_combo" :options="upscalerItems" placeholder="Upscaler..." />
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Steps</label><input type="number" v-model="storeWidgets.hires_steps_input" /></div>
                <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets.hires_denoising_input" step="0.05" /></div>
              </div>
              <div class="ext-row">
                <div class="ext-field"><label>Scale</label><input type="number" v-model="storeWidgets.hires_scale_input" step="0.1" /></div>
                <div class="ext-field"><label>CFG (0=off)</label><input type="number" v-model="storeWidgets.hires_cfg_input" step="0.5" /></div>
              </div>
            </details>

            <!-- ADetailer -->
            <details class="ext-card">
              <summary class="ext-title">ADETAILER</summary>
              <label class="ext-check-row"><input type="checkbox" v-model="ad_enabled" /><span>ADetailer 활성화</span></label>
              <!-- Slot 1 -->
              <div class="ext-sub-title">Slot 1</div>
              <label class="ext-check-row"><input type="checkbox" v-model="ad_s1_enabled" /><span>Slot 1 활성화</span></label>
              <div class="ext-field"><label>Model</label>
                <input type="text" v-model="storeWidgets._ad_s1_model" placeholder="face_yolov8n.pt" /></div>
              <div class="ext-field"><label>Prompt</label>
                <input type="text" v-model="storeWidgets._ad_s1_prompt" placeholder="ADetailer prompt..." /></div>
              <div class="ext-row">
                <div class="ext-field"><label>Confidence</label><input type="number" v-model="storeWidgets._ad_s1_confidence" step="0.05" /></div>
                <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets._ad_s1_denoise" step="0.05" /></div>
                <div class="ext-field"><label>Mask Blur</label><input type="number" v-model="storeWidgets._ad_s1_mask_blur" /></div>
              </div>
              <!-- Slot 2 -->
              <details class="ext-sub">
                <summary>Slot 2</summary>
                <label class="ext-check-row"><input type="checkbox" v-model="ad_s2_enabled" /><span>Slot 2 활성화</span></label>
                <div class="ext-field"><label>Model</label>
                  <input type="text" v-model="storeWidgets._ad_s2_model" placeholder="hand_yolov8n.pt" /></div>
                <div class="ext-field"><label>Prompt</label>
                  <input type="text" v-model="storeWidgets._ad_s2_prompt" placeholder="Slot 2 prompt..." /></div>
                <div class="ext-row">
                  <div class="ext-field"><label>Confidence</label><input type="number" v-model="storeWidgets._ad_s2_confidence" step="0.05" /></div>
                  <div class="ext-field"><label>Denoise</label><input type="number" v-model="storeWidgets._ad_s2_denoise" step="0.05" /></div>
                </div>
              </details>
            </details>

            <!-- NegPiP -->
            <div class="ext-card">
              <label class="ext-check-row">
                <input type="checkbox" v-model="extWidgets.negpip_enabled" />
                <span class="ext-title" style="margin:0">NegPiP 확장</span>
              </label>
              <div class="ext-hint">(keyword:-1.0) 네거티브 가중치 문법</div>
            </div>

            <!-- 조건부 프롬프트 -->
            <details class="ext-card">
              <summary class="ext-title">CONDITIONAL PROMPTS</summary>
              <label class="ext-check-row">
                <input type="checkbox" v-model="extWidgets.cond_enabled" />
                <span>조건부 프롬프트 활성화</span>
              </label>
              <label class="ext-check-row">
                <input type="checkbox" v-model="extWidgets.cond_prevent_dupe" />
                <span>중복 태그 방지</span>
              </label>
              <div class="ext-field" v-if="extWidgets.cond_enabled">
                <label style="color: #4ade80;">Positive Rules</label>
                <textarea v-model="extWidgets.cond_pos_rules" class="cond-textarea"
                  placeholder="IF tag EXISTS → ADD target TO main&#10;한 줄에 하나씩"></textarea>
              </div>
              <div class="ext-field" v-if="extWidgets.cond_enabled">
                <label style="color: #f87171;">Negative Rules</label>
                <textarea v-model="extWidgets.cond_neg_rules" class="cond-textarea"
                  placeholder="IF tag EXISTS → ADD target TO negative&#10;한 줄에 하나씩"></textarea>
              </div>
            </details>

            <!-- LoRA Stack -->
            <div class="ext-card">
              <div class="ext-title">LoRA STACK</div>
              <div class="lora-empty" v-if="loraStack.length === 0">
                LoRA Manager에서 추가하세요
              </div>
              <div v-for="(lora, i) in loraStack" :key="i" class="lora-block">
                <label class="lora-check"><input type="checkbox" v-model="lora.enabled" /></label>
                <div class="lora-name">{{ lora.name }}</div>
                <input type="range" min="-100" max="200" v-model.number="lora.weight" class="lora-slider" />
                <span class="lora-weight">{{ (lora.weight / 100).toFixed(2) }}</span>
                <button class="lora-remove" @click="loraStack.splice(i, 1)">✕</button>
              </div>
              <button class="ext-add-btn" @click="action('open_lora_manager')">+ ADD LoRA</button>
            </div>
          </div>
        </aside>
      </transition>

      <!-- Center: Viewport + EXIF Bar -->
      <section class="viewport-area">
        <div class="viewport-main">
          <router-view v-slot="{ Component }">
            <keep-alive>
              <component :is="Component"
                :image-url="currentImage"
                :resolution="resolution"
                :seed="seed"
                :status="status"
              />
            </keep-alive>
          </router-view>
        </div>
        <!-- EXIF Info Bar (Positive / Negative / Parameters 3탭) -->
        <div class="exif-bar" v-if="showLeftPanel && currentImage">
          <div class="exif-tabs">
            <button v-for="tab in exifTabs" :key="tab.id" class="exif-tab"
              :class="{ active: activeExifTab === tab.id }" @click="activeExifTab = tab.id">
              {{ tab.label }}
            </button>
          </div>
          <div class="exif-content">{{ exifContent }}</div>
        </div>
      </section>

      <!-- Right: History -->
      <aside class="side-panel right" v-if="showLeftPanel">
        <div class="hist-header">
          <h3>HISTORY</h3>
          <span class="count-badge">{{ historyImages.length }}</span>
        </div>
        <button class="hist-nav-btn" @click="histPage = Math.max(0, histPage - 1)" :disabled="histPage <= 0">▲</button>
        <div class="hist-scroll">
          <div v-for="img in visibleHistory" :key="img" class="hist-card"
            @click="selectHistoryImage(img)"
            @contextmenu.prevent="showHistoryMenu($event, img)"
            :class="{ selected: currentImage === img }"
            draggable="true" @dragstart="onDragStart($event, img)"
          >
            <img :src="'file:///' + img" loading="lazy" />
          </div>
        </div>
        <button class="hist-nav-btn" @click="histPage++" :disabled="(histPage + 1) * histPerPage >= historyImages.length">▼</button>

        <transition name="pop">
          <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="ctxMenuStyle">
            <div class="ctx-item" @click="ctxAddFavorite">⭐ ADD TO FAVORITES</div>
            <div class="ctx-item" @click="ctxSendI2I">🖼️ SEND TO I2I</div>
            <div class="ctx-item" @click="ctxSendInpaint">🎨 SEND TO INPAINT</div>
            <div class="ctx-item" @click="ctxSendEditor">✏️ SEND TO EDITOR</div>
            <div class="ctx-item" @click="ctxCompare('before')">🔍 COMPARE (BEFORE)</div>
            <div class="ctx-item" @click="ctxCompare('after')">🔍 COMPARE (AFTER)</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item" @click="ctxCopyPath">📋 COPY PATH</div>
            <div class="ctx-item delete" @click="ctxDelete">🗑️ DELETE</div>
          </div>
        </transition>
      </aside>
    </main>

    <div class="global-progress" v-if="isGenerating">
      <div class="progress-fill" :style="{ width: progressVal + '%' }"></div>
    </div>

    <QueuePanel />

    <!-- VRAM 게이지 (하단 고정) -->
    <div class="vram-bar" v-if="vramInfo.total > 0">
      <div class="vram-fill" :style="{ width: vramInfo.pct + '%' }" :class="vramClass"></div>
      <span class="vram-text">VRAM {{ vramInfo.used }}GB / {{ vramInfo.total }}GB ({{ vramInfo.pct }}%)</span>
    </div>

    <!-- Weight Manager Modal -->
    <transition name="fade">
      <div v-if="showWeightManager" class="wm-overlay" @click.self="showWeightManager = false">
        <div class="wm-modal">
          <div class="wm-header">
            <h3>GLOBAL TAG WEIGHTS</h3>
            <span class="wm-desc">등록된 태그는 어디서든 자동으로 지정 가중치가 적용됩니다</span>
            <button class="close-btn" @click="showWeightManager = false">✕</button>
          </div>
          <div class="wm-body">
            <div v-for="(w, i) in globalWeights" :key="i" class="wm-row">
              <input v-model="w.tag" placeholder="태그명..." class="wm-tag-input" />
              <input type="range" min="50" max="200" v-model.number="w.weight" class="wm-slider" />
              <span class="wm-val">{{ (w.weight / 100).toFixed(2) }}</span>
              <button class="wm-rm" @click="globalWeights.splice(i, 1)">✕</button>
            </div>
            <button class="wm-add" @click="globalWeights.push({ tag: '', weight: 100 })">+ ADD TAG WEIGHT</button>
          </div>
          <div class="wm-footer">
            <button class="wm-save" @click="saveGlobalWeights">💾 SAVE</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Wildcard Manager Modal -->
    <transition name="fade">
      <div v-if="showWcManager" class="wc-overlay" @click.self="showWcManager = false">
        <div class="wc-modal">
          <div class="wc-modal-header">
            <h3>WILDCARD MANAGER</h3>
            <span class="wc-path">wildcards/</span>
            <button class="wc-new-btn" @click="createNewWildcard">+ NEW</button>
            <button class="close-btn" @click="showWcManager = false">✕</button>
          </div>
          <div class="wc-modal-body">
            <!-- 파일 목록 -->
            <div class="wc-sidebar">
              <div v-for="wc in wildcards" :key="wc.name" class="wc-file-item"
                :class="{ active: selectedWc === wc.name }" @click="selectWildcard(wc.name)">
                <span class="wc-fname" @dblclick.stop="renameWildcard(wc.name)">{{ wc.name }}</span>
                <span class="wc-file-count">{{ wc.tags.length }}</span>
                <button class="wc-del" @click.stop="deleteWildcard(wc.name)">✕</button>
              </div>
            </div>
            <!-- 편집 영역 -->
            <div class="wc-content">
              <template v-if="selectedWcData">
                <div class="wc-content-header">
                  <h4>{{ selectedWc }}</h4>
                  <span class="wc-syntax">사용문법: <code>{{'__' + selectedWc + '__'}}</code></span>
                  <button class="wc-copy-btn" @click="copyWcSyntax">📋 COPY</button>
                </div>
                <!-- 블록 뷰: 한 줄 = 하나의 블록 -->
                <div class="wc-blocks">
                  <div v-for="(line, li) in wcEditLines" :key="li" class="wc-block-row">
                    <span class="wc-block-idx">{{ li + 1 }}</span>
                    <input v-model="wcEditLines[li]" class="wc-block-input" @keydown.enter="addWcLine(li)" />
                    <button class="wc-block-use" @click="useWcLine(li)" title="프롬프트에 삽입">USE</button>
                    <button class="wc-block-rm" @click="wcEditLines.splice(li, 1)">✕</button>
                  </div>
                  <button class="wc-add-line" @click="wcEditLines.push('')">+ 줄 추가</button>
                </div>
                <!-- 삽입 옵션 -->
                <div class="wc-insert-bar">
                  <span class="wc-insert-label">삽입 위치:</span>
                  <select v-model="wcInsertTarget" class="wc-insert-sel">
                    <option value="main">Main Tags</option>
                    <option value="prefix">Prefix</option>
                    <option value="suffix">Suffix</option>
                    <option value="clipboard">클립보드</option>
                  </select>
                  <button class="wc-save-btn" @click="saveCurrentWildcard">💾 SAVE</button>
                </div>
              </template>
              <div v-else class="wc-empty">좌측에서 와일드카드를 선택하거나 NEW를 클릭하세요</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Global Toast Notifications -->
    <transition-group name="toast" tag="div" class="toast-container">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type" @click="removeToast(t.id)">
        <span class="toast-icon">{{ t.type === 'error' ? '⚠' : t.type === 'success' ? '✓' : 'ℹ' }}</span>
        {{ t.msg }}
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { initBridge, onBackendEvent, getBackend } from './bridge.js'
import { requestAction, useWidgetStore } from './stores/widgetStore.js'

const wStore = useWidgetStore()
const storeWidgets = wStore.widgets
const samplerItems = computed(() => wStore.getProperty('sampler_combo', 'items') || [])
const schedulerItems = computed(() => wStore.getProperty('scheduler_combo', 'items') || [])
const upscalerItems = computed(() => wStore.getProperty('upscaler_combo', 'items') || [])

// Hires/ADetailer 체크박스 (proxy 연동)
const hires_enabled = computed({ get: () => storeWidgets.hires_options_group === 'true', set: v => { storeWidgets.hires_options_group = v ? 'true' : 'false' } })
const ad_enabled = computed({ get: () => storeWidgets.adetailer_group === 'true', set: v => { storeWidgets.adetailer_group = v ? 'true' : 'false' } })
const ad_s1_enabled = computed({ get: () => storeWidgets.ad_slot1_group === 'true', set: v => { storeWidgets.ad_slot1_group = v ? 'true' : 'false' } })
const ad_s2_enabled = computed({ get: () => storeWidgets.ad_slot2_group === 'true', set: v => { storeWidgets.ad_slot2_group = v ? 'true' : 'false' } })
import PromptPanel from './components/PromptPanel.vue'
import CustomSelect from './components/CustomSelect.vue'
import TabBar from './components/TabBar.vue'
import QueuePanel from './components/QueuePanel.vue'

const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('')
const isGenerating = ref(false)
const progressVal = ref(0)
const showLeftPanel = ref(true)
const showExtendPanel = ref(false)
const historyImages = ref([])
const histPage = ref(0)
const histPerPage = 5

// EXIF
const activeExifTab = ref('positive')
const exifTabs = [
  { id: 'positive', label: 'Positive' },
  { id: 'negative', label: 'Negative' },
  { id: 'params', label: 'Parameters' },
]
const currentExif = ref({ prompt: '', negative: '', raw: '' })
const exifContent = computed(() => {
  if (activeExifTab.value === 'positive') return currentExif.value.prompt || 'No EXIF data'
  if (activeExifTab.value === 'negative') return currentExif.value.negative || ''
  return currentExif.value.raw || ''
})

const autoMode = ref(false)
const vramInfo = ref({ used: 0, total: 0, pct: 0 })
const vramClass = computed(() => vramInfo.value.pct > 90 ? 'critical' : vramInfo.value.pct > 70 ? 'warn' : 'ok')
const autoSettings = reactive({ mode: 'count', limit: 10, repeat: 1, delay: 1.0, allowDupes: false })

// Toast 알림 시스템
const toasts = ref([])
let toastId = 0
function addToast(type, msg) {
  const id = toastId++
  toasts.value.push({ id, type, msg })
  setTimeout(() => removeToast(id), 5000)
}
function removeToast(id) { toasts.value = toasts.value.filter(t => t.id !== id) }

// Extended panel state (NegPiP/조건부만 로컬)
const extWidgets = reactive({
  negpip_enabled: false,
  cond_enabled: false, cond_prevent_dupe: true,
  cond_pos_rules: '', cond_neg_rules: '',
})
const loraStack = reactive([])

// LoRA 추가 함수 (Python에서 호출)
function addLoraToStack(name, weight) {
  const existing = loraStack.find(l => l.name === name)
  if (existing) { existing.weight = Math.round(weight * 100); existing.enabled = true }
  else loraStack.push({ name, weight: Math.round(weight * 100), enabled: true })
}

// History pagination
const visibleHistory = computed(() => {
  const start = histPage.value * histPerPage
  return historyImages.value.slice(start, start + histPerPage)
})

// Context menu (화면 밖 방지)
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const ctxMenuStyle = computed(() => {
  const menuW = 210, menuH = 250
  let x = ctxMenu.value.x, y = ctxMenu.value.y
  if (x + menuW > window.innerWidth) x = window.innerWidth - menuW - 10
  if (y + menuH > window.innerHeight) y = window.innerHeight - menuH - 10
  if (x < 0) x = 10
  if (y < 0) y = 10
  return { top: y + 'px', left: x + 'px' }
})

const wildcards = ref([])
const showPresetMenu = ref(false)
const showWeightManager = ref(false)
const globalWeights = reactive([])  // [{tag, weight}]

function saveGlobalWeights() {
  const valid = globalWeights.filter(w => w.tag.trim())
  action('save_global_weights', { weights: valid })
  showWeightManager.value = false
}

// 프롬프트에 글로벌 가중치 적용
function applyGlobalWeights(text) {
  if (!globalWeights.length) return text
  let result = text
  for (const w of globalWeights) {
    if (!w.tag.trim()) continue
    const tag = w.tag.trim()
    const weight = (w.weight / 100).toFixed(2)
    if (weight === '1.00') continue
    // 이미 가중치가 있으면 교체, 없으면 추가
    const regex = new RegExp(`\\(${tag.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}:[\\d.]+\\)`, 'gi')
    if (regex.test(result)) {
      result = result.replace(regex, `(${tag}:${weight})`)
    } else {
      const plain = new RegExp(`(?<![:(])\\b${tag.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}\\b(?![:\\)])`, 'gi')
      result = result.replace(plain, `(${tag}:${weight})`)
    }
  }
  return result
}
const showWcManager = ref(false)
const selectedWc = ref('')
const selectedWcData = computed(() => wildcards.value.find(w => w.name === selectedWc.value) || null)
const wcEditLines = ref([])
const wcInsertTarget = ref('main')

function selectWildcard(name) {
  selectedWc.value = name
  const wc = wildcards.value.find(w => w.name === name)
  wcEditLines.value = wc ? [...wc.tags] : []
}

async function saveCurrentWildcard() {
  if (!selectedWc.value) return
  const bk = await getBackend()
  const content = wcEditLines.value.join('\n')
  bk.saveWildcard(selectedWc.value + '.txt', content, (json) => {
    try { const r = JSON.parse(json); if (r.ok) addToast('success', '와일드카드 저장됨') } catch {}
  })
  // 로컬 업데이트
  const wc = wildcards.value.find(w => w.name === selectedWc.value)
  if (wc) wc.tags = wcEditLines.value.filter(l => l.trim())
}

async function createNewWildcard() {
  const name = prompt('새 와일드카드 이름:')
  if (!name) return
  const bk = await getBackend()
  bk.saveWildcard(name + '.txt', '', () => {
    wildcards.value.push({ name, file: name + '.txt', tags: [] })
    selectedWc.value = name; wcEditLines.value = []
  })
}

async function deleteWildcard(name) {
  if (!confirm(`"${name}" 와일드카드를 삭제할까요?`)) return
  const bk = await getBackend()
  bk.deleteWildcard(name, () => {
    wildcards.value = wildcards.value.filter(w => w.name !== name)
    if (selectedWc.value === name) { selectedWc.value = ''; wcEditLines.value = [] }
  })
}

async function renameWildcard(oldName) {
  const newName = prompt('새 이름:', oldName)
  if (!newName || newName === oldName) return
  const bk = await getBackend()
  bk.renameWildcard(oldName, newName, () => {
    const wc = wildcards.value.find(w => w.name === oldName)
    if (wc) { wc.name = newName; wc.file = newName + '.txt' }
    if (selectedWc.value === oldName) selectedWc.value = newName
  })
}

function useWcLine(idx) {
  const tag = wcEditLines.value[idx]
  if (!tag) return
  if (wcInsertTarget.value === 'clipboard') {
    navigator.clipboard?.writeText(tag)
    addToast('info', '클립보드에 복사됨')
  } else {
    const targetMap = { main: 'main_prompt_text', prefix: 'prefix_prompt_text', suffix: 'suffix_prompt_text' }
    const key = targetMap[wcInsertTarget.value] || 'main_prompt_text'
    const cur = storeWidgets[key] || ''
    storeWidgets[key] = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
  }
}

function addWcLine(afterIdx) { wcEditLines.value.splice(afterIdx + 1, 0, '') }

function copyWcSyntax() {
  navigator.clipboard?.writeText(`__${selectedWc.value}__`)
  addToast('info', '문법 복사됨')
}

function action(name, payload = {}) { requestAction(name, payload) }

function insertWildcardTag(tag) {
  const cur = storeWidgets.main_prompt_text || ''
  storeWidgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
}

function doGenerate() {
  // 글로벌 가중치 적용
  if (globalWeights.length > 0) {
    const cur = storeWidgets.main_prompt_text || ''
    const weighted = applyGlobalWeights(cur)
    if (weighted !== cur) storeWidgets.main_prompt_text = weighted
  }
  // LoRA Stack
  const activeLoras = loraStack.filter(l => l.enabled)
  if (activeLoras.length > 0) {
    const loraText = activeLoras.map(l => `<lora:${l.name}:${(l.weight/100).toFixed(2)}>`).join(', ')
    requestAction('set_lora_text', { lora_text: loraText })
  }
  action('generate')
}

function showHistoryMenu(e, path) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function hideCtxMenu() { ctxMenu.value.show = false }
const ctxAddFavorite = () => { action('add_favorite', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendI2I = () => { action('send_to_i2i', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendInpaint = () => { action('send_to_inpaint', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxSendEditor = () => { action('send_to_editor', { path: ctxMenu.value.path }); hideCtxMenu() }
const ctxCompare = (slot) => { action('send_to_compare', { path: ctxMenu.value.path, slot }); hideCtxMenu() }
const ctxCopyPath = () => { navigator.clipboard?.writeText(ctxMenu.value.path); hideCtxMenu() }
const ctxDelete = () => { action('delete_image', { path: ctxMenu.value.path }); hideCtxMenu() }

async function selectHistoryImage(path) {
  currentImage.value = path
  const img = new Image()
  img.onload = () => { resolution.value = `${img.naturalWidth} × ${img.naturalHeight}` }
  img.src = 'file:///' + path
  // EXIF 로드
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => {
      try {
        const d = JSON.parse(json)
        currentExif.value = { prompt: d.prompt || '', negative: d.negative || '', raw: d.raw || '' }
      } catch {}
    })
  }
}

// 드래그 앤 드롭 지원
function onDragStart(e, path) {
  e.dataTransfer.setData('text/plain', path)
  e.dataTransfer.effectAllowed = 'copy'
}

function onTabChanged(tabName) {
  showLeftPanel.value = ['t2i', 'i2i', 'inpaint'].includes(tabName)
  showExtendPanel.value = false
  hideCtxMenu()
}

async function loadHistory() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try { historyImages.value = JSON.parse(json).slice(0, 100) } catch {}
    })
  }
}

import { useRouter } from 'vue-router'
const router = useRouter()

onMounted(async () => {
  await initBridge()
  // History는 앱 시작 시 비어있음 — 생성된 이미지만 추가됨
  document.addEventListener('click', hideCtxMenu)
  document.addEventListener('wheel', (e) => { if (e.ctrlKey) e.preventDefault() }, { passive: false })
  // 브라우저 기본 우클릭 메뉴 전역 차단
  document.addEventListener('contextmenu', (e) => { e.preventDefault() })
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'g') { e.preventDefault(); action('generate') }
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); action('save_settings') }
    if (e.key === 'F5') { e.preventDefault(); loadHistory() }
  })

  onBackendEvent('tabChanged', (tabId) => {
    const targetPath = tabId === 't2i' ? '/' : `/${tabId}`
    router.push(targetPath)
    onTabChanged(tabId)
  })

  onBackendEvent('imageGenerated', (data) => {
    const parsed = JSON.parse(data)
    currentImage.value = parsed.path
    resolution.value = `${parsed.width} × ${parsed.height}`
    seed.value = String(parsed.seed)
    isGenerating.value = false
    status.value = ''
    if (parsed.path) {
      historyImages.value.unshift(parsed.path)
      if (historyImages.value.length > 100) historyImages.value.pop()
      histPage.value = 0
    }
  })
  onBackendEvent('generationStarted', () => { isGenerating.value = true; progressVal.value = 0 })
  onBackendEvent('generationProgress', (step, total) => {
    progressVal.value = Math.round(step / total * 100)
    status.value = `Generating... ${step}/${total}`
  })
  onBackendEvent('generationError', (msg) => { isGenerating.value = false; status.value = `Error: ${msg}` })

  // 글로벌 가중치 로드
  onBackendEvent('globalWeightsLoaded', (json) => {
    try { const d = JSON.parse(json); globalWeights.splice(0); d.forEach(w => globalWeights.push(w)) } catch {}
  })

  // 와일드카드 로드
  const _bk = await getBackend()
  if (_bk.getWildcardTree) _bk.getWildcardTree((json) => { try { wildcards.value = JSON.parse(json) } catch {} })

  // VRAM 실시간 업데이트
  onBackendEvent('vramUpdated', (json) => { try { vramInfo.value = JSON.parse(json) } catch {} })

  // Global Toast 알림 (Python → Vue)
  onBackendEvent('showNotification', (type, msg) => { addToast(type, msg) })

  // 에러도 Toast로 표시
  onBackendEvent('generationError', (msg) => { addToast('error', msg) })

  // LoRA 추가 이벤트 (Python lora_manager → Vue)
  onBackendEvent('loraInserted', (json) => {
    try {
      const d = JSON.parse(json)
      addLoraToStack(d.name, d.weight || 0.8)
      showExtendPanel.value = true
    } catch {}
  })
})
</script>

<style scoped>
.app-container { width: 100%; height: 100vh; display: flex; flex-direction: column; background: var(--bg-primary); }
.app-header { height: 60px; display: flex; align-items: center; justify-content: center; background: var(--bg-primary); border-bottom: 1px solid var(--border); z-index: 100; }
.main-workspace { flex: 1; display: flex; overflow: hidden; position: relative; }

.side-panel { width: 360px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); z-index: 10; }
.side-panel.right { width: 220px; border-right: none; border-left: 1px solid var(--border); }
.panel-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }

/* 반달 화살표 */
.half-moon {
  position: absolute; left: 360px; top: 50%; transform: translateY(-50%);
  width: 20px; height: 60px; background: var(--bg-secondary);
  border: 1px solid var(--border); border-left: none;
  border-radius: 0 30px 30px 0; cursor: pointer; z-index: 55;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 10px; transition: all 0.2s;
}
.half-moon:hover { background: var(--bg-card); color: var(--accent); width: 24px; }
.half-moon.open { background: var(--accent-dim); color: var(--accent); left: 680px; }

/* Extended Panel Overlay */
.extend-overlay {
  position: absolute; left: 360px; top: 0; bottom: 0; width: 320px;
  background: var(--bg-secondary); border-right: 1px solid var(--border);
  z-index: 50; display: flex; flex-direction: column;
  box-shadow: 8px 0 32px rgba(0,0,0,0.5);
}
.extend-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.extend-header h3 { font-size: 11px; letter-spacing: 2px; color: var(--text-muted); }
.close-btn { background: none; border: none; color: var(--text-muted); font-size: 16px; cursor: pointer; }
.close-btn:hover { color: #f87171; }
.extend-scroll { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }

.ext-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 12px; }
.ext-title { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 1px; margin-bottom: 10px; cursor: pointer; }
.ext-field { margin-bottom: 8px; }
.ext-field label { font-size: 9px; color: var(--text-muted); font-weight: 700; display: block; margin-bottom: 3px; }
.ext-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.ext-sub { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.ext-sub summary { font-size: 10px; color: var(--text-secondary); cursor: pointer; }
.ext-sub-title { font-size: 10px; font-weight: 800; color: var(--accent); letter-spacing: 1px; margin: 8px 0 4px; }

/* LoRA block */
.lora-block { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: var(--bg-button); border-radius: 6px; margin-bottom: 4px; }
.lora-name { flex: 1; font-size: 11px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lora-slider { width: 60px; accent-color: var(--accent); }
.lora-weight { font-size: 10px; color: var(--accent); min-width: 30px; text-align: right; font-family: monospace; }
.lora-remove { background: none; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.ext-add-btn { width: 100%; padding: 8px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; margin-top: 4px; }
.ext-res-row { display: flex; align-items: center; gap: 6px; }
.ext-res-row input { text-align: center; flex: 1; }
.ext-res-row span { color: var(--text-muted); }
.ext-mini-btn { width: 32px; height: 32px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); cursor: pointer; flex-shrink: 0; }
.ext-check-row { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-secondary); cursor: pointer; margin-bottom: 4px; white-space: nowrap; }
.ext-check-row input[type="checkbox"] { accent-color: var(--accent); }
.ext-hint { font-size: 10px; color: var(--text-muted); margin-top: 4px; }
.cond-textarea { min-height: 60px; font-size: 11px; line-height: 1.6; font-family: 'Consolas', monospace; }
.lora-check { flex-shrink: 0; }
.lora-check input { accent-color: var(--accent); }
.lora-empty { font-size: 11px; color: var(--text-muted); text-align: center; padding: 12px; }

.slide-enter-active, .slide-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(-20px); opacity: 0; }

/* Tool Card */
.tool-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 16px; }
.tool-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.tool-btn { padding: 8px 4px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; transition: var(--transition); }
.tool-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }
.tool-btn.highlight { color: var(--accent); border-color: var(--accent-dim); }
.preset-sub { display: flex; gap: 4px; margin-top: 4px; }

/* Weight Manager */
.wm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.wm-modal { width: 500px; max-height: 500px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.wm-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.wm-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.wm-desc { font-size: 9px; color: var(--text-muted); flex: 1; }
.wm-body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }
.wm-row { display: flex; align-items: center; gap: 6px; }
.wm-tag-input { flex: 1; padding: 5px 8px; font-size: 11px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); }
.wm-slider { width: 100px; accent-color: var(--accent); }
.wm-val { font-size: 11px; color: var(--accent); min-width: 35px; text-align: right; font-family: monospace; }
.wm-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 14px; }
.wm-add { width: 100%; padding: 6px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 4px; color: var(--text-muted); font-size: 10px; cursor: pointer; }
.wm-footer { padding: 10px 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }
.wm-save { padding: 7px 20px; background: var(--accent); border: none; border-radius: 6px; color: #000; font-size: 11px; font-weight: 800; cursor: pointer; }

/* Wildcard Manager Modal */
.wc-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 2000; display: flex; align-items: center; justify-content: center; }
.wc-modal { width: 700px; height: 500px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.wc-modal-header { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.wc-modal-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.wc-path { font-size: 10px; color: var(--text-muted); font-family: monospace; flex: 1; }
.wc-modal-body { flex: 1; display: flex; overflow: hidden; }
.wc-sidebar { width: 180px; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; }
.wc-file-item { padding: 6px 10px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-radius: 4px; display: flex; justify-content: space-between; }
.wc-file-item:hover { background: var(--bg-input); }
.wc-file-item.active { background: var(--accent-dim); color: var(--accent); }
.wc-file-count { font-size: 9px; color: var(--text-muted); }
.wc-content { flex: 1; overflow-y: auto; padding: 16px; }
.wc-content-header { margin-bottom: 12px; }
.wc-content-header h4 { font-size: 14px; color: var(--text-primary); }
.wc-content-header span { font-size: 10px; color: var(--text-muted); }
.wc-content-header code { background: var(--bg-input); padding: 2px 6px; border-radius: 3px; font-size: 10px; color: var(--accent); }
.wc-new-btn { padding: 4px 12px; background: var(--accent); border: none; border-radius: 4px; color: #000; font-size: 10px; font-weight: 800; cursor: pointer; }
.wc-fname { flex: 1; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.wc-del { background: none; border: none; color: #f87171; cursor: pointer; font-size: 11px; opacity: 0; transition: 0.15s; }
.wc-file-item:hover .wc-del { opacity: 1; }
.wc-syntax { font-size: 10px; color: var(--text-muted); }
.wc-syntax code { background: var(--bg-input); padding: 1px 6px; border-radius: 3px; color: var(--accent); }
.wc-copy-btn { padding: 2px 8px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--text-secondary); font-size: 9px; cursor: pointer; }
.wc-blocks { display: flex; flex-direction: column; gap: 3px; max-height: 300px; overflow-y: auto; }
.wc-block-row { display: flex; align-items: center; gap: 4px; }
.wc-block-idx { font-size: 9px; color: var(--text-muted); min-width: 20px; text-align: right; font-family: monospace; }
.wc-block-input { flex: 1; padding: 4px 8px; font-size: 11px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); }
.wc-block-use { padding: 2px 6px; background: var(--accent-dim); border: 1px solid var(--accent); border-radius: 3px; color: var(--accent); font-size: 9px; font-weight: 700; cursor: pointer; }
.wc-block-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.wc-add-line { width: 100%; padding: 4px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 3px; color: var(--text-muted); font-size: 9px; cursor: pointer; margin-top: 4px; }
.wc-insert-bar { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.wc-insert-label { font-size: 9px; color: var(--text-muted); font-weight: 700; }
.wc-insert-sel { padding: 3px 6px; font-size: 9px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 3px; color: var(--text-secondary); }
.wc-save-btn { padding: 5px 14px; background: var(--accent); border: none; border-radius: 4px; color: #000; font-size: 10px; font-weight: 800; cursor: pointer; margin-left: auto; }
.wc-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 13px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.gen-footer { padding: 12px 16px; background: var(--bg-card); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.gen-actions { display: flex; gap: 6px; }
.action-btn { flex: 1; padding: 7px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; transition: var(--transition); }
.action-btn.active { border-color: #4ade80; color: #4ade80; background: rgba(74,222,128,0.05); }
.action-btn.highlight { border-color: var(--accent-dim); color: var(--accent); }
.action-btn:hover { border-color: var(--text-muted); }
.auto-settings { display: flex; flex-direction: column; gap: 4px; padding: 8px; background: rgba(74,222,128,0.03); border: 1px solid rgba(74,222,128,0.1); border-radius: 8px; }
.auto-row { display: flex; align-items: center; gap: 4px; }
.auto-row label { font-size: 9px; color: var(--text-muted); font-weight: 700; min-width: 32px; }
.auto-input { width: 50px; padding: 4px 6px; font-size: 11px; text-align: center; }
.auto-select { width: 60px; padding: 4px; font-size: 10px; }
.auto-check { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-secondary); cursor: pointer; }
.auto-check input { accent-color: #4ade80; }
.btn-generate { width: 100%; height: 50px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 800; font-size: 14px; letter-spacing: 1px; cursor: pointer; transition: var(--transition); }
.btn-generate:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(250, 204, 21, 0.3); }
.btn-generate:disabled { opacity: 0.5; cursor: wait; }

/* Viewport */
.viewport-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #050505; }
.viewport-main { flex: 1; position: relative; overflow: hidden; }

/* EXIF Bar */
.exif-bar { flex-shrink: 0; background: #0D0D0D; border-top: 1px solid var(--border); }
.exif-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
.exif-tab { flex: 1; padding: 6px; background: transparent; border: none; color: var(--text-muted); font-size: 10px; font-weight: 700; cursor: pointer; text-align: center; border-bottom: 2px solid transparent; }
.exif-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.exif-content { padding: 6px 12px; font-size: 11px; color: var(--text-secondary); max-height: 80px; overflow-y: auto; line-height: 1.5; font-family: 'Consolas', monospace; white-space: pre-wrap; word-break: break-all; }

/* History */
.hist-header { padding: 16px; display: flex; justify-content: space-between; align-items: center; }
.hist-header h3 { font-size: 12px; letter-spacing: 2px; color: var(--text-muted); }
.count-badge { background: var(--border); padding: 2px 8px; border-radius: 10px; font-size: 10px; color: var(--text-secondary); }
.hist-nav-btn { width: 100%; padding: 4px; background: #131313; border: none; color: #484848; font-size: 12px; cursor: pointer; flex-shrink: 0; }
.hist-nav-btn:hover { background: #1A1A1A; color: #E8E8E8; }
.hist-nav-btn:disabled { opacity: 0.3; cursor: default; }
.hist-scroll { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 8px; }
.hist-card { position: relative; border-radius: var(--radius-card); overflow: hidden; border: 2px solid transparent; cursor: pointer; transition: border-color 0.15s; }
.hist-card:hover { border-color: #333; }
.hist-card.selected { border-color: var(--accent); box-shadow: 0 0 12px var(--accent-dim); }
.hist-card img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }

/* Context Menu */
.modern-ctx-menu { position: fixed; background: #181818; border: 1px solid #222; border-radius: 10px; padding: 6px; z-index: 1000; min-width: 200px; box-shadow: 0 12px 32px rgba(0,0,0,0.8); }
.ctx-item { padding: 10px 14px; font-size: 11px; font-weight: 600; color: #909090; cursor: pointer; border-radius: 6px; transition: var(--transition); }
.ctx-item:hover { background: #252525; color: #FFF; }
.ctx-item.delete { color: #f87171; }
.ctx-item.delete:hover { background: rgba(248, 113, 113, 0.1); }
.ctx-separator { height: 1px; background: #222; margin: 4px 0; }

.pop-enter-active { animation: pop 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
@keyframes pop { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }

/* VRAM Bar */
.vram-bar {
  position: fixed; bottom: 0; left: 0; right: 0; height: 22px;
  background: #080808; border-top: 1px solid var(--border); z-index: 500;
  display: flex; align-items: center;
}
.vram-fill { height: 100%; transition: width 1s ease; }
.vram-fill.ok { background: rgba(74,222,128,0.4); }
.vram-fill.warn { background: rgba(251,191,36,0.5); }
.vram-fill.critical { background: rgba(248,113,113,0.6); }
.vram-text {
  position: absolute; left: 50%; transform: translateX(-50%);
  font-size: 11px; font-weight: 800; color: #B0B0B0; letter-spacing: 0.5px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.8);
}

.global-progress { position: fixed; top: 0; left: 0; width: 100%; height: 3px; background: transparent; z-index: 1000; }
.progress-fill { height: 100%; background: var(--accent); transition: width 0.3s ease; }

/* Toast Notifications */
.toast-container { position: fixed; top: 70px; right: 20px; z-index: 2000; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
.toast {
  padding: 10px 20px; border-radius: 8px; font-size: 12px; font-weight: 600;
  color: #FFF; pointer-events: auto; cursor: pointer; min-width: 200px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5); backdrop-filter: blur(8px);
}
.toast.success { background: rgba(74, 222, 128, 0.9); color: #000; }
.toast.error { background: rgba(248, 113, 113, 0.9); color: #FFF; }
.toast.info { background: rgba(96, 165, 250, 0.9); color: #FFF; }
.toast-icon { margin-right: 8px; }
.toast-enter-active { animation: slideIn 0.3s ease; }
.toast-leave-active { animation: slideOut 0.3s ease; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideOut { from { opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
</style>
