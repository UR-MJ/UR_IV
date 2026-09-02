<template>
  <div class="curves-editor">
    <div class="curve-head">
      <span class="curve-title">커브</span>
      <div class="curve-channels">
        <button
          v-for="opt in CHANNEL_OPTIONS"
          :key="opt.channel"
          type="button"
          class="channel-btn"
          :class="{ active: channel === opt.channel }"
          :style="channel === opt.channel ? { color: opt.color, borderColor: opt.color } : undefined"
          :title="opt.title"
          @click="setChannel(opt.channel)"
        >{{ opt.label }}</button>
      </div>
    </div>

    <div class="curve-box">
      <canvas
        ref="canvasEl"
        class="curve-canvas"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @contextmenu.prevent="onContextMenu"
      />
    </div>

    <div class="curve-foot">
      <span class="curve-hint">{{ hint }}</span>
      <button
        type="button"
        class="reset-btn"
        :disabled="channelIsIdentity"
        title="이 채널의 커브만 대각선으로 되돌린다"
        @click="resetChannel"
      ><Icon name="undo" size="12" /> {{ activeOption.label }} 초기화</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 톤 커브 편집기.
 *
 * 곡선 계산은 `utils/curves.ts`, 픽셀 적용은 백엔드(`core/curves.py`)가 한다.
 * 여기는 그리기와 조작만 맡는다.
 *
 * 뒤에 히스토그램을 깔아 두는 이유: 점을 어디에 찍을지는 그 톤에 픽셀이 있느냐로
 * 정해진다. 없는 구간을 끌어올려봐야 바뀌는 게 없다.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  addPoint,
  buildLut,
  identityPoints,
  isIdentity,
  LUT_SIZE,
  movePoint,
  nearestPoint,
  removePoint,
  type CurveChannel,
  type CurvePoint,
  type Curves,
} from '../../utils/curves'
import { barRatio, emptyHistograms, normalizationCeiling, type Histograms } from '../../utils/histogram'
import { useHistogramScale } from '../../composables/useHistogramScale'

const props = withDefaults(defineProps<{
  curves: Curves
  /** 뒤에 깔 분포. `useImageHistogram` 이 만든 것을 부모가 나눠 준다. */
  hists?: Histograms
  hasData?: boolean
}>(), {
  hists: () => emptyHistograms(),
  hasData: false,
})

const emit = defineEmits<{
  change: [curves: Curves]
}>()

/** 채널을 가리키는 고정색 — 테마 토큰이 아니다. R 커브는 어느 테마에서도 빨강이어야
 *  뜻이 통한다(데이터 계열색과 같은 성격). */
const CHANNEL_OPTIONS: { channel: CurveChannel; label: string; color: string; title: string }[] = [
  { channel: 'rgb', label: 'RGB', color: '#C6C6C6', title: '세 채널 전체 (다른 채널 커브 위에 얹힌다)' },
  { channel: 'r', label: 'R', color: '#D95C5C', title: '빨강 채널' },
  { channel: 'g', label: 'G', color: '#5CC97C', title: '초록 채널' },
  { channel: 'b', label: 'B', color: '#6797DC', title: '파랑 채널' },
]

/** 채널 → 뒤에 깔 히스토그램. RGB 커브는 세 채널 전체에 걸리므로 휘도를 쓴다. */
const BACKDROP_CHANNEL = { rgb: 'lum', r: 'r', g: 'g', b: 'b' } as const

/** 그래프 안쪽 여백 — 끝점 손잡이가 상자 밖으로 잘리지 않을 만큼. */
const INSET = 8
const HANDLE_RADIUS = 4
/** 손잡이를 집었다고 볼 화면 거리. 손잡이 반지름보다 넉넉해야 잡기 쉽다. */
const GRAB_PX = 11
const CHANNEL_STORAGE_KEY = 'editorCurveChannel'

const canvasEl = ref<HTMLCanvasElement | null>(null)
const channel = ref<CurveChannel>(readStoredChannel())
const draggingIndex = ref(-1)
// 위 히스토그램 상자와 같은 세로축을 쓴다 — 같은 분포가 위아래로 다르게 보이면 안 된다
const { logScale } = useHistogramScale()

let observer: ResizeObserver | null = null

