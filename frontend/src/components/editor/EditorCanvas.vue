<template>
  <div class="canvas-container" ref="containerRef"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
  >
    <canvas ref="canvasEl" :style="canvasStyle" />
    <div class="canvas-info">
      {{ imgWidth }} × {{ imgHeight }}
      <template v-if="hasSelection"> | 선택: {{ selRect.w }}×{{ selRect.h }}</template>
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
})

const emit = defineEmits(['selection-changed', 'mask-changed'])

const containerRef = ref(null)
const canvasEl = ref(null)
const imgWidth = ref(0)
const imgHeight = ref(0)
const zoom = ref(1)
const rotation = ref(0)
const panX = ref(0)
const panY = ref(0)
const hasSelection = ref(false)
const selRect = ref({ x: 0, y: 0, w: 0, h: 0 })

let ctx = null
let sourceImg = null
let drawing = false
let panning = false
let startX = 0, startY = 0
let panStartX = 0, panStartY = 0

const canvasStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value}) rotate(${rotation.value}deg)`,
  transformOrigin: 'center center',
  cursor: panning ? 'grabbing' : (props.tool === 'brush' || props.tool === 'eraser' ? 'crosshair' : 'default'),
}))

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
    drawAll()
  }
  img.src = src
})

function drawAll() {
  if (!canvasEl.value || !sourceImg) return
  const c = canvasEl.value
  c.width = sourceImg.naturalWidth
  c.height = sourceImg.naturalHeight
  ctx = c.getContext('2d')
  ctx.clearRect(0, 0, c.width, c.height)
  ctx.drawImage(sourceImg, 0, 0)

  // 선택 영역 그리기
  if (hasSelection.value) {
    const s = selRect.value
    ctx.strokeStyle = '#E2B340'
    ctx.lineWidth = 2 / zoom.value
    ctx.setLineDash([6 / zoom.value, 4 / zoom.value])
    ctx.strokeRect(s.x, s.y, s.w, s.h)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(226, 179, 64, 0.15)'
    ctx.fillRect(s.x, s.y, s.w, s.h)
  }
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
  // Alt+클릭 → 팬
  if (e.altKey) {
    panning = true
    panStartX = e.clientX - panX.value
    panStartY = e.clientY - panY.value
    return
  }
  const pos = getImagePos(e)
  drawing = true
  startX = pos.x
  startY = pos.y

  if (props.tool === 'brush' || props.tool === 'eraser') {
    drawBrush(pos)
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
    drawAll()
    // 임시 선택 영역
    ctx.strokeStyle = '#E2B340'
    ctx.lineWidth = 2 / zoom.value
    ctx.setLineDash([6 / zoom.value, 4 / zoom.value])
    ctx.strokeRect(startX, startY, pos.x - startX, pos.y - startY)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(226, 179, 64, 0.15)'
    ctx.fillRect(startX, startY, pos.x - startX, pos.y - startY)
  } else if (props.tool === 'brush' || props.tool === 'eraser') {
    drawBrush(pos)
  }
}

function onMouseUp(e) {
  if (panning) { panning = false; return }
  if (!drawing) return
  drawing = false
  const pos = getImagePos(e)

  if (props.tool === 'box') {
    const x1 = Math.min(startX, pos.x)
    const y1 = Math.min(startY, pos.y)
    const w = Math.abs(pos.x - startX)
    const h = Math.abs(pos.y - startY)
    if (w > 3 && h > 3) {
      selRect.value = { x: Math.round(x1), y: Math.round(y1), w: Math.round(w), h: Math.round(h) }
      hasSelection.value = true
      emit('selection-changed', selRect.value)
    }
    drawAll()
  }
}

function drawBrush(pos) {
  if (!ctx) return
  const r = props.brushSize / zoom.value
  if (props.tool === 'eraser') {
    ctx.globalCompositeOperation = 'destination-out'
  }
  ctx.fillStyle = 'rgba(255, 0, 0, 0.4)'
  ctx.beginPath()
  ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
}

function onWheel(e) {
  if (e.shiftKey) {
    // Shift+휠 → 부드러운 회전
    rotation.value += e.deltaY > 0 ? 5 : -5
  } else {
    // Ctrl+휠 또는 기본 휠 → 줌
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    zoom.value = Math.max(0.1, Math.min(10, zoom.value * delta))
  }
}

function clearSelection() {
  hasSelection.value = false
  selRect.value = { x: 0, y: 0, w: 0, h: 0 }
  drawAll()
}

function getSelection() { return hasSelection.value ? selRect.value : null }

defineExpose({ clearSelection, getSelection, drawAll })

onMounted(() => {
  if (props.imageSrc) {
    const img = new Image()
    img.onload = () => {
      sourceImg = img
      imgWidth.value = img.naturalWidth
      imgHeight.value = img.naturalHeight
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
  transition: transform 0.05s ease-out;
}
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px;
  background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px;
  pointer-events: none;
}
</style>
