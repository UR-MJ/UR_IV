<template>
  <div class="editor-panel tool-options">
    <div class="to-head">
      <span class="to-title">{{ toolLabel }}</span>
      <span class="to-key">{{ toolKey }}</span>
    </div>

    <div class="slider-box">
      <div class="slider-header"><span>크기</span><span>{{ toolSize }}px</span></div>
      <input type="range" min="1" max="300" v-model.number="toolSize" class="modern-slider" />
    </div>

    <!-- 올가미 -->
    <div class="control-group" v-if="tool === 'lasso'">
      <label>올가미 방식</label>
      <div class="chip-grid-2">
        <button class="chip-btn" :class="{ active: !magneticLasso }"
          @click="magneticLasso = false; emit('magnetic-changed', false)"><Icon name="loop" /> 자유</button>
        <button class="chip-btn magnet" :class="{ active: magneticLasso }"
          @click="magneticLasso = true; emit('magnetic-changed', true)"><Icon name="magnet" /> 자석</button>
      </div>
    </div>

    <!-- 스탬프 -->
    <template v-if="tool === 'stamp'">
      <div class="control-group">
        <label>도장 모양</label>
        <div class="chip-grid-3">
          <button class="chip-btn" :class="{ active: stampShape === 'circle' }"
            @click="stampShape = 'circle'"><Icon name="circle" /> 원</button>
          <button class="chip-btn" :class="{ active: stampShape === 'bar' }"
            @click="stampShape = 'bar'"><Icon name="bar" /> 띠</button>
          <button class="chip-btn" :class="{ active: stampShape === 'rect' }"
            @click="stampShape = 'rect'"><Icon name="square" /> 사각</button>
        </div>
      </div>
      <div class="slider-box">
        <div class="slider-header"><span>간격</span><span>{{ stampSpacing }}px</span></div>
        <input type="range" min="5" max="200" v-model.number="stampSpacing" class="modern-slider" />
      </div>
      <template v-if="stampShape === 'bar'">
        <div class="slider-box">
          <div class="slider-header"><span>띠 너비</span><span>{{ barW }}px</span></div>
          <input type="range" min="5" max="200" v-model.number="barW" class="modern-slider" />
        </div>
        <div class="slider-box">
          <div class="slider-header"><span>띠 높이</span><span>{{ barH }}px</span></div>
          <input type="range" min="3" max="100" v-model.number="barH" class="modern-slider" />
        </div>
      </template>
    </template>

    <!-- 지우개 -->
    <template v-if="tool === 'eraser'">
      <div class="control-group">
        <label>지우개 종류</label>
        <div class="chip-grid-2">
          <button class="chip-btn" :class="{ active: !eraserRestore }"
            @click="eraserRestore = false; emit('eraser-restore-changed', false)">
            <Icon name="wand" /> 마스크
          </button>
          <button class="chip-btn restore" :class="{ active: eraserRestore }"
            @click="eraserRestore = true; emit('eraser-restore-changed', true)">
            <Icon name="sparkles" /> 모자이크
          </button>
        </div>
      </div>
      <div class="control-group" v-if="!eraserRestore">
        <label>지우는 모양</label>
        <div class="chip-grid-3">
          <button class="chip-btn" :class="{ active: eraserMode === 'brush' }" @click="setEraserMode('brush')">브러시</button>
          <button class="chip-btn" :class="{ active: eraserMode === 'box' }" @click="setEraserMode('box')">사각</button>
          <button class="chip-btn" :class="{ active: eraserMode === 'lasso' }" @click="setEraserMode('lasso')">올가미</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 지금 고른 마스크 도구의 옵션.
 *
 * 예전에는 이 설정들이 `MosaicPanel` 안에 효과·검열·변형과 함께 세로로 쌓여 있었다
 * (그 패널이 1077px = 화면의 135%였던 이유 중 하나). 도구를 세로 툴바로 뺐으니
 * 옵션도 도구를 따라오게 패널 맨 위로 올린다 — 고른 도구의 것만 보인다.
 *
 * 그리기 도구의 옵션은 `DrawPanel` 이 맡는다.
 */
import { ref, computed, watch } from 'vue'
import { toolById } from '../../utils/editorTools'

const props = withDefaults(defineProps<{
  /** 현재 도구 id (box/lasso/brush/eraser/stamp) */
  tool?: string
}>(), { tool: 'box' })

const emit = defineEmits<{
  'params-changed': [payload: {
    toolSize: number; stampSpacing: number; stampShape: string; barW: number; barH: number
  }]
  'eraser-mode-changed': [mode: string]
  'eraser-restore-changed': [val: boolean]
  'magnetic-changed': [val: boolean]
}>()

const toolSize = ref(20)
const eraserMode = ref('brush')
const eraserRestore = ref(false)
const magneticLasso = ref(false)
const stampSpacing = ref(30)
const stampShape = ref('circle')
const barW = ref(40)
const barH = ref(15)

const toolLabel = computed(() => toolById(props.tool)?.label ?? '도구')
const toolKey = computed(() => toolById(props.tool)?.shortcut ?? '')

function setEraserMode(mode: string) {
  eraserMode.value = mode
  emit('eraser-mode-changed', mode)
}

// 도장 모양은 스탬프 도구일 때만 뜻이 있다 — 다른 도구에서 'bar' 가 새어 나가면
// 캔버스가 엉뚱한 커서를 그린다.
watch([toolSize, stampSpacing, stampShape, barW, barH, () => props.tool], () => {
  emit('params-changed', {
    toolSize: toolSize.value,
    stampSpacing: stampSpacing.value,
    stampShape: props.tool === 'stamp' ? stampShape.value : 'circle',
    barW: barW.value,
    barH: barH.value,
  })
}, { immediate: true })
</script>

<style scoped>
.tool-options {
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3) var(--sp-3);
  border-bottom: 1px solid var(--rule);
}

.to-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}

.to-title {
  color: var(--text-primary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
}

.to-key {
  min-width: 18px;
  padding: 1px 5px;
  background: var(--bg-button);
  border: 1px solid var(--rule);
  border-radius: 3px;
  color: var(--text-muted);
  font-size: var(--fs-label);
  text-align: center;
}
</style>
