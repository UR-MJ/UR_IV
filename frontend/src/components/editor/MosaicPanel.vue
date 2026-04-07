<template>
  <div class="mosaic-panel">
    <!-- Tool Selection -->
    <div class="section-header">도구</div>

    <div class="tool-group">
      <button
        v-for="tool in tools"
        :key="tool.id"
        class="tool-btn"
        :class="{ active: selectedTool === tool.id }"
        @click="selectTool(tool.id)"
      >
        {{ tool.label }}
      </button>
    </div>

    <div class="divider" />

    <!-- Effect Selection -->
    <div class="section-header">효과</div>

    <div class="tool-group">
      <button
        v-for="effect in effects"
        :key="effect.id"
        class="tool-btn"
        :class="{ active: selectedEffect === effect.id }"
        @click="selectEffect(effect.id)"
      >
        {{ effect.label }}
      </button>
    </div>

    <div class="divider" />

    <!-- Auto Censor (YOLO) -->
    <div class="auto-censor-section">
      <div class="model-label">{{ modelLabel }}</div>

      <div class="btn-row">
        <button class="secondary-btn" @click="$emit('add-model')">+ 모델</button>
        <button class="secondary-btn" @click="$emit('clear-models')">초기화</button>
      </div>

      <div class="slider-group">
        <label class="slider-label">신뢰도</label>
        <input
          type="range"
          :min="1"
          :max="100"
          v-model.number="detectConf"
          class="slider"
        />
        <span class="slider-value">{{ detectConf }}</span>
      </div>

      <button class="censor-btn" @click="$emit('auto-censor', { confidence: detectConf })">
        자동 검열
      </button>
      <button class="detect-btn" @click="$emit('auto-detect', { confidence: detectConf })">
        감지만 (마스크)
      </button>
      <div class="detect-status">{{ detectStatus }}</div>
    </div>

    <div class="divider" />

    <!-- Action Area -->
    <div class="action-section">
      <!-- Tool Size / Bar Size -->
      <template v-if="selectedEffect === 1 && selectedTool === 0">
        <div class="slider-group">
          <label class="slider-label">너비(W)</label>
          <input type="range" :min="1" :max="500" v-model.number="barWidth" class="slider" />
          <span class="slider-value">{{ barWidth }}</span>
        </div>
        <div class="slider-group">
          <label class="slider-label">높이(H)</label>
          <input type="range" :min="1" :max="500" v-model.number="barHeight" class="slider" />
          <span class="slider-value">{{ barHeight }}</span>
        </div>
      </template>
      <template v-else>
        <div class="slider-group">
          <label class="slider-label">도구 크기</label>
          <input type="range" :min="1" :max="300" v-model.number="toolSize" class="slider" />
          <span class="slider-value">{{ toolSize }}</span>
        </div>
      </template>

      <div class="slider-group">
        <label class="slider-label">{{ selectedEffect === 1 && selectedTool === 0 ? '찍힘 간격' : '효과 강도' }}</label>
        <input type="range" :min="1" :max="100" v-model.number="strength" class="slider" />
        <span class="slider-value">{{ strength }}</span>
      </div>

      <div class="slider-group">
        <label class="slider-label">페더링</label>
        <input type="range" :min="0" :max="50" v-model.number="feather" class="slider" />
        <span class="slider-value">{{ feather }}</span>
      </div>

      <!-- Apply / Cancel Selection -->
      <div class="btn-row">
        <button class="accent-btn flex-2" @click="onApply">적용 (Enter)</button>
        <button class="cancel-btn flex-1" @click="$emit('cancel-selection')">선택 취소 (Esc)</button>
      </div>

      <!-- Crop / Resize / Perspective -->
      <div class="btn-row-3">
        <button class="action-btn" @click="$emit('crop')">크롭</button>
        <button class="action-btn" @click="$emit('resize')">리사이즈</button>
        <button class="action-btn" @click="$emit('perspective')">원근보정</button>
      </div>

      <!-- Rotate -->
      <div class="btn-row">
        <button class="action-btn" @click="$emit('rotate', 'cw')">↻ 90°</button>
        <button class="action-btn" @click="$emit('rotate', 'ccw')">↺ 90°</button>
      </div>

      <!-- Flip -->
      <div class="btn-row">
        <button class="action-btn" @click="$emit('flip', 'horizontal')">↔ 좌우반전</button>
        <button class="action-btn" @click="$emit('flip', 'vertical')">↕ 상하반전</button>
      </div>

      <div class="divider" />

      <!-- Background Removal -->
      <div class="bg-remove-row">
        <label class="small-label">모델:</label>
        <select v-model="bgModel" class="select-input">
          <option v-for="m in bgModels" :key="m.id" :value="m.id">
            {{ m.id }} — {{ m.desc }}
          </option>
        </select>
      </div>
      <div class="bg-remove-row">
        <label class="small-label">배경:</label>
        <select v-model="bgColor" class="select-input">
          <option value="white">흰색</option>
          <option value="black">검은색</option>
        </select>
      </div>

      <button class="action-btn full-width" @click="onRemoveBg">배경 제거</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const emit = defineEmits([
  'tool-changed',
  'effect-changed',
  'effect-apply',
  'cancel-selection',
  'crop',
  'resize',
  'perspective',
  'rotate',
  'flip',
  'remove-bg',
  'add-model',
  'clear-models',
  'auto-censor',
  'auto-detect',
  'params-changed',
])

