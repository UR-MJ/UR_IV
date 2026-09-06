<template>
  <details class="composition-control">
    <summary>구도 · 카메라 <span>프롬프트로 시점 잡기</span></summary>
    <div class="composition-body">
      <p class="composition-help">태그와 구도 문구로 생성을 유도합니다. 실제 3D 카메라 제어가 아니며 모델에 따라 결과가 달라집니다. 조작만으로 프롬프트가 바뀌지 않습니다.</p>
      <div class="composition-presets" aria-label="구도 프리셋">
        <button v-for="preset in COMPOSITION_PRESETS" :key="preset.name" type="button"
          :aria-pressed="sameState(preset.state)" @click="applyPreset(preset.state)">{{ preset.name }}</button>
      </div>
      <div class="composition-orbit" tabindex="0" role="group" aria-label="카메라 구도 조작"
        :aria-describedby="`${id}-help`" aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown Home"
        @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="cancelDrag"
        @lostpointercapture="cancelDrag" @keydown="onOrbitKey">
        <svg viewBox="0 0 300 170" aria-hidden="true" focusable="false">
          <ellipse class="orbit-line" cx="150" cy="88" rx="90" ry="32" />
          <path class="orbit-line" d="M150 38V134 M50 88H250" />
          <text class="diagram-label" x="150" y="158" text-anchor="middle">정면</text>
          <text class="diagram-label" x="150" y="21" text-anchor="middle">후면</text>
          <line class="camera-ray" :x1="camera.x" :y1="camera.y" x2="150" y2="80" :stroke-dasharray="camera.behind ? '4 4' : undefined" />
          <g class="subject-shape">
            <circle cx="150" cy="64" r="9" />
            <path d="M140 82Q150 75 160 82L163 103H137Z M143 105L140 124 M157 105L160 124" />
          </g>
          <g class="camera-shape" :transform="`translate(${camera.x} ${camera.y}) rotate(${state.roll})`">
            <rect x="-11" y="-7" width="18" height="14" rx="3" />
            <path d="M7 -3L14 -6V6L7 3Z" />
          </g>
        </svg>
        <span class="orbit-readout">방향 {{ state.azimuth }}° · 높이 {{ state.elevation }}°</span>
      </div>
      <p :id="`${id}-help`" class="composition-help">드래그 또는 방향키로 시점 조작 · Shift + 방향키: 크게 이동 · Home: 정면 복원. 아래 슬라이더로도 모두 조절할 수 있습니다.</p>
      <div class="composition-ranges">
        <label v-for="control in COMPOSITION_CONTROLS" :key="control.key" :for="`${id}-${control.key}`">
          <span>{{ control.label }} <output :for="`${id}-${control.key}`">{{ state[control.key] }}{{ control.unit }}</output></span>
          <input :id="`${id}-${control.key}`" type="range" :min="control.min" :max="control.max" step="1"
            :value="state[control.key]" @input="setControl(control.key, $event)" @change="persist" />
        </label>
      </div>
      <p class="composition-help">거리 0: 근접 / 100: 원경 · 화면 위치 −: 왼쪽 / +: 오른쪽. 작은 수치 차이는 같은 문구로 표현될 수 있습니다.</p>
      <div class="composition-preview" :id="`${id}-preview`">
        <strong>추가할 태그 · 구도 문구</strong>
        <p>{{ tags.join(', ') }}</p>
      </div>
      <div v-if="plan.conflicts.length" class="composition-warning" role="status">
        기존 구도와 충돌할 수 있습니다. 기존 태그는 삭제하지 않습니다.
        <ul><li v-for="conflict in plan.conflicts" :key="conflict">{{ conflict }}</li></ul>
      </div>
      <div class="composition-actions">
        <button type="button" class="composition-append" :disabled="!plan.additions.length" :aria-describedby="`${id}-preview`" @click="append">
          {{ !plan.additions.length ? '이미 포함된 구도' : plan.conflicts.length ? '기존 구도 유지하고 추가' : '메인 태그에 추가' }}
        </button>
        <button type="button" @click="applyPreset(DEFAULT_COMPOSITION)">초기화</button>
      </div>
      <span class="composition-feedback" role="status" aria-live="polite">{{ feedback }}</span>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import {
  COMPOSITION_CONTROLS, COMPOSITION_PRESETS, DEFAULT_COMPOSITION,
  compositionCameraPoint, compositionTags, dragComposition, normalizeComposition, planCompositionAppend,
  type CompositionState,
} from '../utils/compositionPrompt'

