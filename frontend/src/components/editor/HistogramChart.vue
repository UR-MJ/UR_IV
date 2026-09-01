<template>
  <div class="histogram-chart">
    <div class="hist-head">
      <span class="hist-title">히스토그램</span>
      <div class="hist-modes">
        <button
          v-for="opt in MODE_OPTIONS"
          :key="opt.mode"
          type="button"
          class="mode-btn"
          :class="{ active: mode === opt.mode }"
          :title="opt.title"
          @click="setMode(opt.mode)"
        >{{ opt.label }}</button>
      </div>
    </div>

    <div class="hist-box">
      <canvas
        ref="canvasEl"
        class="hist-canvas"
        @pointermove="onPointerMove"
        @pointerleave="hoverBin = -1"
      />
      <div v-if="notice" class="hist-notice">{{ notice }}</div>
    </div>

    <div class="hist-foot">
      <template v-if="hoverBin >= 0 && hasData">
        <span class="foot-level">레벨 {{ hoverBin }}</span>
        <span class="foot-share" :title="hoverTitle">{{ hoverShare }}</span>
      </template>
      <template v-else-if="hasData">
        <span
          v-if="clipping.shadow >= CLIP_MIN"
          class="clip clip-shadow"
          title="순검정(0)에 몰려 그림자 계조가 사라진 픽셀 비율"
        ><Icon name="chevron-down" /> {{ percent(clipping.shadow) }}</span>
        <span
          v-if="clipping.highlight >= CLIP_MIN"
          class="clip clip-highlight"
          title="순백(255)에 몰려 하이라이트 계조가 사라진 픽셀 비율"
        ><Icon name="chevron-up" /> {{ percent(clipping.highlight) }}</span>
        <span v-if="levelsActive" class="foot-levels">레벨 {{ blackPoint }}–{{ whitePoint }}</span>
      </template>
      <button
        type="button"
        class="log-btn"
        :class="{ active: logScale }"
        title="세로축을 로그로 — 단색 배경 한 덩어리가 천장을 다 먹어 나머지가 안 보일 때"
        @click="toggleLog"
      >로그</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 히스토그램 표시.
 *
 * 계산은 하지 않는다 — `useImageHistogram` 이 만든 결과를 부모가 내려준다.
 * 커브 편집기와 같은 결과를 나눠 써야 둘이 다른 그림을 보여주는 일이 없다.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  BINS,
  barRatio,
  clippingRatio,
  emptyHistograms,
  normalizationCeiling,
  type ChannelKey,
  type Histograms,
} from '../../utils/histogram'
import { useHistogramScale } from '../../composables/useHistogramScale'

type Mode = 'rgb' | 'r' | 'g' | 'b' | 'lum'

const props = withDefaults(defineProps<{
  /** `useImageHistogram` 이 만든 채널별 분포 */
  hists?: Histograms
  hasData?: boolean
  /** 그릴 게 없을 때 상자 가운데에 띄울 문구 */
  notice?: string
  /** 아래 레벨 슬라이더의 현재 값. 잘려나갈 구간을 그래프 위에 겹쳐 보여준다. */
  blackPoint?: number
  whitePoint?: number
}>(), {
  hists: () => emptyHistograms(),
  hasData: false,
  notice: '',
  blackPoint: 0,
  whitePoint: 255,
})

const MODE_OPTIONS: { mode: Mode; label: string; title: string }[] = [
  { mode: 'rgb', label: 'RGB', title: 'R·G·B 겹쳐 보기' },
  { mode: 'r', label: 'R', title: '빨강 채널' },
  { mode: 'g', label: 'G', title: '초록 채널' },
  { mode: 'b', label: 'B', title: '파랑 채널' },
  { mode: 'lum', label: '명도', title: '휘도(Rec.601)' },
]

const MODE_CHANNELS: Record<Mode, ChannelKey[]> = {
  rgb: ['r', 'g', 'b'],
  r: ['r'],
  g: ['g'],
  b: ['b'],
  lum: ['lum'],
}

