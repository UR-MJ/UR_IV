<template>
  <div class="i2i-view">
    <div class="image-area">
      <div class="drop-zone" :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true" @dragleave="isDragging = false"
        @drop.prevent="handleDrop" @click="triggerFileInput"
      >
        <div v-if="!imageSrc" class="drop-hint">
          <div class="icon">🖼️</div>
          <div>이미지를 드래그하거나 클릭</div>
        </div>
        <img v-else :src="imageSrc" class="preview-img" />
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileSelect" />
    </div>
    <div class="settings">
      <h3>I2I 설정</h3>

      <label class="s-label">프롬프트 (비우면 T2I 프롬프트 사용)</label>
      <textarea class="s-textarea" v-model="prompt" placeholder="프롬프트..." rows="3" />

      <label class="s-label">네거티브</label>
      <textarea class="s-textarea" v-model="negPrompt" placeholder="네거티브..." rows="2" />

      <label class="s-label">Denoising Strength</label>
      <div class="slider-row">
        <input type="range" min="0" max="1" step="0.01" v-model.number="denoising" />
        <span class="val">{{ denoising.toFixed(2) }}</span>
      </div>

      <label class="s-label">Resize Mode</label>
      <select v-model="resizeMode" class="s-select">
        <option value="0">Just resize</option>
        <option value="1">Crop and resize</option>
        <option value="2">Resize and fill</option>
        <option value="3">Just resize (latent)</option>
      </select>

      <div class="row">
        <div class="col">
          <label class="s-label">Width</label>
          <input class="s-input" v-model="width" />
        </div>
        <div class="col">
          <label class="s-label">Height</label>
          <input class="s-input" v-model="height" />
        </div>
      </div>

      <label class="s-label">Steps</label>
      <div class="slider-row">
        <input type="range" min="1" max="100" v-model.number="steps" />
        <span class="val">{{ steps }}</span>
      </div>

      <label class="s-label">CFG Scale</label>
      <div class="slider-row">
        <input type="range" min="1" max="20" step="0.5" v-model.number="cfg" />
        <span class="val">{{ cfg }}</span>
      </div>

      <label class="s-label">Seed</label>
      <div class="row">
        <input class="s-input" v-model="seed" />
        <button class="btn-sm" @click="seed = '-1'">🎲</button>
      </div>

      <button class="btn-generate" @click="generate" :disabled="!imageSrc">
        I2I 생성
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const isDragging = ref(false)
const imageSrc = ref('')
const imagePath = ref('')
const fileInput = ref(null)
const prompt = ref('')
const negPrompt = ref('')
const denoising = ref(0.75)
const resizeMode = ref('0')
const width = ref('1024')
const height = ref('1024')
const steps = ref(20)
const cfg = ref(7)
const seed = ref('-1')

function triggerFileInput() { fileInput.value?.click() }
function handleFileSelect(e) { const f = e.target.files?.[0]; if (f) loadFile(f) }
function handleDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) {
    imagePath.value = f.path || ''
    loadFile(f)
  }
}
function loadFile(file) {
  const reader = new FileReader()
  reader.onload = (ev) => { imageSrc.value = ev.target.result }
  reader.readAsDataURL(file)
}

function generate() {
  requestAction('generate_i2i', {
    image: imageSrc.value,
    image_path: imagePath.value,
    prompt: prompt.value,
    negative_prompt: negPrompt.value,
    denoising: denoising.value,
    resize_mode: parseInt(resizeMode.value),
    width: parseInt(width.value),
    height: parseInt(height.value),
    steps: steps.value,
    cfg: cfg.value,
    seed: seed.value,
  })
}
</script>

<style scoped>
.i2i-view { height: 100%; display: flex; }
.image-area { flex: 1; display: flex; align-items: center; justify-content: center; padding: 16px; }
.drop-zone {
  width: 100%; height: 100%; border: 2px dashed #1A1A1A; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  transition: border-color 0.15s; overflow: hidden;
}
.drop-zone.drag-over { border-color: #E2B340; }
.drop-zone:hover { border-color: #333; }
.drop-hint { text-align: center; color: #484848; }
.drop-hint .icon { font-size: 48px; margin-bottom: 8px; opacity: 0.3; }
.drop-hint div { font-size: 13px; }
.preview-img { max-width: 100%; max-height: 100%; object-fit: contain; }

.settings {
  width: 280px; padding: 16px; border-left: 1px solid #1A1A1A;
  display: flex; flex-direction: column; gap: 6px; overflow-y: auto;
}
.settings h3 { color: #E8E8E8; font-size: 14px; margin: 0 0 8px; }
.s-label { color: #585858; font-size: 11px; font-weight: 600; margin-top: 4px; }
.s-textarea {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; resize: vertical; outline: none; font-family: inherit;
}
.s-select, .s-input {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; outline: none; width: 100%;
}
.slider-row { display: flex; align-items: center; gap: 6px; }
.slider-row input { flex: 1; accent-color: #E2B340; }
.val { color: #787878; font-size: 12px; min-width: 35px; text-align: right; }
.row { display: flex; gap: 6px; align-items: end; }
.col { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.btn-sm { padding: 4px 8px; background: #181818; border: none; border-radius: 4px; color: #E8E8E8; cursor: pointer; }
.btn-generate {
  padding: 12px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer; margin-top: auto;
}
.btn-generate:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