const props = withDefaults(defineProps<{ modelValue: string; otherPrompts?: string }>(), { otherPrompts: '' })
const emit = defineEmits<{ append: [text: string] }>()
const id = `composition-${useId()}`
const state = ref<CompositionState>({ ...DEFAULT_COMPOSITION })
const tags = computed(() => compositionTags(state.value))
const plan = computed(() => planCompositionAppend(props.modelValue, tags.value, props.otherPrompts))
const camera = computed(() => compositionCameraPoint(state.value))
const feedback = ref('')
let disposed = false
let touched = false
let disconnect: (() => void) | undefined
let drag: { pointerId: number; x: number; y: number; state: CompositionState } | undefined

function sameState(value: Readonly<CompositionState>) {
  return COMPOSITION_CONTROLS.every(control => state.value[control.key] === value[control.key])
}
function update(value: CompositionState) {
  touched = true
  state.value = normalizeComposition(value)
  feedback.value = ''
}
function persist() {
  requestAction('save_ui_prefs', { compositionControl: { ...state.value } })
}
function applyPreset(value: Readonly<CompositionState>) {
  update({ ...value })
  persist()
}
function setControl(key: keyof CompositionState, event: Event) {
  update({ ...state.value, [key]: Number((event.target as HTMLInputElement).value) })
}
function startDrag(event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0) return
  const target = event.currentTarget as HTMLElement
  target.focus({ preventScroll: true })
  target.setPointerCapture(event.pointerId)
  drag = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, state: { ...state.value } }
}
function moveDrag(event: PointerEvent) {
  if (!drag || drag.pointerId !== event.pointerId) return
  update(dragComposition(drag.state, event.clientX - drag.x, event.clientY - drag.y))
}
function endDrag(event: PointerEvent) {
  if (!drag || drag.pointerId !== event.pointerId) return
  moveDrag(event)
  drag = undefined
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
  persist()
}
function cancelDrag(event: PointerEvent) {
  if (!drag || drag.pointerId !== event.pointerId) return
  // A canceled touch restores the starting control state, never a half gesture.
  state.value = drag.state
  drag = undefined
}
function onOrbitKey(event: KeyboardEvent) {
  if (event.ctrlKey || event.altKey || event.metaKey) return
  const step = event.shiftKey ? 15 : 5
  const moves: Record<string, Partial<CompositionState>> = {
    ArrowLeft: { azimuth: state.value.azimuth - step }, ArrowRight: { azimuth: state.value.azimuth + step },
    ArrowUp: { elevation: state.value.elevation + step }, ArrowDown: { elevation: state.value.elevation - step },
    Home: { azimuth: 0, elevation: 0 },
  }
  if (!moves[event.key]) return
  event.preventDefault()
  update({ ...state.value, ...moves[event.key] })
  persist()
}
function append() {
  if (!plan.value.additions.length) return
  const count = plan.value.additions.length
  emit('append', plan.value.text)
  feedback.value = `메인 태그에 ${count}개를 추가했습니다. 기존 프롬프트는 유지했습니다.`
}
function restore(raw: string) {
  if (disposed || touched || drag) return
  try {
    const prefs = JSON.parse(raw)
    if (prefs && typeof prefs === 'object' && 'compositionControl' in prefs) state.value = normalizeComposition(prefs.compositionControl)
  } catch { /* Malformed old prefs must not prevent prompt editing. */ }
}
onMounted(async () => {
  disconnect = onBackendEvent('uiPrefsLoaded', restore)
  const backend = await getBackend()
  if (!disposed && backend?.getUiPrefs) backend.getUiPrefs(restore)
})
onUnmounted(() => { disposed = true; drag = undefined; disconnect?.() })
</script>