/** 채널 색 — 색상각은 팔레트와 같은 계열(파랑 H218 · 초록 H130)을 쓴다. */
const CHANNEL_RGB: Record<ChannelKey, [number, number, number]> = {
  r: [217, 92, 92],
  g: [92, 201, 124],
  b: [103, 151, 220],
  lum: [198, 198, 198],
}

/** 이 비율 아래의 계조 뭉갬은 알릴 가치가 없다 (0.1%). */
const CLIP_MIN = 0.001
const MODE_STORAGE_KEY = 'editorHistogramMode'

const canvasEl = ref<HTMLCanvasElement | null>(null)
const mode = ref<Mode>(readStoredMode())
// 커브 편집기 배경도 같은 축을 쓴다 — 둘이 다른 그림을 보여주지 않도록
const { logScale } = useHistogramScale()
const hoverBin = ref(-1)

let observer: ResizeObserver | null = null

const channels = computed(() => MODE_CHANNELS[mode.value])
const clipping = computed(() =>
  props.hasData ? clippingRatio(props.hists) : { shadow: 0, highlight: 0 },
)
const levelsActive = computed(() => props.blackPoint > 0 || props.whitePoint < BINS - 1)
/** 정규화 천장. 채널 전체를 훑으므로 마우스가 움직일 때마다 다시 구하지 않는다. */
const ceiling = computed(() =>
  props.hasData ? normalizationCeiling(props.hists, channels.value) : 1,
)

const hoverShare = computed(() => {
  if (hoverBin.value < 0 || !props.hists.count) return ''
  const shares = channels.value.map((key) =>
    ((props.hists[key][hoverBin.value] / props.hists.count) * 100).toFixed(2),
  )
  return `${shares.join(' / ')}%`
})
const hoverTitle = computed(() =>
  channels.value.length > 1
    ? `이 레벨의 픽셀 비율 (${channels.value.map((c) => c.toUpperCase()).join(' / ')})`
    : '이 레벨의 픽셀 비율',
)

function readStoredMode(): Mode {
  const saved = window.localStorage.getItem(MODE_STORAGE_KEY)
  return saved && saved in MODE_CHANNELS ? (saved as Mode) : 'rgb'
}

function setMode(next: Mode) {
  mode.value = next
  window.localStorage.setItem(MODE_STORAGE_KEY, next)
  draw()
}

function toggleLog() {
  logScale.value = !logScale.value
}

function percent(ratio: number): string {
  return `${(ratio * 100).toFixed(ratio >= 0.1 ? 0 : 1)}%`
}

function cssVar(name: string, fallback: string): string {
  const el = canvasEl.value
  if (!el) return fallback
  const value = getComputedStyle(el).getPropertyValue(name).trim()
  return value || fallback
}

function onPointerMove(event: PointerEvent) {
  const canvas = canvasEl.value
  if (!canvas || !props.hasData) return
  const rect = canvas.getBoundingClientRect()
  if (rect.width <= 0) return
  const ratio = (event.clientX - rect.left) / rect.width
  hoverBin.value = Math.max(0, Math.min(BINS - 1, Math.floor(ratio * BINS)))
}

