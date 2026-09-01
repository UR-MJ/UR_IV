<template>
  <div class="editor-panel">
    <PanelSection title="효과" storage-key="effect" :badge="effectLabel">
      <div class="chip-grid-3">
        <button v-for="e in effects" :key="e.id"
          class="chip-btn" :class="{ active: selectedEffect === e.id }"
          @click="selectedEffect = e.id"
        >{{ e.label }}</button>
      </div>
      <div class="slider-box">
        <div class="slider-header"><span>세기</span><span>{{ strength }}</span></div>
        <input type="range" min="1" max="100" v-model.number="strength" class="modern-slider" />
      </div>
      <button class="main-apply-btn" @click="onApply">
        <Icon name="sparkles" /> 선택 영역에 적용
      </button>
      <button class="secondary-btn" @click="$emit('cancel-selection')">선택 해제 (ESC)</button>
    </PanelSection>

    <PanelSection title="AI 검열" storage-key="censor" :default-open="false">
      <div class="glass-box">
        <div class="header-with-action">
          <label>감지 모델</label>
          <span class="status-dot" :class="{ active: detectStatus }"></span>
        </div>
        <div class="model-info">{{ modelLabel }}</div>
        <div class="btn-row mt-8">
          <button class="ghost-btn" @click="$emit('add-model')">+ .PT 추가</button>
          <button class="ghost-btn" @click="$emit('clear-models')">초기화</button>
        </div>
        <div class="slider-box mt-12">
          <div class="slider-header"><span>신뢰도</span><span>{{ detectConf }}%</span></div>
          <input type="range" min="1" max="100" v-model.number="detectConf" class="modern-slider" />
        </div>
        <label class="mt-12 sub-label">SAM 정밀화</label>
        <div class="chip-grid-4">
          <button v-for="m in samModels" :key="m.id"
            class="chip-btn" :class="{ active: samModel === m.id }"
            @click="samModel = m.id" :title="m.tip"
          >{{ m.label }}</button>
        </div>

        <!-- SAM3 는 텍스트 기반 세그멘터라 이 입력이 본체다 -->
        <div v-if="samModel === 'sam3'" class="sam3-exclude mt-8">
          <label class="sub-label">
            검출 프롬프트
            <span class="hint" :title="'마스킹할 대상을 영어로 입력 (예: face, hand)\n입력하면 YOLO 모델 없이 SAM3 단독으로 검출합니다.\n비우면 YOLO 모델 파일명에서 자동 유추합니다.'">ⓘ</span>
          </label>
          <input type="text" v-model="samDetectPrompt" class="exclude-input"
            placeholder="face, hand  (비우면 YOLO 필요)" spellcheck="false" autocomplete="off" />
        </div>
        <div v-if="samModel === 'sam3'" class="sam3-exclude mt-8">
          <label class="sub-label">
            제외 프롬프트
            <span class="hint" :title="'마스크에서 제외할 영역을 영어로 입력 (예: face, eyes, hand)\nSAM3가 검출하면 최종 마스크에서 빠집니다.'">ⓘ</span>
          </label>
          <input type="text" v-model="samExcludePrompt" class="exclude-input"
            placeholder="face, eyes, hand" spellcheck="false" autocomplete="off" />
        </div>

        <div class="btn-row mt-12">
          <button class="action-btn primary" @click="$emit('auto-censor', detectPayload())">자동 검열</button>
          <button class="action-btn" @click="$emit('auto-detect', detectPayload())">마스크만</button>
        </div>
      </div>
    </PanelSection>

    <PanelSection title="배경 제거" storage-key="removebg" :default-open="false">
      <div class="chip-grid-3">
        <button class="chip-btn" :class="{ active: bgQuality === 'fast' }" @click="bgQuality = 'fast'"><Icon name="zap" /> 빠름</button>
        <button class="chip-btn" :class="{ active: bgQuality === 'balanced' }" @click="bgQuality = 'balanced'">균형</button>
        <button class="chip-btn" :class="{ active: bgQuality === 'quality' }" @click="bgQuality = 'quality'">품질</button>
      </div>
      <button class="main-apply-btn" @click="$emit('remove-bg', { quality: bgQuality })">
        <Icon name="palette" /> 배경 제거
      </button>
    </PanelSection>
  </div>
</template>

<script setup lang="ts">
/**
 * 효과 탭 — 모자이크/블러/검은띠, AI 검열, 배경 제거.
 *
 * `MosaicPanel` 에서 갈라져 나왔다. 선택 도구와 도구 옵션은 세로 툴바와
 * `MaskToolOptions` 로, 자르기·회전·원근은 `TransformPanel` 로 갔다.
 * 여기 남은 것은 "선택한 영역에 무언가를 한다" 하나로 묶이는 것들이다.
 */
import { ref, computed, watch } from 'vue'
import PanelSection from './PanelSection.vue'

interface Effect { id: number; label: string }
interface SamModelOption { id: string; label: string; tip: string }
interface DetectPayload {
  confidence: number
  samModel: string
  detectPrompt: string
  excludePrompt: string
}

defineProps<{
  modelLabel?: string
  detectStatus?: string
}>()

const emit = defineEmits<{
  'effect-apply': [payload: { effect: number; strength: number }]
  'cancel-selection': []
  'add-model': []
  'clear-models': []
  'auto-censor': [payload: DetectPayload]
  'auto-detect': [payload: DetectPayload]
  'remove-bg': [payload: { quality: string }]
}>()

const effects: Effect[] = [
  { id: 0, label: '모자이크' },
  { id: 1, label: '검은 띠' },
  { id: 2, label: '블러' },
]

const selectedEffect = ref(0)
const strength = ref(15)
const detectConf = ref(25)
const bgQuality = ref('balanced')

const effectLabel = computed(() => effects.find((e) => e.id === selectedEffect.value)?.label ?? '')

const samModels: SamModelOption[] = [
  { id: 'auto', label: 'AUTO', tip: '자동 — MobileSAM 우선, 없으면 SAM3' },
  { id: 'mobile_sam', label: 'MOBILE', tip: 'MobileSAM (가벼움/빠름, bbox 기반)' },
  { id: 'sam3', label: 'SAM3', tip: 'Meta SAM 3 (텍스트 프롬프트, GPU 권장)' },
  { id: 'off', label: 'OFF', tip: 'SAM 정밀화 끔 — YOLO bbox만 사용' },
]

/** localStorage 영속 — 매번 같은 모델을 다시 고르는 건 일이다. */
function persisted(key: string, fallback: string, allowed?: string[]) {
  const box = ref(fallback)
  try {
    const saved = localStorage.getItem(key)
    if (saved !== null && (!allowed || allowed.includes(saved))) box.value = saved
  } catch { /* 사생활 모드 등 — 기본값으로 간다 */ }
  watch(box, (v) => { try { localStorage.setItem(key, v ?? '') } catch { /* 무시 */ } })
  return box
}

const samModel = persisted('editor.samModel', 'auto', samModels.map((m) => m.id))
const samDetectPrompt = persisted('editor.samDetectPrompt', '')
const samExcludePrompt = persisted('editor.samExcludePrompt', '')

function detectPayload(): DetectPayload {
  return {
    confidence: detectConf.value,
    samModel: samModel.value,
    detectPrompt: samModel.value === 'sam3' ? samDetectPrompt.value.trim() : '',
    excludePrompt: samModel.value === 'sam3' ? samExcludePrompt.value.trim() : '',
  }
}

function onApply() {
  emit('effect-apply', { effect: selectedEffect.value, strength: strength.value })
}
</script>

<style scoped>
.sam3-exclude { display: flex; flex-direction: column; }
</style>