<style scoped>
.composition-control { margin: 8px 0 12px; min-width: 0; border: 1px solid var(--border); border-radius: var(--radius-base, 8px); background: var(--bg-secondary); }
.composition-control summary { min-height: 36px; display: flex; align-items: center; gap: 8px; padding: 4px 10px; flex-wrap: wrap; cursor: pointer; color: var(--text-primary); font-size: var(--fs-label, 12px); font-weight: var(--fw-bold, 600); }
.composition-control summary::before { content: '›'; font-size: 16px; }
.composition-control[open] summary::before { content: '⌄'; }
.composition-control summary span { color: var(--text-muted); font-size: 11px; font-weight: normal; }
.composition-body { padding: 0 10px 8px; min-width: 0; }
.composition-help { margin: 5px 0 8px; color: var(--text-muted); font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.composition-presets, .composition-actions { display: flex; gap: 5px; flex-wrap: wrap; }
.composition-control button { min-height: 32px; padding: 5px 8px; color: var(--text-secondary); background: var(--bg-button); border: 1px solid var(--border); border-radius: 5px; cursor: pointer; font: inherit; font-size: 11px; white-space: normal; }
.composition-control button[aria-pressed="true"] { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.composition-control :is(button, input, summary, .composition-orbit):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.composition-orbit { touch-action: none; user-select: none; cursor: grab; position: relative; margin: 8px 0 4px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); }
.composition-orbit:active { cursor: grabbing; }
.composition-orbit svg { width: 100%; height: 170px; display: block; }
.orbit-line { fill: none; stroke: var(--border); stroke-width: 1.5; }
.diagram-label { fill: var(--text-muted); font-size: 11px; }
.camera-ray { stroke: var(--accent); opacity: 0.7; }
.subject-shape { fill: var(--bg-secondary); stroke: var(--text-secondary); stroke-width: 2; stroke-linecap: round; }
.camera-shape { fill: var(--accent-fill); stroke: var(--on-accent); stroke-width: 1.5; }
.orbit-readout { position: absolute; left: 8px; top: 6px; color: var(--text-muted); font-size: 10px; pointer-events: none; }
.composition-ranges { display: grid; gap: 4px; }
.composition-ranges label { display: block; color: var(--text-secondary); font-size: 11px; min-width: 0; }
.composition-ranges label > span { display: flex; justify-content: space-between; gap: 6px; }
.composition-ranges output { font-variant-numeric: tabular-nums; color: var(--accent); }
.composition-ranges input { width: 100%; min-height: 28px; margin: 0; padding: 0; accent-color: var(--accent-fill); cursor: pointer; }
.composition-preview { padding: 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 11px; }
.composition-preview strong { color: var(--text-secondary); font-size: 10px; }
.composition-preview p { margin: 5px 0 0; line-height: 1.5; overflow-wrap: anywhere; }
.composition-warning { margin: 8px 0; color: var(--state-warn-fg); font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.composition-warning ul { margin: 4px 0; padding-left: 16px; }
.composition-actions { margin-top: 8px; }
.composition-control .composition-append { flex: 1; background: var(--accent-fill); color: var(--on-accent); border-color: var(--accent-fill); }
.composition-control button:disabled { opacity: 0.5; cursor: default; }
.composition-feedback { display: block; color: var(--text-muted); font-size: 11px; margin-top: 5px; overflow-wrap: anywhere; }
@media (hover: hover) and (pointer: fine) { .composition-control button:not(:disabled):hover { border-color: var(--accent); } }
@media (pointer: coarse) { .composition-control button { min-height: 44px; } .composition-ranges input { min-height: 40px; } }
/* No decorative motion: the diagram follows input directly, including reduced motion. */
</style>