const props = defineProps({
  modelLabel: { type: String, default: '모델 없음' },
  detectStatus: { type: String, default: '' },
})

const tools = [
  { id: 0, label: '사각형 선택' },
  { id: 1, label: '올가미 선택' },
  { id: 2, label: '브러쉬' },
  { id: 3, label: '지우기' },
]

const effects = [
  { id: 0, label: '모자이크' },
  { id: 1, label: '검은띠 (Bar)' },
  { id: 2, label: '블러 (Blur)' },
]

const bgModels = [
  { id: 'u2net', desc: '범용 (기본)' },
  { id: 'isnet-anime', desc: '애니/일러스트' },
  { id: 'isnet-general-use', desc: '범용 개선판' },
  { id: 'silueta', desc: '경량 빠름' },
]

const selectedTool = ref(0)
const selectedEffect = ref(0)
const toolSize = ref(20)
const barWidth = ref(50)
const barHeight = ref(20)
const strength = ref(15)
const feather = ref(0)
const detectConf = ref(25)
const bgModel = ref('u2net')
const bgColor = ref('white')

function selectTool(id) {
  selectedTool.value = id
  emit('tool-changed', { tool: id, size: toolSize.value })
}

function selectEffect(id) {
  selectedEffect.value = id
  emit('effect-changed', { effect: id })
}

function onApply() {
  const params = {
    tool: selectedTool.value,
    effect: selectedEffect.value,
    toolSize: toolSize.value,
    barWidth: barWidth.value,
    barHeight: barHeight.value,
    strength: strength.value,
    feather: feather.value,
  }
  emit('effect-apply', params)
}

function onRemoveBg() {
  emit('remove-bg', { model: bgModel.value, bgColor: bgColor.value })
}

watch([toolSize, strength, feather, barWidth, barHeight], () => {
  emit('params-changed', {
    toolSize: toolSize.value,
    strength: strength.value,
    feather: feather.value,
    barWidth: barWidth.value,
    barHeight: barHeight.value,
  })
})
</script>

<style scoped>
.mosaic-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  color: #E8E8E8;
  font-size: 13px;
}

.section-header {
  color: #585858;
  font-size: 18px;
  font-weight: bold;
  padding: 2px;
}

.tool-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-btn {
  background-color: #1A1A1A;
  border: 1px solid #2A2A2A;
  border-radius: 6px;
  color: #B0B0B0;
  font-size: 13px;
  font-weight: bold;
  text-align: left;
  padding: 8px 12px;
  cursor: pointer;
  height: 36px;
  display: flex;
  align-items: center;
}
.tool-btn:hover {
  border-color: #585858;
  background-color: #222;
}
.tool-btn.active {
  background-color: #E2B340;
  color: #fff;
  border-color: #E2B340;
}
.tool-btn.active:hover {
  background-color: #E2B340;
}

.divider {
  height: 1px;
  background-color: #2A2A2A;
  margin: 4px 0;
}

.auto-censor-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-label {
  color: #B0B0B0;
  font-size: 12px;
  word-wrap: break-word;
}

.btn-row {
  display: flex;
  gap: 4px;
}

.btn-row-3 {
  display: flex;
  gap: 4px;
}

.secondary-btn {
  flex: 1;
  height: 35px;
  background-color: #222;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  color: #E8E8E8;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.secondary-btn:hover {
  background-color: #2A2A2A;
}

.censor-btn {
  height: 35px;
  background-color: #8B0000;
  color: #fff;
  border: 1px solid #B22222;
  border-radius: 4px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.censor-btn:hover {
  background-color: #A52A2A;
}

.detect-btn {
  height: 35px;
  background-color: #222;
  color: #E8E8E8;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.detect-btn:hover {
  background-color: #2A2A2A;
}

.detect-status {
  color: #585858;
  font-size: 10px;
  min-height: 18px;
}

.slider-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-label {
  color: #B0B0B0;
  font-size: 12px;
  min-width: 60px;
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

.action-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accent-btn {
  height: 40px;
  background-color: #E2B340;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
}
.accent-btn:hover {
  background-color: #c9a038;
}

.cancel-btn {
  height: 40px;
  background-color: #222;
  color: #B0B0B0;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.cancel-btn:hover {
  background-color: #2A2A2A;
}

.action-btn {
  flex: 1;
  height: 35px;
  background-color: #1A1A1A;
  color: #E8E8E8;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.action-btn:hover {
  background-color: #222;
}

.action-btn.full-width {
  width: 100%;
}

.flex-1 { flex: 1; }
.flex-2 { flex: 2; }

.bg-remove-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.small-label {
  color: #B0B0B0;
  font-size: 12px;
  min-width: 35px;
}

.select-input {
  flex: 1;
  height: 30px;
  background-color: #1A1A1A;
  color: #E8E8E8;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  font-size: 12px;
  padding: 2px 6px;
}
</style>
