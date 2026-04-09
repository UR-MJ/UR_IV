<template>
  <div class="canvas-container" ref="containerRef"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown" @mousemove="onMouseMoveWrap" @mouseup="onMouseUp"
    @mouseleave="onMouseUp" @contextmenu.prevent
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

<script setup>
import { ref, computed, watch, onMounted } from 'vue'

const props = defineProps({
  imageSrc: { type: String, default: '' },
  tool: { type: String, default: 'box' },
  brushSize: { type: Number, default: 20 },
  eraserMode: { type: String, default: 'brush' },
  eraserRestore: { type: Boolean, default: false },
  stampSpacing: { type: Number, default: 30 },
  stampShape: { type: String, default: 'circle' }, // 'circle' or 'bar'
  barWidth: { type: Number, default: 40 },
  barHeight: { type: Number, default: 15 },
  magneticLasso: { type: Boolean, default: false },
  snapRadius: { type: Number, default: 12 },
})

const emit = defineEmits(['selection-changed', 'mask-changed'])

const containerRef = ref(null)
const canvasEl = ref(null)
const maskCanvasEl = ref(null)
const imgWidth = ref(0)
const imgHeight = ref(0)
const zoom = ref(1)
const rotation = ref(0)
const panX = ref(0)
const panY = ref(0)
const hasMask = ref(false)

let ctx = null
let maskCtx = null
let sourceImg = null
let drawing = false
let panning = false
let startX = 0, startY = 0
let panStartX = 0, panStartY = 0
let lastBrushX = -1, lastBrushY = -1
let lassoPoints = []
let maskData = null
let lastAltClick = 0  // Alt 더블클릭 감지
let stampAccum = 0
let savedZoom = 1, savedRotation = 0, savedPanX = 0, savedPanY = 0
let pristineImg = null  // 원본 이미지 (모자이크 지우개용)
let edgeMapData = null  // Canny edge map (자석 올가미용) — Uint8Array
let edgeMapW = 0, edgeMapH = 0

