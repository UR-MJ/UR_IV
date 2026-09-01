<template>
  <div class="i2i-root">
    <!-- 하위 탭: img2img / Refine -->
    <div class="sub-tabs">
      <button class="sub-tab" :class="{ active: subTab === 'i2i' }" @click="subTab = 'i2i'">
        IMG2IMG
      </button>
      <button class="sub-tab" :class="{ active: subTab === 'refine' }" @click="subTab = 'refine'">
        SAM3 REFINE
      </button>
    </div>

    <RefinePanel v-if="subTab === 'refine'" ref="refineRef"
      :image-path="imagePath"
      :sampler-options="samplerOptions"
      :scheduler-options="schedulerOptions"
      :checkpoint-options="checkpointOptions"
      @pick-image="triggerFileInput"
      @image-changed="p => imagePath = p"
    />

  <div class="i2i-workspace" v-show="subTab === 'i2i'">
    <!-- Left Sidebar: Settings -->
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <!-- Input Card -->
        <div class="glass-card">
          <label>Source Image</label>
          <div class="source-thumb" @click="triggerFileInput">
            <img v-if="imageSrc" :src="imageSrc" />
            <div v-else class="upload-hint">EMPTY</div>
            <div class="edit-overlay">CHANGE IMAGE</div>
          </div>
        </div>

        <div v-if="isKrea2" class="glass-card krea-card">
          <label>Identity Reference <span class="optional">OPTIONAL</span></label>
          <div class="source-thumb identity-thumb" @click="triggerReferenceInput">
            <img v-if="referenceSrc" :src="referenceSrc" />
            <div v-else class="upload-hint">SOURCE-ONLY EDIT</div>
            <div class="edit-overlay">{{ referenceSrc ? 'CHANGE REFERENCE' : 'ADD REFERENCE' }}</div>
          </div>
          <button v-if="referenceSrc" class="clear-reference" @click.stop="clearReference">REMOVE REFERENCE</button>
          <input ref="referenceFileInput" type="file" accept="image/*" hidden @change="handleReferenceSelect" />
        </div>

        <!-- Prompt Card -->
        <div class="glass-card">
          <label>Override Prompt</label>
          <textarea v-model="prompt" rows="3" placeholder="Leave empty to use T2I prompt..."></textarea>
          <template v-if="!isKrea2">
            <label class="mt-12 danger">Negative</label>
            <textarea v-model="negPrompt" rows="2" placeholder="Override negative..."></textarea>
          </template>
          <p v-else class="krea-help">Krea2 Identity Edit는 입력 이미지를 사용한 grounded unconditional 경로를 사용하므로 Negative는 적용하지 않습니다.</p>
        </div>

        <!-- Generation Params Card -->
        <div class="glass-card">
          <template v-if="isKrea2">
            <label>Identity Fidelity</label>
            <div class="premium-slider krea-slider">
              <input type="range" min="0.5" max="12" step="0.1" v-model.number="fidelity" />
              <div class="slider-display">
                <span class="val">{{ fidelity.toFixed(1) }}</span>
                <span class="label">Reference Boost</span>
              </div>
            </div>
            <p class="krea-help">높을수록 원본/identity reference 보존을 강하게 요구합니다. 기본값 4.0.</p>
          </template>
          <template v-else>
            <label>Denoising Strength</label>
            <div class="premium-slider">
              <input type="range" min="0" max="1" step="0.01" v-model.number="denoising" />
              <div class="slider-display">
                <span class="val">{{ denoising.toFixed(2) }}</span>
                <span class="label">Intensity</span>
              </div>
            </div>
          </template>

          <template v-if="!isKrea2">
            <label class="mt-12">Resize Mode</label>
            <CustomSelect v-model="resizeModeLabel" :options="resizeModeOptions" placeholder="Resize Mode" />
          </template>

          <div class="grid-2 mt-12">
            <div class="input-unit">
              <label>Width</label>
              <input v-model="width" type="number" />
            </div>
            <div class="input-unit">
              <label>Height</label>
              <input v-model="height" type="number" />
            </div>
          </div>
        </div>

        <!-- Advanced Card -->
        <details class="glass-card">
          <summary class="card-header">ADVANCED SETTINGS</summary>
          <div class="input-group mt-12">
            <label>Steps</label>
            <input type="range" min="1" :max="isKrea2 ? 80 : 100" v-model.number="activeSteps" class="modern-slider" />
            <div class="val-tag">{{ activeSteps }}</div>
          </div>
          <div class="input-group mt-12">
            <label>CFG Scale</label>
            <input type="range" min="1" :max="isKrea2 ? 10 : 20" step="0.5" v-model.number="activeCfg" class="modern-slider" />
            <div class="val-tag">{{ activeCfg }}</div>
          </div>
          <div class="input-group mt-12">
            <label>Seed (−1 = 랜덤)</label>
            <div class="seed-row">
              <input v-model="seed" type="text" class="seed-input" placeholder="-1" />
              <button class="seed-btn" @click="seed = '-1'" title="랜덤으로 초기화"><Icon name="dice" /></button>
            </div>
          </div>
        </details>
      </div>

      <div class="sidebar-footer">
        <button class="btn-generate primary" @click="generate" :disabled="!imageSrc">
          {{ !imageSrc ? 'UPLOAD IMAGE FIRST' : isKrea2 ? 'START KREA2 IDENTITY EDIT' : 'START I2I GENERATION' }}
        </button>
      </div>
    </aside>

    <!-- Main Content: Canvas -->
    <section class="canvas-area">
      <div class="drop-zone" :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true" @dragleave="isDragging = false"
        @drop.prevent="handleDrop" @click="triggerFileInput"
      >
        <transition name="scale">
          <div v-if="!imageSrc" class="drop-empty">
            <div class="icon">⤓</div>
            <h2>DRAG & DROP SOURCE</h2>
            <p>Or click to browse your local storage</p>
          </div>
          <div v-else class="preview-container">
            <img :src="imageSrc" class="main-preview" />
          </div>
        </transition>
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileSelect" />
    </section>
  </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { requestAction, getProperty, getValue } from '../stores/widgetStore.js'