const activeOption = computed(
  () => CHANNEL_OPTIONS.find((o) => o.channel === channel.value) ?? CHANNEL_OPTIONS[0],
)
const activePoints = computed<CurvePoint[]>(
  () => props.curves[channel.value] ?? identityPoints(),
)
const channelIsIdentity = computed(() => isIdentity({ [channel.value]: activePoints.value }))
const hint = computed(() =>
  draggingIndex.value >= 0 ? '드래그해서 이동' : '클릭으로 점 추가 · 우클릭으로 삭제',
)

function readStoredChannel(): CurveChannel {
  const saved = window.localStorage.getItem(CHANNEL_STORAGE_KEY)
  return CHANNEL_OPTIONS.some((o) => o.channel === saved) ? (saved as CurveChannel) : 'rgb'
}

function setChannel(next: CurveChannel) {
  channel.value = next
  window.localStorage.setItem(CHANNEL_STORAGE_KEY, next)
  draw()
}

function commit(points: CurvePoint[]) {
  emit('change', { ...props.curves, [channel.value]: points })
}

function resetChannel() {
  draggingIndex.value = -1
  commit(identityPoints())
}

// ── 좌표 변환 ───────────────────────────────────────────────────────────────

function graphRect(canvas: HTMLCanvasElement) {
  return {
    x: INSET,
    y: INSET,
    w: Math.max(1, canvas.clientWidth - INSET * 2),
    h: Math.max(1, canvas.clientHeight - INSET * 2),
  }
}

/** 포인터 위치 → 0~1 커브 좌표. y 는 위가 1 이다. */
function toCurveSpace(event: PointerEvent | MouseEvent) {
  const canvas = canvasEl.value
  if (!canvas) return null
  const rect = canvas.getBoundingClientRect()
  const g = graphRect(canvas)
  const x = (event.clientX - rect.left - g.x) / g.w
  const y = 1 - (event.clientY - rect.top - g.y) / g.h
  return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)), g }
}

// ── 조작 ────────────────────────────────────────────────────────────────────

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  const spot = toCurveSpace(event)
  if (!spot) return
  const points = activePoints.value
  const hit = nearestPoint(points, spot.x, spot.y, GRAB_PX, spot.g.w, spot.g.h)
  if (hit >= 0) {
    draggingIndex.value = hit
  } else {
    const added = addPoint(points, spot.x, spot.y)
    draggingIndex.value = added.index
    commit(added.points)
  }
  // 포인터를 캔버스에 묶어 두면 상자 밖으로 끌어도 드래그가 끊기지 않는다
  canvasEl.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (draggingIndex.value < 0) return
  const spot = toCurveSpace(event)
  if (!spot) return
  const moved = movePoint(activePoints.value, draggingIndex.value, spot.x, spot.y)
  draggingIndex.value = moved.index
  commit(moved.points)
}

function onPointerUp(event: PointerEvent) {
  if (draggingIndex.value < 0) return
  draggingIndex.value = -1
  canvasEl.value?.releasePointerCapture?.(event.pointerId)
}

function onContextMenu(event: MouseEvent) {
  const spot = toCurveSpace(event)
  if (!spot) return
  const points = activePoints.value
  const hit = nearestPoint(points, spot.x, spot.y, GRAB_PX, spot.g.w, spot.g.h)
  if (hit < 0) return
  const next = removePoint(points, hit)
  if (next !== points) commit(next)
}

// ── 그리기 ──────────────────────────────────────────────────────────────────

