<template>
  <div class="canvas-container" ref="containerRef"
    @wheel.prevent="onWheel"
    @pointerdown="onMouseDown" @pointermove="onMouseMoveWrap" @pointerup="onMouseUp"
    @pointerleave="onMouseUp" @pointercancel="onMouseUp" @contextmenu.prevent
    @dblclick="onDblClick"
  >
    <canvas ref="canvasEl" :style="canvasStyle" />
    <canvas ref="maskCanvasEl" :style="canvasStyle" class="mask-overlay" />
    <div class="canvas-info">
      {{ imgWidth }} × {{ imgHeight }}
      <template v-if="hasMask"> | 마스크 활성</template>
      | {{ Math.round(zoom * 100) }}% | {{ Math.round(rotation) }}°
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

interface Point { x: number; y: number }
interface SelectionBounds { x: number; y: number; w: number; h: number }

const props = withDefaults(defineProps<{
  imageSrc?: string
  tool?: string
  brushSize?: number
  eraserMode?: string
  eraserRestore?: boolean
  stampSpacing?: number
  stampShape?: string // 'circle' or 'bar'
  barWidth?: number
  barHeight?: number
  magneticLasso?: boolean
  snapRadius?: number
}>(), {
  imageSrc: '',
  tool: 'box',
  brushSize: 20,
  eraserMode: 'brush',
  eraserRestore: false,
  stampSpacing: 30,
  stampShape: 'circle',
  barWidth: 40,
  barHeight: 15,
  magneticLasso: false,
  snapRadius: 12,
})

const emit = defineEmits<{
  'selection-changed': [bounds: SelectionBounds]
  'mask-changed': [arg: any]
  // 모자이크 지우개 스트로크가 끝났다 — 부모가 백엔드에 커밋해야 파일에 반영된다
  'restore-ready': []
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)
const maskCanvasEl = ref<HTMLCanvasElement | null>(null)
const imgWidth = ref(0)
const imgHeight = ref(0)
const zoom = ref(1)
const rotation = ref(0)
const panX = ref(0)
const panY = ref(0)
const hasMask = ref(false)

let ctx: CanvasRenderingContext2D | null = null
let maskCtx: CanvasRenderingContext2D | null = null
let sourceImg: HTMLImageElement | null = null
let drawing = false
let panning = false
let startX = 0, startY = 0
let panStartX = 0, panStartY = 0
let lastBrushX = -1, lastBrushY = -1
let lassoPoints: Point[] = []
let maskData: Uint8Array | null = null
let lastAltClick = 0  // Alt 더블클릭 감지
let stampAccum = 0
let maskUndoStack: Uint8Array[] = []
let maskRedoStack: Uint8Array[] = []
const MAX_MASK_UNDO = 10
const maskUndoCount = ref(0)   // 버튼 disabled 반응형 (마스크 undo/redo 가능 여부)
const maskRedoCount = ref(0)
let savedZoom = 1, savedRotation = 0, savedPanX = 0, savedPanY = 0
let pristineImg: HTMLCanvasElement | null = null  // 원본 이미지 (모자이크 지우개용)
let pristineCtx: CanvasRenderingContext2D | null = null   // getContext 반복 호출 방지
let edgeMapData: Uint8Array | null = null  // Canny edge map (자석 올가미용) — Uint8Array
let edgeMapW = 0, edgeMapH = 0

// ── 마스크 오버레이 렌더링 상태 (성능 핵심) ──────────────────────────────────
// 예전에는 pointermove 마다 createImageData(w*h*4) 를 새로 할당하고 maskData 전체를
// 순회했다. 4K(3840×2160)면 이벤트 1건당 830만 회 루프 + 33MB 할당이고, 펜/고주사율
// 마우스는 초당 수백 건을 쏘므로 이게 에디터 버벅임의 주원인이었다.
//
// 바꾼 방식:
//   1) ImageData 를 이미지당 1개만 만들어 재사용 (할당 0)
//   2) 변경된 사각형(dirty rect)만 다시 칠함
//   3) 실제 캔버스 반영은 requestAnimationFrame 으로 1프레임당 1회로 합침
let maskImageData: ImageData | null = null
let maskPixels: Uint32Array | null = null   // maskImageData.data 의 32bit 뷰 (픽셀당 1회 대입)
let dirtyMinX = Infinity, dirtyMinY = Infinity, dirtyMaxX = -Infinity, dirtyMaxY = -Infinity
let overlayFrame = 0            // rAF 핸들
let overlayFullRedraw = false   // 마스크 전체가 갈아엎힌 경우(undo/자동감지 등)
let overlayGuideOnly = false    // 마스크는 그대로, 위에 얹는 가이드만 갱신
let cursorNeedsDraw = false     // 큰 브러시 커서를 오버레이에 직접 그려야 하는지
let cursorX = 0, cursorY = 0

// 마스크 픽셀 색 (RGBA little-endian → ABGR 로 패킹)
// r=226, g=179, b=64, a=80
const MASK_RGBA32 = (80 << 24) | (64 << 16) | (179 << 8) | 226

// 마스크 경계 상자를 증분 추적 — 예전엔 mouseup 마다 w*h 이중 루프로 다시 계산했다
let boundsMinX = Infinity, boundsMinY = Infinity, boundsMaxX = -Infinity, boundsMaxY = -Infinity
let boundsDirty = true          // 지우개로 줄어들 수 있으므로 필요 시 전체 재계산
let maskPixelCount = 0

// ── 영역 이동(MovePanel) 상태 ──
let moveActive = false
let moveDX = 0, moveDY = 0
let moveStartX = 0, moveStartY = 0
let moveSnapshot: ImageData | null = null   // 이동 시작 시점의 화면 픽셀

// ── 원근 보정 상태 ──
// 꼭짓점 4개를 드래그해 '원본에서 직사각형이어야 할 영역'을 지정하면
// 백엔드(core/editor_ops.perspective)가 그 사다리꼴을 정직사각형으로 편다.
// 순서는 백엔드 기대값과 동일: 좌상 → 우상 → 우하 → 좌하
let perspectiveActive = false
let perspectivePoints: Point[] = []
let perspectiveDragIdx = -1
const PERSPECTIVE_HANDLE_PX = 9   // 화면 기준 반경 (줌과 무관하게 일정하게 보이도록)
const PERSPECTIVE_LABELS = ['1', '2', '3', '4']

