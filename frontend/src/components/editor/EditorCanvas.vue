<template>
  <div class="canvas-container" ref="containerRef"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
  >
    <canvas ref="canvasEl" :style="canvasStyle" />
    <!-- 마스크 오버레이 캔버스 (선택 영역 시각화) -->
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
  eraserMode: { type: String, default: 'brush' }, // 'brush' | 'box' | 'lasso'
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

// lasso 전용 상태
let lassoPoints = []

// 마스크 데이터 (누적 — 다중 영역 지원)
let maskData = null  // Uint8Array, 0 or 255 per pixel

const canvasStyle = computed(() => {
  let cursor = 'crosshair'
  if (panning) cursor = 'grabbing'
  else if (props.tool === 'brush' || props.tool === 'eraser') {
    // 브러시/지우개: 원형 커서 (SVG 기반)
    const size = Math.max(4, Math.round(props.brushSize * zoom.value * 2))
    const half = size / 2
    const color = props.tool === 'eraser' ? '%23f87171' : '%23E2B340'
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}'><circle cx='${half}' cy='${half}' r='${half - 1}' fill='none' stroke='${color}' stroke-width='1.5'/><line x1='${half}' y1='${half-3}' x2='${half}' y2='${half+3}' stroke='${color}' stroke-width='1'/><line x1='${half-3}' y1='${half}' x2='${half+3}' y2='${half}' stroke='${color}' stroke-width='1'/></svg>`
    cursor = `url("data:image/svg+xml,${svg}") ${half} ${half}, crosshair`
  }

  return {
    transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value}) rotate(${rotation.value}deg)`,
    transformOrigin: 'center center',
    cursor,
  }
})

watch(() => props.imageSrc, (src) => {
  if (!src) return
  const img = new Image()
  img.onload = () => {
    sourceImg = img
    imgWidth.value = img.naturalWidth
    imgHeight.value = img.naturalHeight
    zoom.value = 1
    rotation.value = 0
    panX.value = 0
    panY.value = 0
    // 마스크 초기화
    maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
    hasMask.value = false
    drawAll()
  }
  img.src = src
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

  // 마스크 오버레이 캔버스
  const mc = maskCanvasEl.value
  if (mc) {
    mc.width = c.width
    mc.height = c.height
    maskCtx = mc.getContext('2d')
    renderMaskOverlay()
  }
}

function renderMaskOverlay() {
  if (!maskCtx || !maskData || !sourceImg) return
  const w = sourceImg.naturalWidth
  const h = sourceImg.naturalHeight
  maskCtx.clearRect(0, 0, w, h)

  // 마스크가 있는 영역을 반투명 노랑으로 표시
  const imgData = maskCtx.createImageData(w, h)
  let anyMask = false
  for (let i = 0; i < maskData.length; i++) {
    if (maskData[i] > 0) {
      anyMask = true
      imgData.data[i * 4] = 226     // R
      imgData.data[i * 4 + 1] = 179 // G
      imgData.data[i * 4 + 2] = 64  // B
      imgData.data[i * 4 + 3] = 80  // A (반투명)
    }
  }
  maskCtx.putImageData(imgData, 0, 0)
  hasMask.value = anyMask
}

function getImagePos(e) {
  if (!canvasEl.value) return { x: 0, y: 0 }
  const rect = canvasEl.value.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) / (rect.width / canvasEl.value.width),
    y: (e.clientY - rect.top) / (rect.height / canvasEl.value.height),
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
  startX = pos.x
  startY = pos.y
  lastBrushX = pos.x
  lastBrushY = pos.y

  if (props.tool === 'lasso') {
    lassoPoints = [{ x: pos.x, y: pos.y }]
  } else if (props.tool === 'brush') {
    paintMaskCircle(pos.x, pos.y, props.brushSize)
    renderMaskOverlay()
  } else if (props.tool === 'eraser') {
    if (props.eraserMode === 'brush') {
      eraseMaskCircle(pos.x, pos.y, props.brushSize)
      renderMaskOverlay()
    } else {
      // box/lasso 모드 시작
      lassoPoints = props.eraserMode === 'lasso' ? [{ x: pos.x, y: pos.y }] : []
    }
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
    // 임시 사각형 표시
    drawAll()
    if (maskCtx) {
      renderMaskOverlay()
      maskCtx.strokeStyle = '#E2B340'
      maskCtx.lineWidth = 2 / zoom.value
      maskCtx.setLineDash([6 / zoom.value, 4 / zoom.value])
      maskCtx.strokeRect(startX, startY, pos.x - startX, pos.y - startY)
      maskCtx.setLineDash([])
    }
  } else if (props.tool === 'lasso') {
    lassoPoints.push({ x: pos.x, y: pos.y })
    renderMaskOverlay()
    // 올가미 경로 + 닫힌 영역 미리보기
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
    // 연속 선 그리기 (점이 아닌 선으로 연결)
    paintMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
    lastBrushX = pos.x
    lastBrushY = pos.y
    renderMaskOverlay()
  } else if (props.tool === 'eraser') {
    if (props.eraserMode === 'brush') {
      eraseMaskLine(lastBrushX, lastBrushY, pos.x, pos.y, props.brushSize)
      lastBrushX = pos.x
      lastBrushY = pos.y
      renderMaskOverlay()
    } else if (props.eraserMode === 'box') {
      renderMaskOverlay()
      if (maskCtx) {
        maskCtx.strokeStyle = '#f87171'
        maskCtx.lineWidth = 2 / zoom.value
        maskCtx.setLineDash([6 / zoom.value, 4 / zoom.value])
        maskCtx.strokeRect(startX, startY, pos.x - startX, pos.y - startY)
        maskCtx.setLineDash([])
      }
    } else if (props.eraserMode === 'lasso') {
      lassoPoints.push({ x: pos.x, y: pos.y })
      renderMaskOverlay()
      if (maskCtx && lassoPoints.length > 1) {
        maskCtx.strokeStyle = '#f87171'
        maskCtx.lineWidth = 2 / zoom.value
        maskCtx.beginPath()
        maskCtx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
        for (let i = 1; i < lassoPoints.length; i++) maskCtx.lineTo(lassoPoints[i].x, lassoPoints[i].y)
        maskCtx.stroke()
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
    const x1 = Math.round(Math.min(startX, pos.x))
    const y1 = Math.round(Math.min(startY, pos.y))
    const x2 = Math.round(Math.max(startX, pos.x))
    const y2 = Math.round(Math.max(startY, pos.y))
    if (x2 - x1 > 3 && y2 - y1 > 3) {
      fillMaskRect(x1, y1, x2, y2)
    }
  } else if (props.tool === 'lasso') {
    if (lassoPoints.length > 2) {
      fillMaskPolygon(lassoPoints)
    }
    lassoPoints = []
  } else if (props.tool === 'eraser') {
    if (props.eraserMode === 'box') {
      const x1 = Math.round(Math.min(startX, pos.x))
      const y1 = Math.round(Math.min(startY, pos.y))
      const x2 = Math.round(Math.max(startX, pos.x))
      const y2 = Math.round(Math.max(startY, pos.y))
      if (x2 - x1 > 3 && y2 - y1 > 3) {
        eraseMaskRect(x1, y1, x2, y2)
      }
    } else if (props.eraserMode === 'lasso') {
      if (lassoPoints.length > 2) {
        eraseMaskPolygon(lassoPoints)
      }
      lassoPoints = []
    }
  }
  // brush/eraser-brush는 이미 onMouseMove에서 처리됨

  renderMaskOverlay()
  emitMaskBounds()
}

// ─── 마스크 조작 함수들 ───

function paintMaskCircle(cx, cy, radius) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const r = Math.max(1, radius)
  const x1 = Math.max(0, Math.floor(cx - r))
  const y1 = Math.max(0, Math.floor(cy - r))
  const x2 = Math.min(w, Math.ceil(cx + r))
  const y2 = Math.min(h, Math.ceil(cy + r))
  for (let y = y1; y < y2; y++) {
    for (let x = x1; x < x2; x++) {
      if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r) {
        maskData[y * w + x] = 255
      }
    }
  }
}

function paintMaskLine(x0, y0, x1, y1, radius) {
  const dx = x1 - x0, dy = y1 - y0
  const dist = Math.sqrt(dx * dx + dy * dy)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, radius * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    paintMaskCircle(x0 + dx * t, y0 + dy * t, radius)
  }
}

function eraseMaskCircle(cx, cy, radius) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const r = Math.max(1, radius)
  const x1 = Math.max(0, Math.floor(cx - r))
  const y1 = Math.max(0, Math.floor(cy - r))
  const x2 = Math.min(w, Math.ceil(cx + r))
  const y2 = Math.min(h, Math.ceil(cy + r))
  for (let y = y1; y < y2; y++) {
    for (let x = x1; x < x2; x++) {
      if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r) {
        maskData[y * w + x] = 0
      }
    }
  }
}

function eraseMaskLine(x0, y0, x1, y1, radius) {
  const dx = x1 - x0, dy = y1 - y0
  const dist = Math.sqrt(dx * dx + dy * dy)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, radius * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    eraseMaskCircle(x0 + dx * t, y0 + dy * t, radius)
  }
}

function fillMaskRect(x1, y1, x2, y2) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const rx1 = Math.max(0, x1), ry1 = Math.max(0, y1)
  const rx2 = Math.min(w, x2), ry2 = Math.min(h, y2)
  for (let y = ry1; y < ry2; y++) {
    for (let x = rx1; x < rx2; x++) {
      maskData[y * w + x] = 255
    }
  }
}

function eraseMaskRect(x1, y1, x2, y2) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const rx1 = Math.max(0, x1), ry1 = Math.max(0, y1)
  const rx2 = Math.min(w, x2), ry2 = Math.min(h, y2)
  for (let y = ry1; y < ry2; y++) {
    for (let x = rx1; x < rx2; x++) {
      maskData[y * w + x] = 0
    }
  }
}

function fillMaskPolygon(points) {
  if (!maskData || !sourceImg || points.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  // 바운딩 박스
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of points) {
    if (p.x < minX) minX = p.x; if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x; if (p.y > maxY) maxY = p.y
  }
  const bx1 = Math.max(0, Math.floor(minX)), by1 = Math.max(0, Math.floor(minY))
  const bx2 = Math.min(w, Math.ceil(maxX)), by2 = Math.min(h, Math.ceil(maxY))
  // 스캔라인 (point-in-polygon)
  for (let y = by1; y < by2; y++) {
    for (let x = bx1; x < bx2; x++) {
      if (pointInPoly(x, y, points)) maskData[y * w + x] = 255
    }
  }
}

function eraseMaskPolygon(points) {
  if (!maskData || !sourceImg || points.length < 3) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of points) {
    if (p.x < minX) minX = p.x; if (p.y < minY) minY = p.y
    if (p.x > maxX) maxX = p.x; if (p.y > maxY) maxY = p.y
  }
  const bx1 = Math.max(0, Math.floor(minX)), by1 = Math.max(0, Math.floor(minY))
  const bx2 = Math.min(w, Math.ceil(maxX)), by2 = Math.min(h, Math.ceil(maxY))
  for (let y = by1; y < by2; y++) {
    for (let x = bx1; x < bx2; x++) {
      if (pointInPoly(x, y, points)) maskData[y * w + x] = 0
    }
  }
}

function pointInPoly(x, y, poly) {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y
    const xj = poly[j].x, yj = poly[j].y
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
      inside = !inside
    }
  }
  return inside
}

function emitMaskBounds() {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = w, minY = h, maxX = 0, maxY = 0
  let any = false
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (maskData[y * w + x] > 0) {
        any = true
        if (x < minX) minX = x; if (y < minY) minY = y
        if (x > maxX) maxX = x; if (y > maxY) maxY = y
      }
    }
  }
  if (any) {
    emit('selection-changed', { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 })
  }
  hasMask.value = any
}

function onWheel(e) {
  if (e.shiftKey) {
    rotation.value += e.deltaY > 0 ? 5 : -5
  } else {
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    zoom.value = Math.max(0.1, Math.min(10, zoom.value * delta))
  }
}

function clearSelection() {
  if (maskData) maskData.fill(0)
  hasMask.value = false
  lassoPoints = []
  renderMaskOverlay()
}

function getSelection() {
  if (!maskData || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  let minX = w, minY = h, maxX = 0, maxY = 0
  let any = false
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (maskData[y * w + x] > 0) {
        any = true
        if (x < minX) minX = x; if (y < minY) minY = y
        if (x > maxX) maxX = x; if (y > maxY) maxY = y
      }
    }
  }
  return any ? { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 } : null
}

// 마스크를 base64 PNG로 내보내기 (Python 백엔드 전송용)
function getMaskBase64() {
  if (!maskData || !sourceImg) return null
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const tmpCanvas = document.createElement('canvas')
  tmpCanvas.width = w; tmpCanvas.height = h
  const tmpCtx = tmpCanvas.getContext('2d')
  const imgData = tmpCtx.createImageData(w, h)
  for (let i = 0; i < maskData.length; i++) {
    const v = maskData[i]
    imgData.data[i * 4] = v
    imgData.data[i * 4 + 1] = v
    imgData.data[i * 4 + 2] = v
    imgData.data[i * 4 + 3] = 255
  }
  tmpCtx.putImageData(imgData, 0, 0)
  return tmpCanvas.toDataURL('image/png')
}

defineExpose({ clearSelection, getSelection, getMaskBase64, drawAll })

onMounted(() => {
  if (props.imageSrc) {
    const img = new Image()
    img.onload = () => {
      sourceImg = img
      imgWidth.value = img.naturalWidth
      imgHeight.value = img.naturalHeight
      maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
      drawAll()
    }
    img.src = props.imageSrc
  }
})
</script>

<style scoped>
.canvas-container {
  width: 100%; height: 100%; position: relative;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; background: #111;
}
canvas {
  max-width: 90%; max-height: 90%;
  position: absolute;
}
.mask-overlay {
  pointer-events: none;
}
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px;
  background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px;
  pointer-events: none; z-index: 2;
}
</style>
