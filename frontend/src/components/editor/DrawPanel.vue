<template>
  <div class="draw-panel">
    <!-- Tool Selection -->
    <div class="section-header">그리기 도구</div>

    <div class="tool-group">
      <button
        v-for="tool in drawTools"
        :key="tool.id"
        class="tool-btn"
        :class="{ active: selectedTool === tool.id }"
        @click="selectTool(tool.id)"
      >
        {{ tool.label }}
      </button>
    </div>

    <div class="divider" />

    <!-- Color Palette -->
    <div class="section-subheader">색상</div>

    <div class="palette-grid">
      <button
        v-for="color in paletteColors"
        :key="color"
        class="palette-btn"
        :style="{ backgroundColor: color }"
        @click="onPaletteClick(color)"
      />
    </div>

    <div class="color-row">
      <div
        class="color-preview"
        :style="{ backgroundColor: currentColor }"
      />
      <button class="secondary-btn" @click="$emit('pick-custom-color')">+ 색상 선택</button>
    </div>

    <!-- Gradient End Color (visible only for gradient tool) -->
    <div v-if="currentToolName === 'gradient'" class="gradient-row">
      <span class="small-label">끝 색상:</span>
      <div
        class="color-preview small"
        :style="{ backgroundColor: gradientEndColor }"
      />
      <button class="small-btn" @click="$emit('pick-gradient-end-color')">선택</button>
    </div>

    <!-- Heal Apply Button (visible only for heal tool) -->
    <button
      v-if="currentToolName === 'heal'"
      class="heal-apply-btn"
      @click="$emit('heal-apply')"
    >
      복원 적용
    </button>

    <div class="divider" />

    <!-- Size / Opacity Sliders -->
    <div class="slider-group">
      <label class="slider-label">크기</label>
      <input type="range" :min="1" :max="100" v-model.number="brushSize" class="slider" />
      <span class="slider-value">{{ brushSize }}</span>
    </div>

    <div class="slider-group">
      <label class="slider-label">투명도</label>
      <input type="range" :min="1" :max="100" v-model.number="brushOpacity" class="slider" />
      <span class="slider-value">{{ brushOpacity }}</span>
    </div>

    <!-- Fill Toggle -->
    <button
      class="fill-btn"
      :class="{ active: isFilled }"
      @click="isFilled = !isFilled"
    >
      {{ isFilled ? '■ 채우기 ON' : '□ 채우기 OFF' }}
    </button>

    <div class="divider" />

    <!-- Layer -->
    <div class="section-subheader">레이어</div>

    <div class="slider-group">
      <label class="slider-label">레이어 투명도</label>
      <input type="range" :min="0" :max="100" v-model.number="layerOpacity" class="slider" />
      <span class="slider-value">{{ layerOpacity }}</span>
    </div>

    <button class="secondary-btn full-width" @click="$emit('flatten-layer')">레이어 병합</button>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const emit = defineEmits([
  'tool-changed',
  'color-changed',
  'params-changed',
  'pick-custom-color',
  'pick-gradient-end-color',
  'heal-apply',
  'flatten-layer',
  'layer-opacity-changed',
])

const props = defineProps({
  gradientEndColor: { type: String, default: '#000000' },
})

const paletteColors = [
  '#000000', '#FFFFFF', '#FF0000', '#00FF00',
  '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF',
  '#FF8800', '#8800FF', '#888888', '#FF4488',
]

const drawTools = [
  { id: 0, name: 'pen', label: '펜 (자유 그리기)' },
  { id: 1, name: 'line', label: '직선' },
  { id: 2, name: 'rect', label: '사각형' },
  { id: 3, name: 'ellipse', label: '원/타원' },
  { id: 4, name: 'fill', label: '채우기' },
  { id: 5, name: 'eyedropper', label: '스포이트' },
  { id: 6, name: 'clone_stamp', label: '클론 스탬프' },
  { id: 7, name: 'text_overlay', label: '텍스트' },
  { id: 8, name: 'gradient', label: '그라디언트' },
  { id: 9, name: 'heal', label: '복원 브러시' },
]

const toolNameMap = Object.fromEntries(drawTools.map(t => [t.id, t.name]))

const selectedTool = ref(0)
const currentColor = ref('#000000')
const brushSize = ref(3)
const brushOpacity = ref(100)
const isFilled = ref(false)
const layerOpacity = ref(100)

const currentToolName = computed(() => toolNameMap[selectedTool.value] || 'pen')

function selectTool(id) {
  selectedTool.value = id
  emitToolChanged()
}

function onPaletteClick(color) {
  currentColor.value = color
  emit('color-changed', { color })
  emitParamsChanged()
}

function emitToolChanged() {
  emit('tool-changed', {
    tool: currentToolName.value,
    color: currentColor.value,
    size: brushSize.value,
    opacity: brushOpacity.value / 100.0,
    filled: isFilled.value,
  })
}

function emitParamsChanged() {
  emit('params-changed', {
    tool: currentToolName.value,
    color: currentColor.value,
    size: brushSize.value,
    opacity: brushOpacity.value / 100.0,
    filled: isFilled.value,
  })
}

watch([brushSize, brushOpacity, isFilled], () => {
  emitParamsChanged()
})

watch(layerOpacity, (val) => {
  emit('layer-opacity-changed', val)
})

/** Called by parent to set color from eyedropper */
function setColor(hexColor) {
  currentColor.value = hexColor
}

defineExpose({ setColor })
</script>

<style scoped>
.draw-panel {
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

.section-subheader {
  color: #585858;
  font-size: 14px;
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

.divider {
  height: 1px;
  background-color: #2A2A2A;
  margin: 4px 0;
}

.palette-grid {
  display: grid;
  grid-template-columns: repeat(6, 32px);
  gap: 4px;
}

.palette-btn {
  width: 32px;
  height: 32px;
  border: 2px solid #2A2A2A;
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
}
.palette-btn:hover {
  border-color: #585858;
}

.color-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.color-preview {
  width: 36px;
  height: 36px;
  border: 2px solid #585858;
  border-radius: 4px;
  flex-shrink: 0;
}
.color-preview.small {
  width: 32px;
  height: 32px;
}

.gradient-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.small-label {
  color: #585858;
  font-size: 12px;
}

.small-btn {
  height: 32px;
  background: #1A1A1A;
  color: #E8E8E8;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  padding: 0 8px;
}

.secondary-btn {
  flex: 1;
  height: 36px;
  background-color: #1A1A1A;
  color: #E8E8E8;
  border: 1px solid #2A2A2A;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  cursor: pointer;
}
.secondary-btn:hover {
  background-color: #222;
}
.secondary-btn.full-width {
  width: 100%;
}

.heal-apply-btn {
  height: 36px;
  background-color: #2D8C4E;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.heal-apply-btn:hover {
  background-color: #3AA05E;
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

.fill-btn {
  height: 34px;
  background-color: #1A1A1A;
  color: #B0B0B0;
  border: 1px solid #2A2A2A;
  border-radius: 6px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
}
.fill-btn:hover {
  border-color: #585858;
}
.fill-btn.active {
  background-color: #E2B340;
  color: #fff;
  border-color: #E2B340;
}
</style>