const canvasStyle = computed(() => {
  let cursor = 'crosshair'
  if (panning) cursor = 'grabbing'
  else if (props.tool === 'perspective') cursor = 'move'
  else if (props.tool === 'brush' || props.tool === 'eraser' || props.tool === 'stamp') {
    const rawSize = Math.round(props.brushSize * zoom.value * 2)
    if (rawSize <= 120) {
      // 작은 크기: SVG 커서
      const displaySize = Math.max(6, rawSize)
      const half = displaySize / 2
      const color = props.tool === 'eraser' ? '%23f87171' : props.tool === 'stamp' ? '%2360a5fa' : '%23E2B340'
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${displaySize}' height='${displaySize}'><circle cx='${half}' cy='${half}' r='${half-1}' fill='none' stroke='${color}' stroke-width='1.5'/><line x1='${half}' y1='${half-3}' x2='${half}' y2='${half+3}' stroke='${color}' stroke-width='0.8'/><line x1='${half-3}' y1='${half}' x2='${half+3}' y2='${half}' stroke='${color}' stroke-width='0.8'/></svg>`
      cursor = `url("data:image/svg+xml,${svg}") ${half} ${half}, crosshair`
    } else {
      // 큰 크기: 커서 숨기고 캔버스에 직접 그림 (onMouseMove에서 처리)
      cursor = 'none'
    }
  }
  return {
    transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value}) rotate(${rotation.value}deg)`,
    transformOrigin: 'center center',
    cursor,
  }
})

// ── 이미지 로드 (zoom/rotation 보존 옵션) ──
function loadNewImage(src: string, preserveTransform = false) {
  if (!src) return
  if (!preserveTransform) {
    savedZoom = 1; savedRotation = 0; savedPanX = 0; savedPanY = 0
  } else {
    savedZoom = zoom.value; savedRotation = rotation.value
    savedPanX = panX.value; savedPanY = panY.value
  }
  const img = new Image()
  img.onload = () => {
    const prevW = sourceImg?.naturalWidth ?? 0
    const prevH = sourceImg?.naturalHeight ?? 0
    sourceImg = img
    imgWidth.value = img.naturalWidth
    imgHeight.value = img.naturalHeight
    zoom.value = savedZoom
    rotation.value = savedRotation
    panX.value = savedPanX
    panY.value = savedPanY

    // 크기가 바뀌었으면(회전/크롭/리사이즈, 또는 다른 이미지) 마스크 버퍼를 새로 잡는다.
    // 예전에는 preserveTransform=true 경로에서 이걸 건너뛰어 stale 마스크가 남았다.
    const sizeChanged = prevW !== img.naturalWidth || prevH !== img.naturalHeight
    if (!preserveTransform || sizeChanged) {
      maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
      maskImageData = null
      resetMaskBounds()
      hasMask.value = false
      restoreMask = null
      restoreDirty = false
    }

    // ★ pristine(원본) 스냅샷은 '이미지가 실제로 교체될 때마다' 갱신해야 한다.
    // 예전에는 최초 1회만 만들어서 —
    //   · 다른 이미지를 열면 모자이크 지우개가 이전 이미지 픽셀을 칠했고
    //   · 회전/크롭 뒤에는 크기가 안 맞아 어긋난 픽셀이나 검은색을 칠했다.
    // 모자이크를 막 적용한 직후에는 '적용 전 그림'이 있어야 지우개가 의미가 있으므로
    // 호출자가 keepPristine 으로 유지 여부를 지정한다.
    if (!preserveTransform || sizeChanged || !pristineImg || !keepPristineOnce) {
      const pc = document.createElement('canvas')
      pc.width = img.naturalWidth; pc.height = img.naturalHeight
      const pctx = pc.getContext('2d', { willReadFrequently: true })!
      pctx.drawImage(img, 0, 0)
      pristineImg = pc
      pristineCtx = pctx
    }
    keepPristineOnce = false

    drawAll()
  }
  img.src = src
}

// 다음 이미지 교체 1회에 한해 pristine 스냅샷을 유지한다.
// (모자이크/블러를 적용한 직후 — 지우개가 '적용 전' 픽셀을 되살릴 수 있어야 함)
let keepPristineOnce = false
function keepPristineForNextLoad() { keepPristineOnce = true }

watch(() => props.imageSrc, (src: string) => {
  // 효과 적용 후 이미지 교체 시 transform 유지
  const preserve = sourceImg !== null
  loadNewImage(src, preserve)
})

function initMask() {
  if (!sourceImg) return
  const need = sourceImg.naturalWidth * sourceImg.naturalHeight
  if (!maskData || maskData.length !== need) {
    maskData = new Uint8Array(need)
    resetMaskBounds()
    maskImageData = null   // 크기가 바뀌었으니 오버레이 버퍼도 새로 만든다
    markDirtyAll()
  }
}

function resetMaskBounds() {
  boundsMinX = Infinity; boundsMinY = Infinity
  boundsMaxX = -Infinity; boundsMaxY = -Infinity
  boundsDirty = false
  maskPixelCount = 0
}

/** 페인트할 때마다 경계 상자를 넓힌다 (mouseup 마다 전체 스캔하지 않기 위해) */
function growBounds(x1: number, y1: number, x2: number, y2: number) {
  if (x1 < boundsMinX) boundsMinX = x1
  if (y1 < boundsMinY) boundsMinY = y1
  if (x2 > boundsMaxX) boundsMaxX = x2
  if (y2 > boundsMaxY) boundsMaxY = y2
}

/** 변경된 사각형을 dirty 영역에 합친다 */
function markDirty(x1: number, y1: number, x2: number, y2: number) {
  if (x1 < dirtyMinX) dirtyMinX = x1
  if (y1 < dirtyMinY) dirtyMinY = y1
  if (x2 > dirtyMaxX) dirtyMaxX = x2
  if (y2 > dirtyMaxY) dirtyMaxY = y2
  scheduleOverlay()
}

function markDirtyAll() {
  overlayFullRedraw = true
  if (sourceImg) markDirty(0, 0, sourceImg.naturalWidth, sourceImg.naturalHeight)
  else scheduleOverlay()
}

/** 마스크 픽셀은 그대로고 위에 얹는 가이드(원근 사각형/올가미 경로 등)만 바뀐 경우.
 *  maskData→픽셀 변환 루프를 건너뛰고 기존 ImageData를 다시 올리기만 한다.
 *  (4K에서 드래그마다 830만 회 루프를 도는 것을 피하려는 것 — dirty-rect와 같은 이유) */
function markGuideDirty() {
  overlayGuideOnly = true
  scheduleOverlay()
}

/** 실제 캔버스 반영은 프레임당 1회로 합친다 — 포인터 이벤트가 초당 수백 건 와도 안전 */
function scheduleOverlay() {
  if (overlayFrame) return
  overlayFrame = requestAnimationFrame(() => {
    overlayFrame = 0
    flushMaskOverlay()
  })
}

function ensureMaskBuffers(w: number, h: number) {
  if (!maskImageData || maskImageData.width !== w || maskImageData.height !== h) {
    maskImageData = new ImageData(w, h)
    maskPixels = new Uint32Array(maskImageData.data.buffer)
    overlayFullRedraw = true
  }
}

/** dirty 사각형만 다시 칠하고 putImageData 로 그 영역만 올린다 */
function flushMaskOverlay() {
  if (!maskCtx || !maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  ensureMaskBuffers(w, h)
  if (!maskPixels || !maskImageData) return

  // 가이드만 바뀐 프레임 — 픽셀 변환 루프를 건너뛰고 기존 버퍼를 다시 올린다
  if (overlayGuideOnly && !overlayFullRedraw && dirtyMaxX < dirtyMinX) {
    overlayGuideOnly = false
    maskCtx.putImageData(maskImageData, 0, 0)
    drawTransientOverlay()
    return
  }
  overlayGuideOnly = false

  let x1 = Math.max(0, Math.floor(dirtyMinX))
  let y1 = Math.max(0, Math.floor(dirtyMinY))
  let x2 = Math.min(w, Math.ceil(dirtyMaxX))
  let y2 = Math.min(h, Math.ceil(dirtyMaxY))
  if (overlayFullRedraw) { x1 = 0; y1 = 0; x2 = w; y2 = h; overlayFullRedraw = false }

  const hasDirty = x2 > x1 && y2 > y1
  if (hasDirty) {
    for (let y = y1; y < y2; y++) {
      const row = y * w
      for (let x = x1; x < x2; x++) {
        const i = row + x
        maskPixels[i] = maskData[i] > 0 ? MASK_RGBA32 : 0
      }
    }
    // 마스크 레이어는 전체를 다시 올리지 않고 변경 영역만 갱신
    maskCtx.putImageData(maskImageData, 0, 0, x1, y1, x2 - x1, y2 - y1)
  }
  dirtyMinX = Infinity; dirtyMinY = Infinity
  dirtyMaxX = -Infinity; dirtyMaxY = -Infinity

  hasMask.value = maskPixelCount > 0 || boundsDirty ? computeHasMask() : false

  // 오버레이 위에 임시로 그리는 것들(선택 박스, 올가미 경로, 큰 브러시 커서)
  drawTransientOverlay()
}

/** hasMask 는 화면 표시용이라 정확도보다 비용이 중요 — 카운터로 판단하고,
 *  지우개로 0이 될 수 있는 경우에만 실제로 확인한다. */
function computeHasMask(): boolean {
  if (maskPixelCount > 0) return true
  if (!boundsDirty || !maskData) return false
  return recomputeBounds()
}

/** 지우개로 마스크가 줄어든 뒤 정확한 경계가 필요할 때만 전체 스캔 (mouseup 1회) */
function recomputeBounds(): boolean {
  if (!maskData || !sourceImg) return false
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = w, minY = h, maxX = -1, maxY = -1, count = 0
  for (let y = 0; y < h; y++) {
    const row = y * w
    let rowHit = false
    for (let x = 0; x < w; x++) {
      if (maskData[row + x] > 0) {
        count++
        rowHit = true
        if (x < minX) minX = x
        if (x > maxX) maxX = x
      }
    }
    if (rowHit) {
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
  }
  maskPixelCount = count
  boundsDirty = false
  if (maxX < 0) {
    boundsMinX = Infinity; boundsMinY = Infinity
    boundsMaxX = -Infinity; boundsMaxY = -Infinity
    return false
  }
  boundsMinX = minX; boundsMinY = minY
  boundsMaxX = maxX + 1; boundsMaxY = maxY + 1
  return true
}

function drawAll() {
  if (!canvasEl.value || !sourceImg) return
  const c = canvasEl.value
  c.width = sourceImg.naturalWidth
  c.height = sourceImg.naturalHeight
  // willReadFrequently — 모자이크 지우개가 getImageData 를 반복 호출하므로
  // 이 힌트가 없으면 Chromium 이 GPU 경로로 두고 매번 느린 리드백을 한다
  ctx = c.getContext('2d', { willReadFrequently: true })!
  ctx.clearRect(0, 0, c.width, c.height)
  ctx.drawImage(sourceImg, 0, 0)
  const mc = maskCanvasEl.value
  if (mc) {
    mc.width = c.width; mc.height = c.height
    maskCtx = mc.getContext('2d')
    maskImageData = null
    markDirtyAll()
    flushMaskOverlay()
  }
}

/** 화면 1px이 이미지 좌표로 몇 px인지 — 핸들/선 두께를 줌과 무관하게 유지 */
function imagePerScreenPx(): number {
  const c = canvasEl.value
  if (!c) return 1
  const baseScale = (c.clientWidth || 1) / (c.width || 1)
  const total = baseScale * (zoom.value || 1)
  return total > 0 ? 1 / total : 1
}

/** 매 프레임 오버레이 위에 다시 그려야 하는 일회성 요소들 */
function drawTransientOverlay() {
  if (!maskCtx) return
  if (perspectiveActive) { drawPerspectiveGuide(); return }
  if (drawing && props.tool === 'box') {
    strokeDashRect(startX, startY, lastBrushX - startX, lastBrushY - startY, '#E2B340')
  } else if (drawing && props.tool === 'eraser' && props.eraserMode === 'box') {
    strokeDashRect(startX, startY, lastBrushX - startX, lastBrushY - startY, '#f87171')
  } else if (drawing && (props.tool === 'lasso'
              || (props.tool === 'eraser' && props.eraserMode === 'lasso'))) {
    strokeLasso(props.tool === 'lasso' ? '#E2B340' : '#f87171')
  }
  if (cursorNeedsDraw) drawBigCursor()
}

function strokeDashRect(x: number, y: number, w: number, h: number, color: string) {
  if (!maskCtx) return
  maskCtx.strokeStyle = color
  maskCtx.lineWidth = 2 / zoom.value
  maskCtx.setLineDash([6 / zoom.value, 4 / zoom.value])
  maskCtx.strokeRect(x, y, w, h)
  maskCtx.setLineDash([])
}

function strokeLasso(color: string) {
  if (!maskCtx || lassoPoints.length < 2) return
  maskCtx.strokeStyle = color
  maskCtx.lineWidth = 2 / zoom.value
  maskCtx.setLineDash([4 / zoom.value, 3 / zoom.value])
  maskCtx.beginPath()
  maskCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
  for (let i = 1; i < lassoPoints.length; i++) maskCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
  maskCtx.closePath()
  maskCtx.stroke()
  maskCtx.setLineDash([])
  if (color === '#E2B340') {
    maskCtx.fillStyle = 'rgba(226, 179, 64, 0.1)'
    maskCtx.fill()
  }
}

function drawBigCursor() {
  if (!maskCtx) return
  const color = props.tool === 'eraser' ? 'rgba(248,113,113,0.5)'
    : props.tool === 'stamp' ? 'rgba(96,165,250,0.5)' : 'rgba(226,179,64,0.5)'
  maskCtx.strokeStyle = color
  maskCtx.lineWidth = 2
  if (props.tool === 'stamp' && props.stampShape === 'bar') {
    maskCtx.strokeRect(cursorX - props.barWidth / 2, cursorY - props.barHeight / 2,
                       props.barWidth, props.barHeight)
  } else {
    maskCtx.beginPath()
    maskCtx.arc(cursorX, cursorY, props.brushSize, 0, Math.PI * 2)
    maskCtx.stroke()
  }
  maskCtx.lineWidth = 1
  maskCtx.beginPath(); maskCtx.moveTo(cursorX - 5, cursorY); maskCtx.lineTo(cursorX + 5, cursorY); maskCtx.stroke()
  maskCtx.beginPath(); maskCtx.moveTo(cursorX, cursorY - 5); maskCtx.lineTo(cursorX, cursorY + 5); maskCtx.stroke()
}

/** 원근 보정 가이드 — 사각형 + 꼭짓점 핸들 + 3분할 그리드 */
function drawPerspectiveGuide() {
  if (!maskCtx || perspectivePoints.length !== 4) return
  const px = imagePerScreenPx()
  const ctx2 = maskCtx

  // 바깥 영역을 어둡게 — 어디가 펴질 부분인지 한눈에
  if (sourceImg) {
    ctx2.save()
    ctx2.beginPath()
    ctx2.rect(0, 0, sourceImg.naturalWidth, sourceImg.naturalHeight)
    ctx2.moveTo(perspectivePoints[0].x, perspectivePoints[0].y)
    for (let i = 3; i >= 1; i--) ctx2.lineTo(perspectivePoints[i].x, perspectivePoints[i].y)
    ctx2.closePath()
    ctx2.fillStyle = 'rgba(0, 0, 0, 0.45)'
    ctx2.fill('evenodd')
    ctx2.restore()
  }

  // 사각형 외곽선
  ctx2.strokeStyle = '#E2B340'
  ctx2.lineWidth = 2 * px
  ctx2.beginPath()
  ctx2.moveTo(perspectivePoints[0].x, perspectivePoints[0].y)
  for (let i = 1; i < 4; i++) ctx2.lineTo(perspectivePoints[i].x, perspectivePoints[i].y)
  ctx2.closePath()
  ctx2.stroke()

  // 3분할 그리드 — 변을 따라 보간해서 기울기를 눈으로 확인
  ctx2.strokeStyle = 'rgba(226, 179, 64, 0.35)'
  ctx2.lineWidth = 1 * px
  const lerp = (a: Point, b: Point, t: number): Point => ({
    x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t,
  })
  for (const t of [1 / 3, 2 / 3]) {
    const top = lerp(perspectivePoints[0], perspectivePoints[1], t)
    const bottom = lerp(perspectivePoints[3], perspectivePoints[2], t)
    ctx2.beginPath(); ctx2.moveTo(top.x, top.y); ctx2.lineTo(bottom.x, bottom.y); ctx2.stroke()
    const left = lerp(perspectivePoints[0], perspectivePoints[3], t)
    const right = lerp(perspectivePoints[1], perspectivePoints[2], t)
    ctx2.beginPath(); ctx2.moveTo(left.x, left.y); ctx2.lineTo(right.x, right.y); ctx2.stroke()
  }

  // 꼭짓점 핸들
  const r = PERSPECTIVE_HANDLE_PX * px
  for (let i = 0; i < 4; i++) {
    const p = perspectivePoints[i]
    const active = i === perspectiveDragIdx
    ctx2.beginPath()
    ctx2.arc(p.x, p.y, r, 0, Math.PI * 2)
    ctx2.fillStyle = active ? '#E2B340' : 'rgba(20, 20, 20, 0.85)'
    ctx2.fill()
    ctx2.strokeStyle = '#E2B340'
    ctx2.lineWidth = 2 * px
    ctx2.stroke()
    // 순서 번호 (좌상 1 → 시계방향)
    ctx2.fillStyle = active ? '#000' : '#E2B340'
    ctx2.font = `${Math.round(11 * px)}px sans-serif`
    ctx2.textAlign = 'center'
    ctx2.textBaseline = 'middle'
    ctx2.fillText(PERSPECTIVE_LABELS[i], p.x, p.y)
  }
  ctx2.textAlign = 'start'
  ctx2.textBaseline = 'alphabetic'
}

/** 클릭 지점에서 가장 가까운 꼭짓점 인덱스 (히트 반경 안일 때만) */
function hitPerspectiveHandle(x: number, y: number): number {
  const r = PERSPECTIVE_HANDLE_PX * imagePerScreenPx() * 1.8   // 넉넉하게
  let best = -1
  let bestDist = r * r
  for (let i = 0; i < perspectivePoints.length; i++) {
    const dx = perspectivePoints[i].x - x
    const dy = perspectivePoints[i].y - y
    const d = dx * dx + dy * dy
    if (d <= bestDist) { bestDist = d; best = i }
  }
  return best
}

/** 원근 보정 시작 — 이미지 모서리에서 5% 안쪽으로 꼭짓점 4개 배치
 *  (PyQt판 perspective_dialog.py 와 동일한 초기값) */
function beginPerspective() {
  if (!sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const m = 0.05
  perspectivePoints = [
    { x: w * m, y: h * m },
    { x: w * (1 - m), y: h * m },
    { x: w * (1 - m), y: h * (1 - m) },
    { x: w * m, y: h * (1 - m) },
  ]
  perspectiveDragIdx = -1
  perspectiveActive = true
  markDirtyAll()
  flushMaskOverlay()
}

/** 확정 — 꼭짓점 4개를 [[x,y] x4] 로 반환 (백엔드 corners 형식) */
function endPerspective(): number[][] | null {
  if (!perspectiveActive || perspectivePoints.length !== 4) return null
  const corners = perspectivePoints.map(p => [Math.round(p.x), Math.round(p.y)])
  perspectiveActive = false
  perspectivePoints = []
  perspectiveDragIdx = -1
  markDirtyAll()
  flushMaskOverlay()
  return corners
}

function cancelPerspective() {
  perspectiveActive = false
  perspectivePoints = []
  perspectiveDragIdx = -1
  markDirtyAll()
  flushMaskOverlay()
}

/** 하위 호환 alias — 외부/기존 호출부가 쓰던 이름 */
function renderMaskOverlay() {
  markDirtyAll()
  flushMaskOverlay()
}

// ── 좌표 변환: 화면 → 이미지 ──
// FIX 1 (이전): 회전 미반영 — getBoundingClientRect의 AABB로 비율 계산
// FIX 2 (이번): CSS max-width로 캔버스가 축소 표시되는 경우, zoom으로 나누면
//              실제 표시 배율과 안 맞아 클릭 위치가 좌측 위로 어긋남.
//              base scale = clientWidth/canvas.width 로 정확히 계산.
function getImagePos(e: MouseEvent | PointerEvent): Point {
  if (!canvasEl.value) return { x: 0, y: 0 }
  const c = canvasEl.value
  const rect = c.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  // 1) 화면 좌표 → AABB 중심 기준 상대 벡터
  const dx = e.clientX - cx
  const dy = e.clientY - cy
  // 2) CSS 레이아웃 배율 (max-width 등 반영) + zoom 적용 = 총 화면-내부 배율
  //    clientWidth/Height는 transform 적용 전 CSS 크기 → 안정적
  const baseScale = (c.clientWidth || 1) / (c.width || 1)
  const totalScale = baseScale * (zoom.value || 1)
  if (totalScale === 0) return { x: c.width / 2, y: c.height / 2 }
  const sx = dx / totalScale
  const sy = dy / totalScale
  // 3) 역 회전 (-rotation rad)
  const theta = -rotation.value * Math.PI / 180
  const cos = Math.cos(theta), sin = Math.sin(theta)
  const lx = sx * cos - sy * sin
  const ly = sx * sin + sy * cos
  // 4) 중심 기준 → 캔버스 좌상단 기준 (내부 좌표)
  return {
    x: lx + c.width / 2,
    y: ly + c.height / 2,
  }
}

// ── 변환 초기화 (확대/회전/이동 전부 reset) ──
function resetTransform() {
  zoom.value = 1
  rotation.value = 0
  panX.value = 0
  panY.value = 0
}

// ── Alt 더블클릭: 위치 복귀 ──
function onDblClick(e: MouseEvent) {
  if (e.altKey) resetTransform()
}

function saveMaskState() {
  if (maskData) {
    maskUndoStack.push(new Uint8Array(maskData))
    while (maskUndoStack.length > MAX_MASK_UNDO) maskUndoStack.shift()
    maskRedoStack = []
    maskUndoCount.value = maskUndoStack.length
    maskRedoCount.value = 0
  }
}
// 마스크를 한 단계 되돌림. 되돌렸으면 true(이미지 undo로 안 넘어가도록), 없으면 false.
function undoMask(): boolean {
  if (maskUndoStack.length === 0 || !maskData) return false
  const snapshot = maskUndoStack.pop()!
  // 크기가 다른 스냅샷(이미지가 바뀐 뒤 남은 stale 항목)은 버린다
  if (snapshot.length !== maskData.length) {
    maskUndoStack = []; maskRedoStack = []
    maskUndoCount.value = 0; maskRedoCount.value = 0
    return false
  }
  maskRedoStack.push(new Uint8Array(maskData))
  maskData.set(snapshot)
  maskUndoCount.value = maskUndoStack.length
  maskRedoCount.value = maskRedoStack.length
  boundsDirty = true
  recomputeBounds()
  markDirtyAll(); flushMaskOverlay(); emitMaskBounds()
  return true
}
function redoMask(): boolean {
  if (maskRedoStack.length === 0 || !maskData) return false
  const snapshot = maskRedoStack.pop()!
  if (snapshot.length !== maskData.length) {
    maskRedoStack = []
    maskRedoCount.value = 0
    return false
  }
  maskUndoStack.push(new Uint8Array(maskData))
  maskData.set(snapshot)
  maskUndoCount.value = maskUndoStack.length
  maskRedoCount.value = maskRedoStack.length
  boundsDirty = true
  recomputeBounds()
  markDirtyAll(); flushMaskOverlay(); emitMaskBounds()
  return true
}

function onMouseDown(e: PointerEvent) {
  // 포인터 캡처 — 이게 없으면 빠른 드래그가 컨테이너 밖으로 나가는 순간
  // pointerleave 가 떠서 스트로크가 그 자리에서 끊겼다
  try { (e.currentTarget as Element)?.setPointerCapture?.(e.pointerId) } catch {}

  if (e.altKey || e.button === 1) {
    panning = true
    panStartX = e.clientX - panX.value
    panStartY = e.clientY - panY.value
    return
  }
  // 원근 보정 모드 — 꼭짓점만 잡고 마스킹은 하지 않는다
  if (perspectiveActive) {
    const p = getImagePos(e)
    perspectiveDragIdx = hitPerspectiveHandle(p.x, p.y)
    drawing = perspectiveDragIdx >= 0
    if (drawing) { markGuideDirty(); scheduleOverlay() }
    return
  }

  initMask()
  const pos = getImagePos(e)
  drawing = true
  startX = pos.x; startY = pos.y
  lastBrushX = pos.x; lastBrushY = pos.y
  stampAccum = 0

  // 영역 이동 모드에서는 마스킹 대신 드래그로 옮긴다
  if (moveActive) {
    moveStartX = pos.x - moveDX
    moveStartY = pos.y - moveDY
    return
  }

  // 압력 감응 — 펜 입력일 때만 적용 (마우스는 항상 0.5로 고정되어 의미 없음)
  // 펜 압력 0~1 → 0.3~1.2 배율로 매핑 (최소 30% 보장, 최대 120%)
  const sizeFor = (base: number) => {
    if (e.pointerType === 'pen' && typeof e.pressure === 'number' && e.pressure > 0) {
      return Math.max(2, base * (0.3 + 0.9 * Math.min(1, e.pressure)))
    }
    return base
  }
  const brushR = sizeFor(props.brushSize)

  // maskData가 즉시 바뀌는 도구만 undo 스냅샷 저장 (box/lasso는 mouseup 적용 시 저장 —
  //  빈 클릭/미세 드래그가 빈 undo 단계로 쌓이거나 redo를 날리는 것 방지)
  if (props.tool === 'brush' || props.tool === 'stamp'
      || (props.tool === 'eraser' && (props.eraserRestore || props.eraserMode === 'brush'))) {
    saveMaskState()
  }
  if (props.tool === 'lasso') {
    const sp = props.magneticLasso ? snapToEdge(pos.x, pos.y) : pos
    lassoPoints = [{ x: sp.x, y: sp.y }]
  } else if (props.tool === 'brush') {
    paintMaskCircle(pos.x, pos.y, brushR)
    renderMaskOverlay()
  } else if (props.tool === 'stamp') {
    paintStamp(pos.x, pos.y)
    renderMaskOverlay()
  } else if (props.tool === 'eraser') {
    if (props.eraserRestore) {
      restoreCircle(pos.x, pos.y, brushR)
    } else if (props.eraserMode === 'brush') {
      eraseMaskCircle(pos.x, pos.y, brushR)
      renderMaskOverlay()
    } else {
      lassoPoints = props.eraserMode === 'lasso' ? [{ x: pos.x, y: pos.y }] : []
    }
  }
}

function onMouseMoveWrap(e: PointerEvent) {
  // 큰 브러시일 땐 커서를 오버레이에 직접 그린다(네이티브 커서가 120px를 넘으면 잘림).
  // 예전에는 여기서 renderMaskOverlay()를 한 번 더 불러 프레임당 전체 스캔이 2회 돌았다.
  // 이제는 플래그만 세우고 실제 그리기는 rAF 한 번에서 처리한다.
  const rawSize = Math.round(props.brushSize * zoom.value * 2)
  const wantCursor = rawSize > 120
    && (props.tool === 'brush' || props.tool === 'eraser' || props.tool === 'stamp')
  if (wantCursor) {
    const pos = getImagePos(e)
    cursorX = pos.x; cursorY = pos.y
  }
  // 커서를 껐다 켤 때 잔상이 남지 않게 해당 프레임은 전체를 다시 칠한다
  if (cursorNeedsDraw || wantCursor) {
    cursorNeedsDraw = wantCursor
    markGuideDirty()
  }
  onMouseMove(e)
  if (wantCursor) scheduleOverlay()
}

function onMouseMove(e: PointerEvent) {
  if (panning) {
    panX.value = e.clientX - panStartX
    panY.value = e.clientY - panStartY
    return
  }
  if (perspectiveActive) {
    if (drawing && perspectiveDragIdx >= 0 && sourceImg) {
      const p = getImagePos(e)
      // 이미지 밖으로 나가지 않게 클램프 — warpPerspective가 빈 영역을 만들지 않도록
      perspectivePoints[perspectiveDragIdx] = {
        x: Math.max(0, Math.min(sourceImg.naturalWidth, p.x)),
        y: Math.max(0, Math.min(sourceImg.naturalHeight, p.y)),
      }
      markGuideDirty()
      scheduleOverlay()
    }
    return
  }
  if (moveActive && drawing) {
    const pos = getImagePos(e)
    moveDX = pos.x - moveStartX
    moveDY = pos.y - moveStartY
    renderMovePreview()
    return
  }
  if (!drawing) return
  const pos = getImagePos(e)

  if (props.tool === 'box') {
    // 점선 사각형은 매 프레임 drawTransientOverlay()가 그린다 —
    // 여기서는 좌표만 갱신하고 전체 스캔은 하지 않는다
    lastBrushX = pos.x; lastBrushY = pos.y
    markGuideDirty()
  } else if (props.tool === 'lasso') {
    const sp = props.magneticLasso ? snapToEdge(pos.x, pos.y) : pos
    lassoPoints.push({ x: sp.x, y: sp.y })
    markGuideDirty()
  } else if (props.tool === 'brush') {
    // 펜 압력에 따라 브러시 반경 동적 조정 (마우스는 props.brushSize 그대로)
    let brushR = props.brushSize
    if (e.pointerType === 'pen' && typeof e.pressure === 'number' && e.pressure > 0) {
      brushR = Math.max(2, props.brushSize * (0.3 + 0.9 * Math.min(1, e.pressure)))
    }
    paintMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, brushR)
    lastBrushX = pos.x; lastBrushY = pos.y
  } else if (props.tool === 'stamp') {
    // STAMP: 일정 간격마다 원형 마스킹
    const dx = pos.x - lastBrushX, dy = pos.y - lastBrushY
    const dist = Math.sqrt(dx * dx + dy * dy)
    stampAccum += dist
    if (stampAccum >= props.stampSpacing) {
      paintStamp(pos.x, pos.y)
      stampAccum = 0
    }
    lastBrushX = pos.x; lastBrushY = pos.y
  } else if (props.tool === 'eraser') {
    if (props.eraserRestore) {
      restoreLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
      lastBrushX = pos.x; lastBrushY = pos.y
    } else if (props.eraserMode === 'brush') {
      eraseMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
      lastBrushX = pos.x; lastBrushY = pos.y
    } else if (props.eraserMode === 'box') {
      lastBrushX = pos.x; lastBrushY = pos.y
      markGuideDirty()
    } else if (props.eraserMode === 'lasso') {
      lassoPoints.push({ x: pos.x, y: pos.y })
      markGuideDirty()
    }
  }
}

function onMouseUp(e: PointerEvent) {
  try { (e.currentTarget as Element)?.releasePointerCapture?.(e.pointerId) } catch {}
  if (panning) { panning = false; return }
  if (perspectiveActive) {
    drawing = false
    perspectiveDragIdx = -1
    markGuideDirty(); scheduleOverlay()
    return
  }
  if (!drawing) return
  drawing = false
  if (moveActive) return   // 이동 미리보기는 확정/취소 때 정리한다

  // 모자이크 지우개는 화면 캔버스만 바꾼다 — 파일에 남기려면 부모가 커밋해야 한다
  if (props.tool === 'eraser' && props.eraserRestore && restoreDirty) {
    emit('restore-ready')
    return
  }
  const pos = getImagePos(e)

  if (props.tool === 'box') {
    const x1 = Math.round(Math.min(startX, pos.x)), y1 = Math.round(Math.min(startY, pos.y))
    const x2 = Math.round(Math.max(startX, pos.x)), y2 = Math.round(Math.max(startY, pos.y))
    if (x2 - x1 > 3 && y2 - y1 > 3) { saveMaskState(); fillMaskRect(x1, y1, x2, y2) }
  } else if (props.tool === 'lasso') {
    if (lassoPoints.length > 2) { saveMaskState(); fillMaskPolygon(lassoPoints) }
    lassoPoints = []
  } else if (props.tool === 'eraser') {
    if (props.eraserMode === 'box') {
      const x1 = Math.round(Math.min(startX, pos.x)), y1 = Math.round(Math.min(startY, pos.y))
      const x2 = Math.round(Math.max(startX, pos.x)), y2 = Math.round(Math.max(startY, pos.y))
      if (x2 - x1 > 3 && y2 - y1 > 3) { saveMaskState(); eraseMaskRect(x1, y1, x2, y2) }
    } else if (props.eraserMode === 'lasso') {
      if (lassoPoints.length > 2) { saveMaskState(); eraseMaskPolygon(lassoPoints) }
      lassoPoints = []
    }
  }
  // 지운 뒤에는 경계가 부정확할 수 있으니 여기서 한 번만 정확히 다시 잡는다
  if (boundsDirty) recomputeBounds()
  markGuideDirty()
  scheduleOverlay()
  emitMaskBounds()
}

// ── 마스크 조작 ──
function paintMaskBar(cx: number, cy: number, bw: number, bh: number) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const x1 = Math.max(0, Math.round(cx - bw / 2))
  const y1 = Math.max(0, Math.round(cy - bh / 2))
  const x2 = Math.min(w, Math.round(cx + bw / 2))
  const y2 = Math.min(h, Math.round(cy + bh / 2))
  for (let y = y1; y < y2; y++) {
    const row = y * w
    for (let x = x1; x < x2; x++) {
      if (maskData[row + x] === 0) { maskData[row + x] = 255; maskPixelCount++ }
    }
  }
  growBounds(x1, y1, x2, y2)
  markDirty(x1, y1, x2, y2)
}

function paintStamp(cx: number, cy: number) {
  if (props.stampShape === 'bar') paintMaskBar(cx, cy, props.barWidth, props.barHeight)
  else if (props.stampShape === 'rect') paintMaskBar(cx, cy, props.brushSize * 2, props.brushSize * 2)
  else paintMaskCircle(cx, cy, props.brushSize)
}

function paintMaskCircle(cx: number, cy: number, r: number) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  const rr = radius * radius
  const x1 = Math.max(0, Math.floor(cx - radius)), x2 = Math.min(w, Math.ceil(cx + radius))
  const y1 = Math.max(0, Math.floor(cy - radius)), y2 = Math.min(h, Math.ceil(cy + radius))
  for (let y = y1; y < y2; y++) {
    const row = y * w
    const dy = y - cy
    const dy2 = dy * dy
    for (let x = x1; x < x2; x++) {
      const dx = x - cx
      if (dx * dx + dy2 <= rr && maskData[row + x] === 0) {
        maskData[row + x] = 255
        maskPixelCount++
      }
    }
  }
  growBounds(x1, y1, x2, y2)
  markDirty(x1, y1, x2, y2)
}
function paintMaskLine(x0: number, y0: number, x1: number, y1: number, r: number) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, r * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    paintMaskCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r)
  }
}
function eraseMaskCircle(cx: number, cy: number, r: number) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  const rr = radius * radius
  const x1 = Math.max(0, Math.floor(cx - radius)), x2 = Math.min(w, Math.ceil(cx + radius))
  const y1 = Math.max(0, Math.floor(cy - radius)), y2 = Math.min(h, Math.ceil(cy + radius))
  for (let y = y1; y < y2; y++) {
    const row = y * w
    const dy = y - cy
    const dy2 = dy * dy
    for (let x = x1; x < x2; x++) {
      const dx = x - cx
      if (dx * dx + dy2 <= rr && maskData[row + x] !== 0) {
        maskData[row + x] = 0
        maskPixelCount--
      }
    }
  }
  // 지우면 경계가 줄어들 수 있다 — 정확한 경계는 mouseup 때 한 번만 재계산
  boundsDirty = true
  markDirty(x1, y1, x2, y2)
}
function eraseMaskLine(x0: number, y0: number, x1: number, y1: number, r: number) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, r * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    eraseMaskCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r)
  }
}
function fillMaskRect(x1: number, y1: number, x2: number, y2: number) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const cx1 = Math.max(0, x1), cx2 = Math.min(w, x2)
  const cy1 = Math.max(0, y1), cy2 = Math.min(h, y2)
  for (let y = cy1; y < cy2; y++) {
    const row = y * w
    for (let x = cx1; x < cx2; x++) {
      if (maskData[row + x] === 0) { maskData[row + x] = 255; maskPixelCount++ }
    }
  }
  growBounds(cx1, cy1, cx2, cy2)
  markDirty(cx1, cy1, cx2, cy2)
}
function eraseMaskRect(x1: number, y1: number, x2: number, y2: number) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const cx1 = Math.max(0, x1), cx2 = Math.min(w, x2)
  const cy1 = Math.max(0, y1), cy2 = Math.min(h, y2)
  for (let y = cy1; y < cy2; y++) {
    const row = y * w
    for (let x = cx1; x < cx2; x++) {
      if (maskData[row + x] !== 0) { maskData[row + x] = 0; maskPixelCount-- }
    }
  }
  boundsDirty = true
  markDirty(cx1, cy1, cx2, cy2)
}
function _polygonBBox(pts: Point[], w: number, h: number) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of pts) {
    if (p.x < minX) minX = p.x
    if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x
    if (p.y > maxY) maxY = p.y
  }
  return {
    x1: Math.max(0, Math.floor(minX)), y1: Math.max(0, Math.floor(minY)),
    x2: Math.min(w, Math.ceil(maxX)), y2: Math.min(h, Math.ceil(maxY)),
  }
}
function fillMaskPolygon(pts: Point[]) {
  if (!maskData || !sourceImg || pts.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const { x1, y1, x2, y2 } = _polygonBBox(pts, w, h)
  for (let y = y1; y < y2; y++) {
    const row = y * w
    for (let x = x1; x < x2; x++) {
      if (pip(x, y, pts) && maskData[row + x] === 0) { maskData[row + x] = 255; maskPixelCount++ }
    }
  }
  growBounds(x1, y1, x2, y2)
  markDirty(x1, y1, x2, y2)
}
function eraseMaskPolygon(pts: Point[]) {
  if (!maskData || !sourceImg || pts.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const { x1, y1, x2, y2 } = _polygonBBox(pts, w, h)
  for (let y = y1; y < y2; y++) {
    const row = y * w
    for (let x = x1; x < x2; x++) {
      if (pip(x, y, pts) && maskData[row + x] !== 0) { maskData[row + x] = 0; maskPixelCount-- }
    }
  }
  boundsDirty = true
  markDirty(x1, y1, x2, y2)
}
function pip(x: number, y: number, poly: Point[]) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// ── 모자이크 지우개 (원본 복원) ──────────────────────────────────────────────
// 복원한 픽셀은 화면 캔버스에만 있으면 저장에 반영되지 않는다(저장은 파일 경로 기반).
// 그래서 복원 영역을 restoreMask 에 기록해 두고, 지우개를 뗄 때 부모가
// getRestoreMaskBase64() 로 가져가 백엔드에 'restore' 로 커밋한다.
let restoreMask: Uint8Array | null = null
let restoreDirty = false

function ensureRestoreMask() {
  if (!sourceImg) return
  const need = sourceImg.naturalWidth * sourceImg.naturalHeight
  if (!restoreMask || restoreMask.length !== need) restoreMask = new Uint8Array(need)
}

/** 한 스트로크 구간을 한 번의 getImageData/putImageData 로 처리.
 *  예전에는 보간 스텝마다(수십 회) 리드백을 해서 지우개가 가장 느린 도구였다. */
function restoreLine(x0: number, y0: number, x1: number, y1: number, r: number) {
  if (!ctx || !pristineImg || !pristineCtx || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  // pristine 이 현재 이미지와 크기가 다르면(회전/크롭 후) 복원은 무의미하다
  if (pristineImg.width !== w || pristineImg.height !== h) return

  const bx1 = Math.max(0, Math.floor(Math.min(x0, x1) - radius))
  const by1 = Math.max(0, Math.floor(Math.min(y0, y1) - radius))
  const bx2 = Math.min(w, Math.ceil(Math.max(x0, x1) + radius))
  const by2 = Math.min(h, Math.ceil(Math.max(y0, y1) + radius))
  const sw = bx2 - bx1, sh = by2 - by1
  if (sw <= 0 || sh <= 0) return

  ensureRestoreMask()
  const src = pristineCtx.getImageData(bx1, by1, sw, sh)
  const dst = ctx.getImageData(bx1, by1, sw, sh)

  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, radius * 0.3)))
  const rr = radius * radius

  for (let s = 0; s <= steps; s++) {
    const t = steps === 0 ? 0 : s / steps
    const cx = x0 + (x1 - x0) * t
    const cy = y0 + (y1 - y0) * t
    const px1 = Math.max(bx1, Math.floor(cx - radius))
    const py1 = Math.max(by1, Math.floor(cy - radius))
    const px2 = Math.min(bx2, Math.ceil(cx + radius))
    const py2 = Math.min(by2, Math.ceil(cy + radius))
    for (let py = py1; py < py2; py++) {
      const dy = py - cy
      const dy2 = dy * dy
      const rowOff = (py - by1) * sw
      for (let px = px1; px < px2; px++) {
        const dx = px - cx
        if (dx * dx + dy2 > rr) continue
        const i = (rowOff + (px - bx1)) * 4
        dst.data[i] = src.data[i]
        dst.data[i + 1] = src.data[i + 1]
        dst.data[i + 2] = src.data[i + 2]
        dst.data[i + 3] = src.data[i + 3]
        if (restoreMask) restoreMask[py * w + px] = 255
      }
    }
  }
  ctx.putImageData(dst, bx1, by1)
  restoreDirty = true
}

function restoreCircle(cx: number, cy: number, r: number) {
  restoreLine(cx, cy, cx, cy, r)
}

/** 복원 영역을 흑백 PNG 마스크로 — 백엔드가 pristine 픽셀을 되돌리는 데 쓴다 */
function getRestoreMaskBase64(): string | null {
  if (!restoreDirty || !restoreMask || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const tc = document.createElement('canvas'); tc.width = w; tc.height = h
  const tctx = tc.getContext('2d')!
  const id = tctx.createImageData(w, h)
  const px = new Uint32Array(id.data.buffer)
  for (let i = 0; i < restoreMask.length; i++) {
    px[i] = restoreMask[i] > 0 ? 0xffffffff : 0xff000000
  }
  tctx.putImageData(id, 0, 0)
  return tc.toDataURL('image/png')
}

function hasPendingRestore(): boolean { return restoreDirty }

function clearRestoreMask() {
  if (restoreMask) restoreMask.fill(0)
  restoreDirty = false
}

// ── 자석 올가미: edge map 로드 + snap ──
function loadEdgeMap(b64: string) {
  if (!b64) return
  const img = new Image()
  img.onload = () => {
    const tc = document.createElement('canvas')
    tc.width = img.naturalWidth; tc.height = img.naturalHeight
    const tctx = tc.getContext('2d')!
    tctx.drawImage(img, 0, 0)
    const id = tctx.getImageData(0, 0, tc.width, tc.height)
    edgeMapW = tc.width; edgeMapH = tc.height
    edgeMapData = new Uint8Array(edgeMapW * edgeMapH)
    for (let i = 0; i < edgeMapData.length; i++) edgeMapData[i] = id.data[i * 4]
  }
  img.src = b64
}

function snapToEdge(x: number, y: number): Point {
  if (!edgeMapData || !props.magneticLasso) return { x, y }
  const r = props.snapRadius
  let bestDist = Infinity, bx = x, by = y
  const x0 = Math.max(0, Math.floor(x - r)), y0 = Math.max(0, Math.floor(y - r))
  const x1 = Math.min(edgeMapW, Math.ceil(x + r)), y1 = Math.min(edgeMapH, Math.ceil(y + r))
  for (let py = y0; py < y1; py++) {
    for (let px = x0; px < x1; px++) {
      if (edgeMapData[py * edgeMapW + px] > 127) {
        const d = (px - x) ** 2 + (py - y) ** 2
        if (d < bestDist) { bestDist = d; bx = px; by = py }
      }
    }
  }
  return { x: bx, y: by }
}

function emitMaskBounds() {
  const sel = getSelection()
  if (sel) emit('selection-changed', sel)
  hasMask.value = sel !== null
}

function onWheel(e: WheelEvent) {
  if (e.shiftKey) { rotation.value += e.deltaY > 0 ? 5 : -5 }
  else { zoom.value = Math.max(0.1, Math.min(10, zoom.value * (e.deltaY > 0 ? 0.9 : 1.1))) }
}

function clearSelection(resetHistory = false) {
  if (maskData) maskData.fill(0)
  resetMaskBounds()
  hasMask.value = false; lassoPoints = []
  // 이미지 작업/새 이미지 로드 후에만(resetHistory=true) 마스크 히스토리 리셋 — stale 마스크
  // undo가 이미지 undo를 가리지 않게. Esc/취소(기본 false)는 보존 → Ctrl+Z로 마스크 복구 가능.
  if (resetHistory) {
    maskUndoStack = []; maskRedoStack = []
    maskUndoCount.value = 0; maskRedoCount.value = 0
  }
  markDirtyAll()
  flushMaskOverlay()
}

/** 마스크 경계 상자. 증분 추적한 값을 쓰고, 지우개 이후에만 한 번 재계산한다.
 *  (예전에는 호출할 때마다 w*h 이중 루프를 돌았다 — 4K에서 830만 회) */
function getSelection(): SelectionBounds | null {
  if (!maskData || !sourceImg) return null
  if (boundsDirty) recomputeBounds()
  if (boundsMaxX <= boundsMinX || boundsMaxY <= boundsMinY) return null
  return {
    x: boundsMinX, y: boundsMinY,
    w: boundsMaxX - boundsMinX, h: boundsMaxY - boundsMinY,
  }
}

function getMaskBase64() {
  if (!maskData || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const tc = document.createElement('canvas'); tc.width = w; tc.height = h
  const tctx = tc.getContext('2d')!
  const id = tctx.createImageData(w, h)
  // 32bit 뷰로 픽셀당 1회 대입 (0xAABBGGRR, little-endian)
  const px = new Uint32Array(id.data.buffer)
  for (let i = 0; i < maskData.length; i++) {
    px[i] = maskData[i] > 0 ? 0xffffffff : 0xff000000
  }
  tctx.putImageData(id, 0, 0)
  return tc.toDataURL('image/png')
}

// 외부에서 마스크 로드 (YOLO/SAM3 auto-detect 결과)
function loadMaskFromBase64(b64: string) {
  if (!sourceImg) return
  const img = new Image()
  img.onload = () => {
    if (!sourceImg) return
    const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
    const tc = document.createElement('canvas'); tc.width = w; tc.height = h
    const tctx = tc.getContext('2d', { willReadFrequently: true })!
    tctx.drawImage(img, 0, 0, w, h)
    const id = tctx.getImageData(0, 0, w, h)
    initMask()
    if (!maskData) return
    saveMaskState()   // 자동 감지 마스크도 undo 한 단계로 (통합 undo에서 마스크 우선 되돌림)
    // maskData.length 로 돌면 캔버스 크기와 어긋날 수 있어 w*h 기준으로 순회
    const n = Math.min(maskData.length, w * h)
    let count = 0
    for (let i = 0; i < n; i++) {
      const on = id.data[i * 4] > 127
      maskData[i] = on ? 255 : 0
      if (on) count++
    }
    maskPixelCount = count
    boundsDirty = true
    recomputeBounds()
    markDirtyAll()
    flushMaskOverlay()
    emitMaskBounds()
  }
  img.src = b64
}

// ── 영역 이동 미리보기 ──────────────────────────────────────────────────────
// 확정 전까지는 화면에서만 옮겨 보여주고, 실제 픽셀 연산은 백엔드 move_region이 한다.
function beginMove() {
  if (!ctx || !sourceImg) return
  const sel = getSelection()
  if (!sel) return
  moveActive = true
  moveDX = 0; moveDY = 0
  moveSnapshot = ctx.getImageData(0, 0, sourceImg.naturalWidth, sourceImg.naturalHeight)
}

function renderMovePreview() {
  if (!ctx || !moveSnapshot || !maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const out = ctx.createImageData(w, h)
  const src = moveSnapshot.data
  const dst = out.data
  // 배경: 마스크 밖은 그대로, 마스크 안(원래 자리)은 검게 비움
  for (let i = 0; i < w * h; i++) {
    const o = i * 4
    if (maskData[i] > 0) {
      dst[o] = 0; dst[o + 1] = 0; dst[o + 2] = 0; dst[o + 3] = 255
    } else {
      dst[o] = src[o]; dst[o + 1] = src[o + 1]; dst[o + 2] = src[o + 2]; dst[o + 3] = src[o + 3]
    }
  }
  // 옮겨진 조각을 덧그린다
  const dx = Math.round(moveDX), dy = Math.round(moveDY)
  for (let y = 0; y < h; y++) {
    const ty = y + dy
    if (ty < 0 || ty >= h) continue
    for (let x = 0; x < w; x++) {
      if (maskData[y * w + x] === 0) continue
      const tx = x + dx
      if (tx < 0 || tx >= w) continue
      const so = (y * w + x) * 4
      const to = (ty * w + tx) * 4
      dst[to] = src[so]; dst[to + 1] = src[so + 1]
      dst[to + 2] = src[so + 2]; dst[to + 3] = src[so + 3]
    }
  }
  ctx.putImageData(out, 0, 0)
}

function endMove(): { dx: number; dy: number } {
  const result = { dx: Math.round(moveDX), dy: Math.round(moveDY) }
  moveActive = false
  moveSnapshot = null
  moveDX = 0; moveDY = 0
  return result
}

function cancelMove() {
  if (ctx && moveSnapshot) ctx.putImageData(moveSnapshot, 0, 0)
  moveActive = false
  moveSnapshot = null
  moveDX = 0; moveDY = 0
}

// zoom/rotation 초기화
function resetView() { resetTransform() }  // 하위 호환 alias

defineExpose({
  clearSelection, getSelection, getMaskBase64, loadMaskFromBase64, loadEdgeMap,
  drawAll, resetView, resetTransform, undoMask, redoMask, maskUndoCount, maskRedoCount,
  // 모자이크 지우개 커밋용 — 화면에만 있던 복원을 백엔드에 반영하기 위해
  getRestoreMaskBase64, hasPendingRestore, clearRestoreMask, keepPristineForNextLoad,
  // 영역 이동
  beginMove, endMove, cancelMove,
  // 원근 보정
  beginPerspective, endPerspective, cancelPerspective,
})

onMounted(() => {
  if (props.imageSrc) loadNewImage(props.imageSrc, false)
})

onBeforeUnmount(() => {
  // rAF 핸들 정리 — 탭을 떠난 뒤에도 프레임이 돌면 누수가 된다
  if (overlayFrame) { cancelAnimationFrame(overlayFrame); overlayFrame = 0 }
})
</script>

<style scoped>
.canvas-container {
  width: 100%; height: 100%; position: relative;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; background: #111;
}
/* 90% 제한은 고정폭 사이드패널과 겹쳐 이미지가 창의 약 59%만 쓰게 했다.
   baseScale(=clientWidth/width)이 실측값을 읽으므로 좌표 변환은 그대로 성립한다. */
canvas { max-width: 100%; max-height: 100%; position: absolute; }
.mask-overlay { pointer-events: none; }
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px;
  background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px;
  pointer-events: none; z-index: 2;
}
</style>