import { onBackendEvent } from '../bridge.js'
import { mediaUrl } from '../utils/media.js'
import CustomSelect from '../components/CustomSelect.vue'
import RefinePanel from '../components/RefinePanel.vue'

// 하위 탭 — 마지막 선택을 기억한다
const subTab = ref(localStorage.getItem('i2i.subTab') || 'i2i')
watch(subTab, (v) => { try { localStorage.setItem('i2i.subTab', v) } catch {} })
const refineRef = ref<any>(null)

// Refine 패널 드롭다운 — t2i가 쓰는 것과 같은 위젯 property를 읽는다.
// (전용 이벤트를 새로 만들면 브리지 계약이 어긋난다 — tests/test_bridge_contract.py)
const samplerOptions = computed(
  () => ['Use same sampler', ...(getProperty('sampler_combo', 'items') || [])])
const schedulerOptions = computed(
  () => ['Use same scheduler', ...(getProperty('scheduler_combo', 'items') || [])])
const checkpointOptions = computed(
  () => getProperty('_sam3_checkpoint', 'items') || ['sam3.pt'])

const isDragging = ref(false)
const imageSrc = ref('')
const imagePath = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const referenceSrc = ref('')
const referencePath = ref('')
const referenceFileInput = ref<HTMLInputElement | null>(null)
const prompt = ref('')
const negPrompt = ref('')
const denoising = ref(0.75)
const fidelity = ref(4)
const resizeMode = ref('0')
const resizeModeOptions = ['JUST RESIZE', 'CROP AND RESIZE', 'RESIZE AND FILL', 'LATENT RESIZE']
const resizeModeLabel = computed({
  get: () => resizeModeOptions[parseInt(resizeMode.value)] || resizeModeOptions[0],
  set: (v: string) => { resizeMode.value = String(resizeModeOptions.indexOf(v)) }
})
const width = ref('1024')
const height = ref('1024')
const steps = ref(20)
const cfg = ref(7)
const kreaSteps = ref(15)
const kreaCfg = ref(1)
const seed = ref('-1')