const canvasStyle = computed(() => {
  let cursor = 'crosshair'
  if (panning) cursor = 'grabbing'
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
function loadNewImage(src, preserveTransform = false) {
  if (!src) return
  if (!preserveTransform) {
    savedZoom = 1; savedRotation = 0; savedPanX = 0; savedPanY = 0
  } else {
    savedZoom = zoom.value; savedRotation = rotation.value
    savedPanX = panX.value; savedPanY = panY.value
  }
  const img = new Image()
  img.onload = () => {
    sourceImg = img
    imgWidth.value = img.naturalWidth
    imgHeight.value = img.naturalHeight
    zoom.value = savedZoom
    rotation.value = savedRotation
    panX.value = savedPanX
    panY.value = savedPanY
    if (!preserveTransform) {
      maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
      hasMask.value = false
      // 원본 이미지 저장 (모자이크 지우개용)
      const pc = document.createElement('canvas')
      pc.width = img.naturalWidth; pc.height = img.naturalHeight
      pc.getContext('2d').drawImage(img, 0, 0)
      pristineImg = pc
    }
    drawAll()
  }
  img.src = src
}

watch(() => props.imageSrc, (src) => {
  // 효과 적용 후 이미지 교체 시 transform 유지
  const preserve = sourceImg !== null
  loadNewImage(src, preserve)
})

function initMask() {
  if (!sourceImg) return
  if (!maskData || maskData.length !== sourceImg.naturalWidth * sourceImg.naturalHeight) {
    maskData = new Uint8Array(sourceImg.naturalWidth * sourceImg.naturalHeight)
  }
}

function drawAll() {
  if (!canvasEl.value || !sourceImg) return
  const c = canvasEl.value
  c.width = sourceImg.naturalWidth
  c.height = sourceImg.naturalHeight
  ctx = c.getContext('2d')
  ctx.clearRect(0, 0, c.width, c.height)
  ctx.drawImage(sourceImg, 0, 0)
  const mc = maskCanvasEl.value
  if (mc) {
    mc.width = c.width; mc.height = c.height
    maskCtx = mc.getContext('2d')
    renderMaskOverlay()
  }
}

function renderMaskOverlay() {
  if (!maskCtx || !maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  maskCtx.clearRect(0, 0, w, h)
  const imgData = maskCtx.createImageData(w, h)
  let anyMask = false
  for (let i = 0; i < maskData.length; i++) {
    if (maskData[i] > 0) {
      anyMask = true
      imgData.data[i * 4] = 226; imgData.data[i * 4 + 1] = 179
      imgData.data[i * 4 + 2] = 64; imgData.data[i * 4 + 3] = 80
    }
  }
  maskCtx.putImageData(imgData, 0, 0)
  hasMask.value = anyMask
}

// ── 좌표 변환: 화면 → 이미지 (getBoundingClientRect 기반 — CSS 변환 포함) ──
function getImagePos(e) {
  if (!canvasEl.value) return { x: 0, y: 0 }
  // getBoundingClientRect는 CSS transform(zoom/rotate/pan)이 적용된 후의 실제 화면 좌표를 반환
  const rect = canvasEl.value.getBoundingClientRect()
  // 화면 좌표 → 캔버스 내부 비율 좌표 (0~1)
  const ratioX = (e.clientX - rect.left) / rect.width
  const ratioY = (e.clientY - rect.top) / rect.height
  // 이미지 좌표로 변환
  const imgX = ratioX * canvasEl.value.width
  const imgY = ratioY * canvasEl.value.height
  return { x: imgX, y: imgY }
}

// ── Alt 더블클릭: 위치 복귀 ──
function onDblClick(e) {
  if (e.altKey) {
    zoom.value = 1; rotation.value = 0; panX.value = 0; panY.value = 0
  }
}

function onMouseDown(e) {
  if (e.altKey || e.button === 1) {
    panning = true
    panStartX = e.clientX - panX.value
    panStartY = e.clientY - panY.value
    return
  }
  initMask()
  const pos = getImagePos(e)
  drawing = true
  startX = pos.x; startY = pos.y
  lastBrushX = pos.x; lastBrushY = pos.y
  stampAccum = 0

  if (props.tool === 'lasso') {
    const sp = props.magneticLasso ? snapToEdge(pos.x, pos.y) : pos
    lassoPoints = [{ x: sp.x, y: sp.y }]
  } else if (props.tool === 'brush') {
    paintMaskCircle(pos.x, pos.y, props.brushSize)
    renderMaskOverlay()
  } else if (props.tool === 'stamp') {
    paintStamp(pos.x, pos.y)
    renderMaskOverlay()
  } else if (props.tool === 'eraser') {
    if (props.eraserRestore) {
      // 모자이크 지우개: 원본에서 해당 영역 복원
      restoreCircle(pos.x, pos.y, props.brushSize)
    } else if (props.eraserMode === 'brush') {
      eraseMaskCircle(pos.x, pos.y, props.brushSize)
      renderMaskOverlay()
    } else {
      lassoPoints = props.eraserMode === 'lasso' ? [{ x: pos.x, y: pos.y }] : []
    }
  }
}

function onMouseMoveWrap(e) {
  onMouseMove(e)
  // 큰 커서를 마스크 오버레이에 직접 그리기
  const rawSize = Math.round(props.brushSize * zoom.value * 2)
  if (rawSize > 120 && maskCtx && (props.tool === 'brush' || props.tool === 'eraser' || props.tool === 'stamp')) {
    renderMaskOverlay()
    const pos = getImagePos(e)
    const r = props.brushSize
    const color = props.tool === 'eraser' ? 'rgba(248,113,113,0.5)' : props.tool === 'stamp' ? 'rgba(96,165,250,0.5)' : 'rgba(226,179,64,0.5)'
    if (props.tool === 'stamp' && props.stampShape === 'bar') {
      maskCtx.strokeStyle = color; maskCtx.lineWidth = 2
      maskCtx.strokeRect(pos.x - props.barWidth/2, pos.y - props.barHeight/2, props.barWidth, props.barHeight)
    } else {
      maskCtx.strokeStyle = color; maskCtx.lineWidth = 2
      maskCtx.beginPath(); maskCtx.arc(pos.x, pos.y, r, 0, Math.PI * 2); maskCtx.stroke()
    }
    // 십자선
    maskCtx.strokeStyle = color; maskCtx.lineWidth = 1
    maskCtx.beginPath(); maskCtx.moveTo(pos.x - 5, pos.y); maskCtx.lineTo(pos.x + 5, pos.y); maskCtx.stroke()
    maskCtx.beginPath(); maskCtx.moveTo(pos.x, pos.y - 5); maskCtx.lineTo(pos.x, pos.y + 5); maskCtx.stroke()
  }
}

function onMouseMove(e) {
  if (panning) {
    panX.value = e.clientX - panStartX
    panY.value = e.clientY - panStartY
    return
  }
  if (!drawing) return
  const pos = getImagePos(e)

  if (props.tool === 'box') {
    renderMaskOverlay()
    if (maskCtx) {
      maskCtx.strokeStyle = '#E2B340'
      maskCtx.lineWidth = 2 / zoom.value
      maskCtx.setLineDash([6 / zoom.value, 4 / zoom.value])
      maskCtx.strokeRect(startX, startY, pos.x - startX, pos.y - startY)
      maskCtx.setLineDash([])
    }
  } else if (props.tool === 'lasso') {
    const sp = props.magneticLasso ? snapToEdge(pos.x, pos.y) : pos
    lassoPoints.push({ x: sp.x, y: sp.y })
    renderMaskOverlay()
    if (maskCtx && lassoPoints.length > 1) {
      maskCtx.strokeStyle = '#E2B340'
      maskCtx.lineWidth = 2 / zoom.value
      maskCtx.setLineDash([4 / zoom.value, 3 / zoom.value])
      maskCtx.beginPath()
      maskCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
      for (let i = 1; i < lassoPoints.length; i++) maskCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
      maskCtx.closePath()
      maskCtx.stroke()
      maskCtx.setLineDash([])
      maskCtx.fillStyle = 'rgba(226, 179, 64, 0.1)'
      maskCtx.fill()
    }
  } else if (props.tool === 'brush') {
    paintMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
    lastBrushX = pos.x; lastBrushY = pos.y
    renderMaskOverlay()
  } else if (props.tool === 'stamp') {
    // STAMP: 일정 간격마다 원형 마스킹
    const dx = pos.x - lastBrushX, dy = pos.y - lastBrushY
    const dist = Math.sqrt(dx * dx + dy * dy)
    stampAccum += dist
    if (stampAccum >= props.stampSpacing) {
      paintStamp(pos.x, pos.y)
      stampAccum = 0
      renderMaskOverlay()
    }
    lastBrushX = pos.x; lastBrushY = pos.y
  } else if (props.tool === 'eraser') {
    if (props.eraserRestore) {
      restoreLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
      lastBrushX = pos.x; lastBrushY = pos.y
    } else if (props.eraserMode === 'brush') {
      eraseMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
      lastBrushX = pos.x; lastBrushY = pos.y
      renderMaskOverlay()
    } else if (props.eraserMode === 'box') {
      renderMaskOverlay()
      if (maskCtx) {
        maskCtx.strokeStyle = '#f87171'; maskCtx.lineWidth = 2 / zoom.value
        maskCtx.setLineDash([6 / zoom.value, 4 / zoom.value])
        maskCtx.strokeRect(startX, startY, pos.x - startX, pos.y - startY)
        maskCtx.setLineDash([])
      }
    } else if (props.eraserMode === 'lasso') {
      lassoPoints.push({ x: pos.x, y: pos.y })
      renderMaskOverlay()
      if (maskCtx && lassoPoints.length > 1) {
        maskCtx.strokeStyle = '#f87171'; maskCtx.lineWidth = 2 / zoom.value
        maskCtx.beginPath()
        maskCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
        for (let i = 1; i < lassoPoints.length; i++) maskCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
        maskCtx.closePath(); maskCtx.stroke()
      }
    }
  }
}

function onMouseUp(e) {
  if (panning) { panning = false; return }
  if (!drawing) return
  drawing = false
  const pos = getImagePos(e)

  if (props.tool === 'box') {
    const x1 = Math.round(Math.min(startX, pos.x)), y1 = Math.round(Math.min(startY, pos.y))
    const x2 = Math.round(Math.max(startX, pos.x)), y2 = Math.round(Math.max(startY, pos.y))
    if (x2 - x1 > 3 && y2 - y1 > 3) fillMaskRect(x1, y1, x2, y2)
  } else if (props.tool === 'lasso') {
    if (lassoPoints.length > 2) fillMaskPolygon(lassoPoints)
    lassoPoints = []
  } else if (props.tool === 'eraser') {
    if (props.eraserMode === 'box') {
      const x1 = Math.round(Math.min(startX, pos.x)), y1 = Math.round(Math.min(startY, pos.y))
      const x2 = Math.round(Math.max(startX, pos.x)), y2 = Math.round(Math.max(startY, pos.y))
      if (x2 - x1 > 3 && y2 - y1 > 3) eraseMaskRect(x1, y1, x2, y2)
    } else if (props.eraserMode === 'lasso') {
      if (lassoPoints.length > 2) eraseMaskPolygon(lassoPoints)
      lassoPoints = []
    }
  }
  renderMaskOverlay()
  emitMaskBounds()
}

// ── 마스크 조작 ──
function paintMaskBar(cx, cy, bw, bh) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const x1 = Math.max(0, Math.round(cx - bw / 2))
  const y1 = Math.max(0, Math.round(cy - bh / 2))
  const x2 = Math.min(w, Math.round(cx + bw / 2))
  const y2 = Math.min(h, Math.round(cy + bh / 2))
  for (let y = y1; y < y2; y++) for (let x = x1; x < x2; x++) maskData[y * w + x] = 255
}

function paintStamp(cx, cy) {
  if (props.stampShape === 'bar') paintMaskBar(cx, cy, props.barWidth, props.barHeight)
  else paintMaskCircle(cx, cy, props.brushSize)
}

function paintMaskCircle(cx, cy, r) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  for (let y = Math.max(0, Math.floor(cy - radius)); y < Math.min(h, Math.ceil(cy + radius)); y++) {
    for (let x = Math.max(0, Math.floor(cx - radius)); x < Math.min(w, Math.ceil(cx + radius)); x++) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2) maskData[y * w + x] = 255
    }
  }
}
function paintMaskLine(x0, y0, x1, y1, r) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, r * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    paintMaskCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r)
  }
}
function eraseMaskCircle(cx, cy, r) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  for (let y = Math.max(0, Math.floor(cy - radius)); y < Math.min(h, Math.ceil(cy + radius)); y++) {
    for (let x = Math.max(0, Math.floor(cx - radius)); x < Math.min(w, Math.ceil(cx + radius)); x++) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2) maskData[y * w + x] = 0
    }
  }
}
function eraseMaskLine(x0, y0, x1, y1, r) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, r * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    eraseMaskCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r)
  }
}
function fillMaskRect(x1, y1, x2, y2) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  for (let y = Math.max(0, y1); y < Math.min(h, y2); y++)
    for (let x = Math.max(0, x1); x < Math.min(w, x2); x++) maskData[y * w + x] = 255
}
function eraseMaskRect(x1, y1, x2, y2) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  for (let y = Math.max(0, y1); y < Math.min(h, y2); y++)
    for (let x = Math.max(0, x1); x < Math.min(w, x2); x++) maskData[y * w + x] = 0
}
function fillMaskPolygon(pts) {
  if (!maskData || !sourceImg || pts.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of pts) { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y) }
  for (let y = Math.max(0, Math.floor(minY)); y < Math.min(h, Math.ceil(maxY)); y++)
    for (let x = Math.max(0, Math.floor(minX)); x < Math.min(w, Math.ceil(maxX)); x++)
      if (pip(x, y, pts)) maskData[y * w + x] = 255
}
function eraseMaskPolygon(pts) {
  if (!maskData || !sourceImg || pts.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of pts) { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y) }
  for (let y = Math.max(0, Math.floor(minY)); y < Math.min(h, Math.ceil(maxY)); y++)
    for (let x = Math.max(0, Math.floor(minX)); x < Math.min(w, Math.ceil(maxX)); x++)
      if (pip(x, y, pts)) maskData[y * w + x] = 0
}
function pip(x, y, poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// ── 모자이크 지우개 (원본 복원) ──
function restoreCircle(cx, cy, r) {
  if (!ctx || !pristineImg || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const radius = Math.max(1, r)
  const x1 = Math.max(0, Math.floor(cx - radius))
  const y1 = Math.max(0, Math.floor(cy - radius))
  const x2 = Math.min(w, Math.ceil(cx + radius))
  const y2 = Math.min(h, Math.ceil(cy + radius))
  const sw = x2 - x1, sh = y2 - y1
  if (sw <= 0 || sh <= 0) return
  // pristine에서 해당 영역 가져오기
  const pCtx = pristineImg.getContext('2d')
  const srcData = pCtx.getImageData(x1, y1, sw, sh)
  const dstData = ctx.getImageData(x1, y1, sw, sh)
  // 원형 영역만 복원
  for (let dy = 0; dy < sh; dy++) {
    for (let dx = 0; dx < sw; dx++) {
      const px = x1 + dx, py = y1 + dy
      if ((px - cx) ** 2 + (py - cy) ** 2 <= radius ** 2) {
        const i = (dy * sw + dx) * 4
        dstData.data[i] = srcData.data[i]
        dstData.data[i+1] = srcData.data[i+1]
        dstData.data[i+2] = srcData.data[i+2]
        dstData.data[i+3] = srcData.data[i+3]
      }
    }
  }
  ctx.putImageData(dstData, x1, y1)
}
function restoreLine(x0, y0, x1, y1, r) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, r * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    restoreCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r)
  }
}

