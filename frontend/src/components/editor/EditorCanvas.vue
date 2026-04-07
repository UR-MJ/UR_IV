<template>
  <div class="canvas-container" ref="containerRef">
    <!-- 원본 이미지 -->
    <canvas ref="mainCanvas" class="main-canvas"
      @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
      @mouseleave="onMouseUp" @wheel.prevent="onWheel"
    />
    <!-- 선택/마스크 오버레이 -->
    <canvas ref="overlayCanvas" class="overlay-canvas"
      @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
    />
    <div class="canvas-info">
      {{ imgWidth }} × {{ imgHeight }}
      <template v-if="hasSelection"> | 선택: {{ selRect.w }}×{{ selRect.h }}</template>
      <template v-if="zoom !== 1"> | {{ Math.round(zoom * 100) }}%</template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'

const props = defineProps({
  imageSrc: { type: String, default: '' },
  tool: { type: String, default: 'box' },     // box, lasso, brush, eraser
  brushSize: { type: Number, default: 20 },
  brushColor: { type: String, default: '#FF0000' },
})

const emit = defineEmits(['selection-changed', 'mask-changed', 'color-picked'])

const containerRef = ref(null)
const mainCanvas = ref(null)
const overlayCanvas = ref(null)
const imgWidth = ref(0)
const imgHeight = ref(0)
const zoom = ref(1)
const hasSelection = ref(false)
const selRect = ref({ x: 0, y: 0, w: 0, h: 0 })

let ctx = null
let overlayCtx = null
let sourceImg = null
let drawing = false
let startX = 0, startY = 0
let maskData = null  // Uint8Array mask

// 이미지 로드
watch(() => props.imageSrc, (src) => {
  if (!src) return
  const img = new Image()
  img.onload = () => {
    sourceImg = img
    imgWidth.value = img.naturalWidth
    imgHeight.value = img.naturalHeight
    resizeCanvases()
    drawImage()
    clearOverlay()
    maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
  }
  img.src = src
})

function resizeCanvases() {
  if (!mainCanvas.value || !sourceImg) return
  const c = mainCanvas.value
  const o = overlayCanvas.value
  c.width = sourceImg.naturalWidth
  c.height = sourceImg.naturalHeight
  o.width = c.width
  o.height = c.height
  ctx = c.getContext('2d')
  overlayCtx = o.getContext('2d')
}

function drawImage() {
  if (!ctx || !sourceImg) return
  ctx.clearRect(0, 0, mainCanvas.value.width, mainCanvas.value.height)
  ctx.drawImage(sourceImg, 0, 0)
}

function clearOverlay() {
  if (!overlayCtx) return
  overlayCtx.clearRect(0, 0, overlayCanvas.value.width, overlayCanvas.value.height)
  hasSelection.value = false
}

function getCanvasPos(e) {
  const rect = overlayCanvas.value.getBoundingClientRect()
  const sx = overlayCanvas.value.width / rect.width
  const sy = overlayCanvas.value.height / rect.height
  return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy }
}

function onMouseDown(e) {
  const pos = getCanvasPos(e)
  drawing = true
  startX = pos.x
  startY = pos.y

  if (props.tool === 'brush' || props.tool === 'eraser') {
    drawBrushStroke(pos)
  }
}

function onMouseMove(e) {
  if (!drawing) return
  const pos = getCanvasPos(e)

  if (props.tool === 'box') {
    // 사각형 선택 프리뷰
    clearOverlay()
    const w = pos.x - startX
    const h = pos.y - startY
    overlayCtx.strokeStyle = '#E2B340'
    overlayCtx.lineWidth = 2
    overlayCtx.setLineDash([5, 5])
    overlayCtx.strokeRect(startX, startY, w, h)
    overlayCtx.setLineDash([])
    // 반투명 채움
    overlayCtx.fillStyle = 'rgba(226, 179, 64, 0.1)'
    overlayCtx.fillRect(startX, startY, w, h)
  } else if (props.tool === 'brush' || props.tool === 'eraser') {
    drawBrushStroke(pos)
  }
}