const generationFamily = computed(() => String(getValue('generation_family_combo') || 'STANDARD').toUpperCase())
const isKrea2 = computed(() => generationFamily.value === 'KREA2')
const activeSteps = computed({
  get: () => isKrea2.value ? kreaSteps.value : steps.value,
  set: (value: number) => { if (isKrea2.value) kreaSteps.value = value; else steps.value = value },
})
const activeCfg = computed({
  get: () => isKrea2.value ? kreaCfg.value : cfg.value,
  set: (value: number) => { if (isKrea2.value) kreaCfg.value = value; else cfg.value = value },
})

function triggerFileInput() { fileInput.value?.click() }
function handleFileSelect(e: Event) { const f = (e.target as HTMLInputElement).files?.[0]; if (f) loadFile(f) }
function triggerReferenceInput() { referenceFileInput.value?.click() }
function handleReferenceSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev: ProgressEvent<FileReader>) => { referenceSrc.value = ev.target?.result as string }
  reader.readAsDataURL(file)
  referencePath.value = ((file as any).path || '').replace(/\\/g, '/')
}
function clearReference() {
  referenceSrc.value = ''
  referencePath.value = ''
  if (referenceFileInput.value) referenceFileInput.value.value = ''
}
function handleDrop(e: DragEvent) {
  isDragging.value = false
  // 파일 드롭
  const f = e.dataTransfer?.files?.[0]
  if (f) { imagePath.value = (f as any).path || ''; loadFile(f); return }
  // History에서 경로 텍스트 드롭
  const path = e.dataTransfer?.getData('text/plain')
  if (path && path.includes('/')) loadFromPath(path)
}
function loadFile(file: File) {
  const reader = new FileReader()
  reader.onload = (ev: ProgressEvent<FileReader>) => { imageSrc.value = ev.target?.result as string }
  reader.readAsDataURL(file)
  imagePath.value = ((file as any).path || '').replace(/\\/g, '/')
}

// 경로로 직접 이미지 로드 (History/Gallery에서 전송 시)
async function loadFromPath(path: string) {
  const normalized = path.replace(/\\/g, '/')
  imagePath.value = normalized
  imageSrc.value = mediaUrl(normalized)
}

onMounted(() => {
  // History/Gallery에서 send_to_i2i 시 이미지 로드 — 현재 하위 탭 쪽으로 보낸다
  onBackendEvent('i2iImageLoaded', (path: string) => {
    loadFromPath(path)
    if (subTab.value === 'refine') refineRef.value?.setImage?.(path)
  })
})

// Refine 탭으로 넘어갈 때 현재 이미지를 물려준다
watch(subTab, (v) => {
  if (v === 'refine' && imagePath.value) refineRef.value?.setImage?.(imagePath.value)
})

function generate() {
  requestAction('generate_i2i', {
    generation_family: isKrea2.value ? 'krea2' : 'standard',
    image: imagePath.value ? '' : imageSrc.value,
    image_path: imagePath.value,
    reference_image: isKrea2.value && !referencePath.value ? referenceSrc.value : '',
    reference_path: isKrea2.value ? referencePath.value : '',
    prompt: prompt.value,
    negative_prompt: negPrompt.value,
    denoising: denoising.value,
    fidelity: fidelity.value,
    resize_mode: parseInt(resizeMode.value),
    width: parseInt(width.value),
    height: parseInt(height.value),
    steps: activeSteps.value,
    cfg: activeCfg.value,
    seed: seed.value,
  })
}
</script>

<style scoped>
.i2i-root { height: 100%; display: flex; flex-direction: column; background: var(--bg-primary); min-height: 0; }
.sub-tabs {
  display: flex; gap: 4px; padding: 8px 12px 0;
  background: var(--bg-secondary); border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sub-tab {
  padding: 8px 18px; font-size: var(--fs-label); font-weight: 800; letter-spacing: 1px;
  background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-muted); cursor: pointer; transition: var(--transition);
}
.sub-tab:hover { color: var(--text-primary); }
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.i2i-root > :not(.sub-tabs) { flex: 1; min-height: 0; }

.i2i-workspace { height: 100%; display: flex; background: var(--bg-primary); }

/* Sidebar */
.sidebar {
  width: 340px; display: flex; flex-direction: column;
  background: var(--bg-secondary); border-right: 1px solid var(--border);
}
.sidebar-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.sidebar-footer { padding: 16px; background: var(--bg-card); border-top: 1px solid var(--border); }

