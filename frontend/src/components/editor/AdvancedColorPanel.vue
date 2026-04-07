<template>
  <div class="advanced-color-panel">
    <!-- Histogram placeholder -->
    <div class="section-header">히스토그램</div>
    <div class="histogram-placeholder">
      <canvas ref="histCanvas" width="280" height="100" />
    </div>

    <div class="divider" />

    <!-- Curves placeholder -->
    <div class="section-header">커브 (Curves)</div>
    <div class="curves-placeholder">
      <canvas ref="curvesCanvas" width="280" height="150" />
    </div>

    <div class="divider" />

    <!-- Levels -->
    <div class="section-header">레벨 (Levels)</div>

    <div class="slider-group">
      <label class="slider-label">블랙 포인트</label>
      <input type="range" :min="0" :max="255" v-model.number="blackPoint" class="slider" />
      <span class="slider-value">{{ blackPoint }}</span>
    </div>

    <div class="slider-group">
      <label class="slider-label">화이트 포인트</label>
      <input type="range" :min="0" :max="255" v-model.number="whitePoint" class="slider" />
      <span class="slider-value">{{ whitePoint }}</span>
    </div>

    <div class="slider-group">
      <label class="slider-label">감마 x10</label>
      <input type="range" :min="1" :max="30" v-model.number="gamma" class="slider" />
      <span class="slider-value">{{ gamma }}</span>
    </div>

    <div class="divider" />

    <!-- Temperature / Tint -->
    <div class="section-header">색온도 / 틴트</div>

    <div class="slider-group">
      <label class="slider-label">색온도</label>
      <input type="range" :min="-100" :max="100" v-model.number="temperature" class="slider" />
      <span class="slider-value">{{ temperature }}</span>
    </div>

    <div class="slider-group">
      <label class="slider-label">틴트</label>
      <input type="range" :min="-100" :max="100" v-model.number="tint" class="slider" />
      <span class="slider-value">{{ tint }}</span>
    </div>

    <!-- Apply / Reset -->
    <div class="btn-row">
      <button class="accent-btn flex-2" @click="onApply">적용</button>
      <button class="reset-btn flex-1" @click="onReset">초기화</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const emit = defineEmits([
  'preview',
  'apply',
  'reset',
])

const histCanvas = ref(null)
const curvesCanvas = ref(null)

const blackPoint = ref(0)
const whitePoint = ref(255)
const gamma = ref(10)
const temperature = ref(0)
const tint = ref(0)

// Emit preview on any slider change
watch([blackPoint, whitePoint, gamma, temperature, tint], () => {
  emitPreview()
})

function emitPreview() {
  emit('preview', {
    blackPoint: blackPoint.value,
    whitePoint: whitePoint.value,
    gamma: gamma.value / 10.0,
    temperature: temperature.value,
    tint: tint.value,
  })
}

function onApply() {
  emit('apply', {
    blackPoint: blackPoint.value,
    whitePoint: whitePoint.value,
    gamma: gamma.value / 10.0,
    temperature: temperature.value,
    tint: tint.value,
  })
  resetControls()
}

function onReset() {
  resetControls()
  emit('reset')
}

function resetControls() {
  blackPoint.value = 0
  whitePoint.value = 255
  gamma.value = 10
  temperature.value = 0
  tint.value = 0
}
</script>

<style scoped>
.advanced-color-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  color: #E8E8E8;
  font-size: 13px;
}

.section-header {
  color: #585858;
  font-size: 14px;
  font-weight: bold;
  padding: 2px;
}

.histogram-placeholder,
.curves-placeholder {
  background-color: #111;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.histogram-placeholder canvas,
.curves-placeholder canvas {
  width: 100%;
  display: block;
}

.divider {
  height: 1px;
  background-color: #2A2A2A;
  margin: 4px 0;
}

.slider-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-label {
  color: #B0B0B0;
  font-size: 12px;
  min-width: 80px;
  white-space: nowrap;
}

.slider {
  flex: 1;
  accent-color: #E2B340;
  height: 4px;
  background: #2A2A2A;
  border-radius: 2px;
}

.slider-value {
  color: #E8E8E8;
  font-size: 12px;
  min-width: 30px;
  text-align: right;
}

.btn-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.accent-btn {
  height: 36px;
  background-color: #E2B340;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.accent-btn:hover {
  background-color: #c9a038;
}

.reset-btn {
  height: 36px;
  background-color: #222;
  color: #B0B0B0;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}
.reset-btn:hover {
  background-color: #2A2A2A;
}

.flex-1 { flex: 1; }
.flex-2 { flex: 2; }
</style>
