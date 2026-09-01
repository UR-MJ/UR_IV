<template>
  <div class="editor-panel">
    <PanelSection title="회전 · 뒤집기" storage-key="rotate">
      <div class="btn-grid-4">
        <button class="mini-btn" @click="$emit('rotate', 'ccw')" title="반시계 90°"><Icon name="rotate-ccw" /></button>
        <button class="mini-btn" @click="$emit('rotate', 'cw')" title="시계 90°"><Icon name="rotate-cw" /></button>
        <button class="mini-btn" @click="$emit('flip', 'horizontal')" title="좌우 반전"><Icon name="arrows-horizontal" /></button>
        <button class="mini-btn" @click="$emit('flip', 'vertical')" title="상하 반전"><Icon name="arrow-down" /></button>
      </div>
    </PanelSection>

    <PanelSection title="자르기" storage-key="crop" :badge="cropPending">
      <button class="action-btn" :class="{ on: !!cropPending }" @click="$emit('crop')">
        <Icon name="crop" /> 선택 영역으로 자르기
      </button>
      <!-- 무엇이 얼마로 잘리는지 보여주고 확정을 받는다 — 예전에는 확인 없이 바로 잘랐다 -->
      <div v-if="cropPending" class="resize-box">
        <div class="resize-cur">자르기 결과 {{ cropPending }}</div>
        <div class="btn-row">
          <button class="action-btn primary" @click="$emit('crop-confirm')">자르기</button>
          <button class="action-btn" @click="$emit('crop-cancel')">취소</button>
        </div>
      </div>
    </PanelSection>

    <PanelSection title="크기 변경" storage-key="resize" :default-open="false"
      :badge="imgWidth ? `${imgWidth}×${imgHeight}` : ''">
      <div class="resize-box">
        <div class="resize-row">
          <label class="resize-l">W</label>
          <input class="resize-in" type="number" min="1" max="65536" v-model.number="resizeW" @input="onResizeW" />
          <span class="resize-x">×</span>
          <label class="resize-l">H</label>
          <input class="resize-in" type="number" min="1" max="65536" v-model.number="resizeH" @input="onResizeH" />
        </div>
        <label class="resize-lock">
          <input type="checkbox" v-model="keepRatio" /> 비율 유지
        </label>
        <div class="btn-row">
          <button class="action-btn primary" @click="applyResize">적용</button>
          <button class="action-btn" @click="resetResize">되돌리기</button>
        </div>
      </div>
    </PanelSection>

    <PanelSection title="원근 보정" storage-key="perspective" :default-open="false">
      <template v-if="!perspectiveActive">
        <button class="action-btn" @click="$emit('perspective-start')"
          title="기울어져 찍힌 사각형(액자·표지판·문서)을 정면처럼 펴줍니다">
          <Icon name="layers" /> 꼭짓점 맞추기 시작
        </button>
      </template>
      <template v-else>
        <p class="persp-hint">꼭짓점 4개를 펴고 싶은 사각형의 모서리에 맞춘 뒤 적용하세요.</p>
        <div class="btn-row">
          <button class="action-btn primary" @click="$emit('perspective-confirm')">적용</button>
          <button class="action-btn" @click="$emit('perspective-cancel')">취소</button>
        </div>
      </template>
    </PanelSection>
  </div>
</template>

<script setup lang="ts">
/**
 * 변형 탭 — 회전·뒤집기·자르기·크기 변경·원근 보정.
 *
 * `MosaicPanel` 의 Transform 섹션이 갈라져 나왔다. 이것들은 선택 영역이나 이미지
 * 전체에 **한 번 적용하고 끝나는** 작업이라, 상시 모드인 도구(툴바)와 성질이 다르다.
 * 그래서 툴바가 아니라 탭에 남는다.
 */
import { ref, watch } from 'vue'
import PanelSection from './PanelSection.vue'

const props = withDefaults(defineProps<{
  imgWidth?: number
  imgHeight?: number
  /** 자를 결과 크기 문구. 값이 있으면 확인 UI 가 뜬다. */
  cropPending?: string
  perspectiveActive?: boolean
}>(), { imgWidth: 0, imgHeight: 0, cropPending: '', perspectiveActive: false })

const emit = defineEmits<{
  crop: []
  'crop-confirm': []
  'crop-cancel': []
  resize: [payload: { width: number; height: number }]
  'perspective-start': []
  'perspective-confirm': []
  'perspective-cancel': []
  rotate: [dir: string]
  flip: [dir: string]
}>()

const keepRatio = ref(true)
const resizeW = ref(0)
const resizeH = ref(0)

const ratio = () => (props.imgHeight > 0 ? props.imgWidth / props.imgHeight : 1)

function resetResize() {
  resizeW.value = props.imgWidth
  resizeH.value = props.imgHeight
}
watch(() => [props.imgWidth, props.imgHeight], resetResize, { immediate: true })

function onResizeW() {
  if (!keepRatio.value || !resizeW.value) return
  resizeH.value = Math.max(1, Math.round(resizeW.value / ratio()))
}
function onResizeH() {
  if (!keepRatio.value || !resizeH.value) return
  resizeW.value = Math.max(1, Math.round(resizeH.value * ratio()))
}

function applyResize() {
  const w = Math.max(1, Math.min(65536, Math.round(resizeW.value || 0)))
  const h = Math.max(1, Math.min(65536, Math.round(resizeH.value || 0)))
  if (w === props.imgWidth && h === props.imgHeight) return   // 같은 크기면 보내지 않는다
  emit('resize', { width: w, height: h })
}
</script>