.glass-card {
  background: rgba(255,255,255,0.02); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 14px;
}
.krea-card { border-color: rgba(167,139,250,0.35); background: rgba(124,58,237,0.06); }
.optional { margin-left: 5px; font-size: var(--fs-label); color: #a78bfa; letter-spacing: 1px; }
.identity-thumb { aspect-ratio: 2/1; }
.clear-reference {
  width: 100%; margin-top: 7px; padding: 6px; background: transparent;
  border: 1px solid rgba(248,113,113,0.3); border-radius: 5px;
  color: #f87171; font-size: var(--fs-label); font-weight: 800; cursor: pointer;
}
.krea-help { margin: 8px 0 0; color: var(--text-muted); font-size: var(--fs-label); line-height: 1.45; }
.krea-slider .val { color: #a78bfa; }

.source-thumb {
  width: 100%; aspect-ratio: 16/9; background: var(--bg-input); border-radius: var(--radius-base);
  margin-top: 8px; overflow: hidden; position: relative; cursor: pointer; border: 1px solid var(--border);
}
.source-thumb img { width: 100%; height: 100%; object-fit: cover; }
.upload-hint { height: 100%; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: var(--fs-label); font-weight: 800; letter-spacing: 2px; }
.edit-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,0.6); color: var(--accent);
  display: flex; align-items: center; justify-content: center; font-size: var(--fs-label); font-weight: 800;
  opacity: 0; transition: var(--transition);
}
.source-thumb:hover .edit-overlay { opacity: 1; }

/* Premium Slider */
.premium-slider { margin-top: 8px; }
.slider-display { display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px; }
.slider-display .val { font-size: 20px; font-weight: 900; color: var(--accent); font-family: 'Consolas', monospace; }
.slider-display .label { font-size: var(--fs-label); font-weight: 800; color: var(--text-muted); text-transform: uppercase; }

.modern-slider { appearance: none; width: 100%; height: 4px; background: var(--bg-input); border-radius: 2px; outline: none; accent-color: var(--accent); }
.val-tag { font-size: 11px; font-weight: 800; color: var(--text-secondary); text-align: right; margin-top: 4px; }
.seed-row { display: flex; gap: 6px; align-items: center; }
.seed-input {
  flex: 1; padding: 8px 10px; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: 12px; outline: none;
  font-family: 'Consolas', monospace;
}
.seed-input:focus { border-color: var(--accent); }
.seed-btn {
  padding: 8px 12px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 6px; color: var(--accent); font-size: 14px; cursor: pointer;
}
.seed-btn:hover { background: var(--bg-input); border-color: var(--accent); }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.mt-12 { margin-top: 12px; }
.danger { color: #f87171; }

.btn-generate {
  width: 100%; height: 46px; background: var(--accent); border: none;
  border-radius: var(--radius-pill); color: #000; font-weight: 900;
  font-size: 12px; letter-spacing: 1px; cursor: pointer; transition: var(--transition);
}
.btn-generate:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(250, 204, 21, 0.3); }

/* Canvas Area */
.canvas-area { flex: 1; padding: 24px; display: flex; align-items: center; justify-content: center; }
.drop-zone {
  width: 100%; height: 100%; max-width: 1200px;
  background: var(--bg-card); border: 2px dashed var(--border); border-radius: 20px;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  transition: var(--transition); position: relative;
}
.drop-zone.drag-over { border-color: var(--accent); background: var(--accent-dim); }
.drop-zone:hover { border-color: var(--text-muted); }

.drop-empty { text-align: center; }
.drop-empty .icon { font-size: 64px; color: var(--text-muted); margin-bottom: 16px; }
.drop-empty h2 { font-size: 18px; letter-spacing: 4px; color: var(--text-secondary); margin-bottom: 8px; }
.drop-empty p { font-size: 13px; color: var(--text-muted); }

.preview-container { width: 100%; height: 100%; padding: 20px; display: flex; align-items: center; justify-content: center; }
.main-preview { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 8px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }

/* Animation */
.scale-enter-active, .scale-leave-active { transition: all 0.3s ease; }
.scale-enter-from, .scale-leave-to { opacity: 0; transform: scale(0.95); }
</style>