function cssVar(name: string, fallback: string): string {
  const el = canvasEl.value
  if (!el) return fallback
  return getComputedStyle(el).getPropertyValue(name).trim() || fallback
}

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const cssW = canvas.clientWidth
  const cssH = canvas.clientHeight
  if (cssW <= 0 || cssH <= 0) return
  const pxW = Math.round(cssW * dpr)
  const pxH = Math.round(cssH * dpr)
  if (canvas.width !== pxW || canvas.height !== pxH) {
    canvas.width = pxW
    canvas.height = pxH
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, cssW, cssH)

  const g = graphRect(canvas)
  const rule = cssVar('--rule', '#2E2E2E')
  const color = activeOption.value.color

  // 배경 히스토그램 — 점을 어디에 찍을지는 그 톤에 픽셀이 있느냐로 정해진다.
  // 세로축(선형/로그)은 위 히스토그램 상자의 설정을 그대로 따른다.
  if (props.hasData) {
    const key = BACKDROP_CHANNEL[channel.value]
    const hist = props.hists[key]
    const ceiling = normalizationCeiling(props.hists, [key])
    ctx.beginPath()
    ctx.moveTo(g.x, g.y + g.h)
    for (let i = 0; i < LUT_SIZE; i++) {
      const x = g.x + (i / (LUT_SIZE - 1)) * g.w
      ctx.lineTo(x, g.y + g.h - barRatio(hist[i], ceiling, logScale.value) * g.h)
    }
    ctx.lineTo(g.x + g.w, g.y + g.h)
    ctx.closePath()
    ctx.fillStyle = 'rgba(255, 255, 255, 0.10)'
    ctx.fill()
  }

  // 4분할 격자
  ctx.strokeStyle = rule
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const x = Math.round(g.x + (g.w * i) / 4) + 0.5
    const y = Math.round(g.y + (g.h * i) / 4) + 0.5
    ctx.beginPath()
    ctx.moveTo(x, g.y)
    ctx.lineTo(x, g.y + g.h)
    ctx.moveTo(g.x, y)
    ctx.lineTo(g.x + g.w, y)
    ctx.stroke()
  }

  // 대각선 = 아무것도 바꾸지 않는 상태. 지금 커브가 얼마나 벗어났는지의 기준선이다.
  ctx.save()
  ctx.setLineDash([3, 3])
  ctx.strokeStyle = rule
  ctx.beginPath()
  ctx.moveTo(g.x, g.y + g.h)
  ctx.lineTo(g.x + g.w, g.y)
  ctx.stroke()
  ctx.restore()

  // 테두리
  ctx.strokeStyle = rule
  ctx.strokeRect(Math.round(g.x) + 0.5, Math.round(g.y) + 0.5, g.w, g.h)

  // 곡선 — 실제로 적용될 LUT 를 그대로 그린다
  const lut = buildLut(activePoints.value)
  ctx.beginPath()
  for (let i = 0; i < LUT_SIZE; i++) {
    const x = g.x + (i / (LUT_SIZE - 1)) * g.w
    const y = g.y + (1 - lut[i] / 255) * g.h
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()

  // 제어점
  activePoints.value.forEach((point, index) => {
    const x = g.x + point[0] * g.w
    const y = g.y + (1 - point[1]) * g.h
    ctx.beginPath()
    ctx.arc(x, y, index === draggingIndex.value ? HANDLE_RADIUS + 1 : HANDLE_RADIUS, 0, Math.PI * 2)
    ctx.fillStyle = index === draggingIndex.value ? color : 'rgba(255, 255, 255, 0.85)'
    ctx.fill()
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.stroke()
  })
}

watch(
  [() => props.curves, () => props.hists, () => props.hasData, channel, draggingIndex, logScale],
  () => draw(),
  { deep: true },
)

onMounted(() => {
  const canvas = canvasEl.value
  if (canvas && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => draw())
    observer.observe(canvas)
  }
  draw()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<style scoped>
.curves-editor {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.curve-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-2);
}

.curve-title {
  color: var(--text-secondary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
  white-space: nowrap;
}

.curve-channels {
  display: flex;
  gap: 2px;
}

.channel-btn {
  min-width: 24px;
  height: 20px;
  padding: 0 var(--sp-1);
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
  border-radius: 3px;
  font-size: var(--fs-label);
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
}
.channel-btn:hover {
  color: var(--text-secondary);
  border-color: var(--rule);
}

/* 정사각이어야 한다 — 기준선인 대각선이 45°가 아니면 커브가 얼마나 휘었는지
   눈으로 못 읽는다. 패널이 넓어져도 300px 를 넘기지 않고 가운데 둔다. */
.curve-box {
  width: min(100%, 300px);
  aspect-ratio: 1;
  margin: 0 auto;
  background-color: var(--bg-primary);
  border: 1px solid var(--rule);
  border-radius: var(--radius-base);
  overflow: hidden;
}

.curve-canvas {
  display: block;
  width: 100%;
  height: 100%;
  touch-action: none;
  cursor: crosshair;
}

.curve-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-2);
  min-height: 16px;
  color: var(--text-muted);
  font-size: var(--fs-label);
}

.curve-hint {
  white-space: nowrap;
}

.reset-btn {
  padding: 0 var(--sp-1);
  height: 16px;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
  border-radius: 3px;
  font-size: var(--fs-label);
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
}
.reset-btn:hover:not(:disabled) {
  color: var(--text-secondary);
  border-color: var(--rule);
}
.reset-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
