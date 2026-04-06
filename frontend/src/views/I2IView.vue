<template>
  <div class="tab-view">
    <div class="i2i-container">
      <h2>Image to Image</h2>

      <div
        class="drop-zone"
        :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave="isDragging = false"
        @drop.prevent="handleDrop"
        @click="triggerFileInput"
      >
        <div v-if="!imageSrc" class="drop-placeholder">
          <div class="drop-icon">&#x1F5BC;</div>
          <p>이미지를 드래그하거나 클릭하여 업로드</p>
        </div>
        <img v-else :src="imageSrc" class="preview-img" alt="preview" />
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileSelect" />

      <div class="control-row">
        <label class="control-label">
          Denoising Strength
          <span class="value-badge">{{ denoising.toFixed(2) }}</span>
        </label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          v-model.number="denoising"
          class="slider"
        />
      </div>

      <button class="btn-generate" @click="generateI2I" :disabled="!imageSrc">
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
const imageFile = ref(null)
const denoising = ref(0.75)
const fileInput = ref(null)

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) loadFile(file)
}

function handleDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) loadFile(file)
}

function loadFile(file) {
  imageFile.value = file
  const reader = new FileReader()
  reader.onload = (ev) => {
    imageSrc.value = ev.target.result
  }
  reader.readAsDataURL(file)
}

function generateI2I() {
  requestAction('generate_i2i', {
    denoising: denoising.value
  })
}
</script>

<style scoped>
.tab-view {
  width: 100%;
  height: 100%;
  background: #0A0A0A;
  color: #E8E8E8;
  overflow-y: auto;
}
.i2i-container {
  max-width: 520px;
  margin: 0 auto;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.i2i-container h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}
.drop-zone {
  border: 2px dashed #1A1A1A;
  border-radius: 6px;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.15s;
  overflow: hidden;
}
.drop-zone.drag-over {
  border-color: #E2B340;
}
.drop-zone:hover {
  border-color: #585858;
}
.drop-placeholder {
  text-align: center;
  color: #585858;
}
.drop-icon {
  font-size: 36px;
  margin-bottom: 8px;
}
.drop-placeholder p {
  font-size: 13px;
  margin: 0;
}
.preview-img {
  max-width: 100%;
  max-height: 300px;
  object-fit: contain;
  display: block;
}
.control-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control-label {
  font-size: 13px;
  color: #E8E8E8;
  display: flex;
  align-items: center;
  gap: 8px;
}
.value-badge {
  color: #E2B340;
  font-size: 12px;
  font-weight: 600;
}
.slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  background: #1A1A1A;
  border-radius: 2px;
  outline: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #E2B340;
  cursor: pointer;
}
.btn-generate {
  background: #E2B340;
  border: none;
  color: #0A0A0A;
  padding: 10px 0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: opacity 0.15s;
}
.btn-generate:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.btn-generate:not(:disabled):hover {
  opacity: 0.85;
}
</style>