function onMouseUp(e) {
  if (!drawing) return
  drawing = false
  const pos = getCanvasPos(e)

  if (props.tool === 'box') {
    const x1 = Math.min(startX, pos.x)
    const y1 = Math.min(startY, pos.y)
    const x2 = Math.max(startX, pos.x)
    const y2 = Math.max(startY, pos.y)
    selRect.value = { x: Math.round(x1), y: Math.round(y1), w: Math.round(x2 - x1), h: Math.round(y2 - y1) }
    hasSelection.value = selRect.value.w > 5 && selRect.value.h > 5
    if (hasSelection.value) {
      emit('selection-changed', selRect.value)
      // 마스크에 선택 영역 기록
      fillMaskRect(x1, y1, x2, y2)
    }
  }
}

function drawBrushStroke(pos) {
  if (!overlayCtx) return
  const r = props.brushSize
  if (props.tool === 'eraser') {
    overlayCtx.globalCompositeOperation = 'destination-out'
    overlayCtx.beginPath()
    overlayCtx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
    overlayCtx.fill()
    overlayCtx.globalCompositeOperation = 'source-over'
    // 마스크에서 제거
    fillMaskCircle(pos.x, pos.y, r, 0)
  } else {
    overlayCtx.fillStyle = 'rgba(255, 0, 0, 0.4)'
    overlayCtx.beginPath()
    overlayCtx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
    overlayCtx.fill()
    // 마스크에 추가
    fillMaskCircle(pos.x, pos.y, r, 255)
  }
  emit('mask-changed', getMaskBase64())
}

function fillMaskRect(x1, y1, x2, y2) {
  if (!maskData) return
  for (let y = Math.max(0, Math.floor(y1)); y < Math.min(imgHeight.value, Math.ceil(y2)); y++) {
    for (let x = Math.max(0, Math.floor(x1)); x < Math.min(imgWidth.value, Math.ceil(x2)); x++) {
      maskData[y * imgWidth.value + x] = 255
    }
  }
}

function fillMaskCircle(cx, cy, r, val) {
  if (!maskData) return
  for (let y = Math.max(0, Math.floor(cy - r)); y < Math.min(imgHeight.value, Math.ceil(cy + r)); y++) {
    for (let x = Math.max(0, Math.floor(cx - r)); x < Math.min(imgWidth.value, Math.ceil(cx + r)); x++) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r ** 2) {
        maskData[y * imgWidth.value + x] = val
      }
    }
  }
}

function getMaskBase64() {
  if (!maskData || !imgWidth.value) return ''
  const c = document.createElement('canvas')
  c.width = imgWidth.value
  c.height = imgHeight.value
  const cx = c.getContext('2d')
  const imgData = cx.createImageData(imgWidth.value, imgHeight.value)
  for (let i = 0; i < maskData.length; i++) {
    imgData.data[i * 4] = imgData.data[i * 4 + 1] = imgData.data[i * 4 + 2] = maskData[i]
    imgData.data[i * 4 + 3] = 255
  }
  cx.putImageData(imgData, 0, 0)
  return c.toDataURL('image/png')
}

function onWheel(e) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  zoom.value = Math.max(0.1, Math.min(5, zoom.value * delta))
  if (containerRef.value) {
    mainCanvas.value.style.transform = `scale(${zoom.value})`
    overlayCanvas.value.style.transform = `scale(${zoom.value})`
  }
}

// 외부 API
function clearSelection() { clearOverlay(); hasSelection.value = false; maskData?.fill(0) }
function getSelection() { return hasSelection.value ? selRect.value : null }

defineExpose({ clearSelection, getSelection, getMaskBase64, clearOverlay })

onMounted(() => {
  if (props.imageSrc) {
    const img = new Image()
    img.onload = () => {
      sourceImg = img
      imgWidth.value = img.naturalWidth
      imgHeight.value = img.naturalHeight
      resizeCanvases()
      drawImage()
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
.main-canvas, .overlay-canvas {
  max-width: 100%; max-height: 100%; object-fit: contain;
  transform-origin: center center;
}
.overlay-canvas {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: auto; cursor: crosshair;
}
.main-canvas {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px;
  background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px;
}
</style>