// ── 자석 올가미: edge map 로드 + snap ──
function loadEdgeMap(b64) {
  if (!b64) return
  const img = new Image()
  img.onload = () => {
    const tc = document.createElement('canvas')
    tc.width = img.naturalWidth; tc.height = img.naturalHeight
    const tctx = tc.getContext('2d')
    tctx.drawImage(img, 0, 0)
    const id = tctx.getImageData(0, 0, tc.width, tc.height)
    edgeMapW = tc.width; edgeMapH = tc.height
    edgeMapData = new Uint8Array(edgeMapW * edgeMapH)
    for (let i = 0; i < edgeMapData.length; i++) edgeMapData[i] = id.data[i * 4]
  }
  img.src = b64
}

function snapToEdge(x, y) {
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
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = w, minY = h, maxX = 0, maxY = 0, any = false
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (maskData[y * w + x] > 0) { any = true; minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y) }
  }
  if (any) emit('selection-changed', { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 })
  hasMask.value = any
}

function onWheel(e) {
  if (e.shiftKey) { rotation.value += e.deltaY > 0 ? 5 : -5 }
  else { zoom.value = Math.max(0.1, Math.min(10, zoom.value * (e.deltaY > 0 ? 0.9 : 1.1))) }
}

function clearSelection() {
  if (maskData) maskData.fill(0)
  hasMask.value = false; lassoPoints = []
  renderMaskOverlay()
}