watch(hoverBin, () => draw())
watch(
  [() => props.hists, () => props.hasData, () => props.blackPoint, () => props.whitePoint, logScale],
  () => draw(),
)

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

  const rule = cssVar('--rule', '#2E2E2E')
  const edge = cssVar('--edge', '#666666')

  // 4분할 눈금 — 그림자/중간/하이라이트 구간을 눈으로 집을 수 있게
  ctx.strokeStyle = rule
  ctx.lineWidth = 1
  for (let i = 1; i < 4; i++) {
    const x = Math.round((cssW * i) / 4) + 0.5
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, cssH)
    ctx.stroke()
  }

  if (!props.hasData) return

  const top = ceiling.value
  const single = channels.value.length === 1

  // 겹쳐 그릴 때는 가산 합성 — 겹친 구간이 밝아져 어느 채널이 겹쳤는지 보인다
  ctx.globalCompositeOperation = single ? 'source-over' : 'lighter'
  for (const key of channels.value) {
    const [r, g, b] = CHANNEL_RGB[key]
    const hist = props.hists[key]
    ctx.beginPath()
    ctx.moveTo(0, cssH)
    for (let i = 0; i < BINS; i++) {
      const x = (i / (BINS - 1)) * cssW
      const y = cssH - barRatio(hist[i], top, logScale.value) * cssH
      ctx.lineTo(x, y)
    }
    ctx.lineTo(cssW, cssH)
    ctx.closePath()
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${single ? 0.42 : 0.5})`
    ctx.fill()
    ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, 0.95)`
    ctx.lineWidth = 1
    ctx.stroke()
  }
  ctx.globalCompositeOperation = 'source-over'

  // 레벨 슬라이더가 잘라낼 구간을 덮어 보여준다 — 슬라이더는 바로 아래에 있다
  if (levelsActive.value) {
    const bx = (props.blackPoint / (BINS - 1)) * cssW
    const wx = (props.whitePoint / (BINS - 1)) * cssW
    ctx.fillStyle = 'rgba(0, 0, 0, 0.55)'
    if (bx > 0) ctx.fillRect(0, 0, bx, cssH)
    if (wx < cssW) ctx.fillRect(wx, 0, cssW - wx, cssH)
    ctx.strokeStyle = edge
    ctx.lineWidth = 1
    for (const x of [bx, wx]) {
      const px = Math.round(x) + 0.5
      ctx.beginPath()
      ctx.moveTo(px, 0)
      ctx.lineTo(px, cssH)
      ctx.stroke()
    }
  }

  if (hoverBin.value >= 0) {
    const x = Math.round((hoverBin.value / (BINS - 1)) * cssW) + 0.5
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.55)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, cssH)
    ctx.stroke()
  }
}

onMounted(() => {
  const canvas = canvasEl.value
  if (canvas && typeof ResizeObserver !== 'undefined') {
    // 사이드 패널은 200~500px 로 드래그된다 — 폭이 바뀌면 다시 그려야 흐려지지 않는다
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
.histogram-chart {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

/* 사이드 패널은 200px 까지 좁아진다. 그 폭에서는 제목+버튼이 한 줄에 못 들어가므로
   버튼 묶음을 통째로 다음 줄로 내린다 — 글자 단위로 쪼개지는 것보다 낫다. */
.hist-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-2);
}

.hist-title {
  color: var(--text-secondary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
  white-space: nowrap;
}

.hist-modes {
  display: flex;
  gap: 2px;
}

.mode-btn {
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
.mode-btn:hover {
  color: var(--text-secondary);
  border-color: var(--rule);
}
.mode-btn.active {
  color: var(--text-primary);
  border-color: var(--edge);
}

.hist-box {
  position: relative;
  height: 96px;
  background-color: var(--bg-primary);
  border: 1px solid var(--rule);
  border-radius: var(--radius-base);
  overflow: hidden;
}

.hist-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.hist-notice {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: var(--fs-meta);
  pointer-events: none;
}

.hist-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-1) var(--sp-2);
  min-height: 16px;
  color: var(--text-muted);
  font-size: var(--fs-label);
  white-space: nowrap;
}

.foot-level,
.foot-levels {
  color: var(--text-secondary);
}

.foot-share,
.clip {
  font-variant-numeric: tabular-nums;
}

.clip-shadow {
  color: var(--state-info);
}
.clip-highlight {
  color: var(--state-alert);
}

.log-btn {
  margin-left: auto;
  padding: 0 var(--sp-1);
  height: 16px;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid transparent;
  border-radius: 3px;
  font-size: var(--fs-label);
  line-height: 1;
  cursor: pointer;
}
.log-btn:hover {
  color: var(--text-secondary);
  border-color: var(--rule);
}
.log-btn.active {
  color: var(--text-primary);
  border-color: var(--edge);
}
</style>
