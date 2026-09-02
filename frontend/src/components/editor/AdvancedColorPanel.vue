<template>
  <div class="advanced-color-panel">
    <HistogramChart
      :hists="hists"
      :has-data="hasData"
      :notice="notice"
      :black-point="blackPoint"
      :white-point="whitePoint"
    />

    <div class="divider" />

    <CurvesEditor
      :curves="curves"
      :hists="hists"
      :has-data="hasData"
      @change="onCurvesChange"
    />

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

<script setup lang="ts">
import { ref, watch } from 'vue'
import HistogramChart from './HistogramChart.vue'
import CurvesEditor from './CurvesEditor.vue'
import { useImageHistogram } from '../../composables/useImageHistogram'
import { identityCurves, type Curves } from '../../utils/curves'

const props = withDefaults(defineProps<{
  /** 지금 캔버스에 보이는 이미지 src — 히스토그램이 프리뷰까지 따라가려면 필요하다 */
  src?: string
  /** 이 패널이 보이는 탭인지. 숨어 있는 동안 히스토그램을 계산하지 않기 위한 것. */
  active?: boolean
}>(), { src: '', active: false })

interface ColorAdjustments {
  blackPoint: number
  whitePoint: number
  gamma: number
  temperature: number
  tint: number
  curves: Curves
}

const emit = defineEmits<{
  preview: [payload: ColorAdjustments]
  apply: [payload: ColorAdjustments]
  reset: []
}>()

// 히스토그램은 여기서 한 번만 계산해 상자와 커브 편집기가 나눠 쓴다.
// 컴포넌트마다 따로 하면 같은 이미지를 두 번 디코드하고, 둘이 다른 순간의 결과를 보여준다.
const { hists, hasData, notice } = useImageHistogram(() => props.src, () => props.active)

const blackPoint = ref(0)
const whitePoint = ref(255)
const gamma = ref(10)
const temperature = ref(0)
const tint = ref(0)
const curves = ref<Curves>(identityCurves())

watch([blackPoint, whitePoint, gamma, temperature, tint], () => {
  emitPreview()
})

function onCurvesChange(next: Curves) {
  curves.value = next
  emitPreview()
}

function payload(): ColorAdjustments {
  return {
    blackPoint: blackPoint.value,
    whitePoint: whitePoint.value,
    gamma: gamma.value / 10.0,
    temperature: temperature.value,
    tint: tint.value,
    curves: curves.value,
  }
}

function emitPreview() {
  emit('preview', payload())
}

function onApply() {
  emit('apply', payload())
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
  // 커브도 되돌린다. 적용하면 결과가 이미지에 구워지므로, 남겨두면 다음 조작에서
  // 같은 커브가 한 번 더 얹힌다. (PyQt 판은 커브를 안 되돌려 이 겹침이 있었다.)
  curves.value = identityCurves()
}
</script>

<style scoped>
.advanced-color-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  color: var(--text-primary);
  font-size: 13px;
}

/* 히스토그램·커브의 제목과 같은 취급 — 한 패널 안에서 제목이 두 가지로 보이지 않게.
   이전 값(#585858 14px bold)은 이 배경에서 대비가 3.2:1 로 본문 기준(4.5:1) 미달이었다. */
.section-header {
  color: var(--text-secondary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
  padding: 2px 0;
}

.divider {
  height: 1px;
  background-color: var(--rule);
  margin: 4px 0;
}

.slider-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.slider-label {
  color: var(--text-secondary);
  font-size: 12px;
  min-width: 80px;
  white-space: nowrap;
}

.slider {
  flex: 1;
  accent-color: var(--accent);
  height: 4px;
  background: var(--rule);
  border-radius: 2px;
}

.slider-value {
  color: var(--text-primary);
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
  background-color: var(--accent-fill);
  color: var(--on-accent);
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: var(--fw-bold);
  cursor: pointer;
}
.accent-btn:hover {
  background-color: var(--accent-fill-hover);
}

.reset-btn {
  height: 36px;
  background-color: var(--bg-button);
  color: var(--text-secondary);
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}
.reset-btn:hover {
  background-color: var(--bg-button-hover);
}

.flex-1 { flex: 1; }
.flex-2 { flex: 2; }
</style>