function getSelection() {
  if (!maskData || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = w, minY = h, maxX = 0, maxY = 0, any = false
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (maskData[y * w + x] > 0) { any = true; minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y) }
  }
  return any ? { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 } : null
}

function getMaskBase64() {
  if (!maskData || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const tc = document.createElement('canvas'); tc.width = w; tc.height = h
  const tctx = tc.getContext('2d')
  const id = tctx.createImageData(w, h)
  for (let i = 0; i < maskData.length; i++) { id.data[i*4] = id.data[i*4+1] = id.data[i*4+2] = maskData[i]; id.data[i*4+3] = 255 }
  tctx.putImageData(id, 0, 0)
  return tc.toDataURL('image/png')
}

// 외부에서 마스크 로드 (YOLO auto-detect 결과)
function loadMaskFromBase64(b64) {
  if (!sourceImg) return
  const img = new Image()
  img.onload = () => {
    const tc = document.createElement('canvas'); tc.width = sourceImg.naturalWidth; tc.height = sourceImg.naturalHeight
    const tctx = tc.getContext('2d'); tctx.drawImage(img, 0, 0, tc.width, tc.height)
    const id = tctx.getImageData(0, 0, tc.width, tc.height)
    initMask()
    for (let i = 0; i < maskData.length; i++) { if (id.data[i * 4] > 127) maskData[i] = 255 }
    renderMaskOverlay()
    emitMaskBounds()
  }
  img.src = b64
}

// zoom/rotation 초기화
function resetView() { zoom.value = 1; rotation.value = 0; panX.value = 0; panY.value = 0 }

defineExpose({ clearSelection, getSelection, getMaskBase64, loadMaskFromBase64, loadEdgeMap, drawAll, resetView })

onMounted(() => {
  if (props.imageSrc) loadNewImage(props.imageSrc, false)
})
</script>

<style scoped>
.canvas-container {
  width: 100%; height: 100%; position: relative;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; background: #111;
}
canvas { max-width: 90%; max-height: 90%; position: absolute; }
.mask-overlay { pointer-events: none; }
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px;
  background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px;
  pointer-events: none; z-index: 2;
}
</style>
