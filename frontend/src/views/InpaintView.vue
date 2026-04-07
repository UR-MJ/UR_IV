<template>
  <div class="inpaint-view">
    <!-- 좌측: 캔버스 -->
    <div class="canvas-area">
      <div class="canvas-toolbar">
        <button :class="{ active: tool === 'brush' }" @click="tool = 'brush'">브러시</button>
        <button :class="{ active: tool === 'eraser' }" @click="tool = 'eraser'">지우개</button>
        <button @click="clearMask">초기화</button>
        <label class="brush-size">
          크기 <input type="range" min="5" max="100" v-model.number="brushSize" />
          <span>{{ brushSize }}</span>
        </label>
      </div>
      <div class="canvas-wrap"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <canvas ref="canvasRef"
          @mousedown="startDraw"
          @mousemove="draw"
          @mouseup="stopDraw"
          @mouseleave="stopDraw"
        />
        <div v-if="!hasImage" class="canvas-hint" @click="openFile" @dblclick="openFile">
          이미지를 드래그하거나 더블클릭하여 선택
        </div>
      </div>
    </div>
    <!-- 우측: 설정 -->
    <div class="settings-panel">
      <h3>Inpaint 설정</h3>
      <label class="s-label">Denoising</label>
      <div class="slider-row">
        <input type="range" min="0" max="1" step="0.01" v-model.number="denoising" />
        <span>{{ denoising.toFixed(2) }}</span>
      </div>
      <label class="s-label">Mask Blur</label>
      <div class="slider-row">
        <input type="range" min="0" max="64" step="1" v-model.number="maskBlur" />
        <span>{{ maskBlur }}</span>
      </div>
      <label class="s-label">Fill Mode</label>
      <select v-model="fillMode" class="s-select">
        <option value="0">fill</option>
        <option value="1">original</option>
        <option value="2">latent noise</option>
        <option value="3">latent nothing</option>
      </select>
      <button class="btn-generate" @click="generate" :disabled="!hasImage">
        Inpaint 생성
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { onBackendEvent } from '../bridge.js'

const canvasRef = ref(null)
const tool = ref('brush')
const brushSize = ref(30)
const denoising = ref(0.75)
const maskBlur = ref(4)
const fillMode = ref('1')
const hasImage = ref(false)
const drawing = ref(false)
let ctx = null
let maskCtx = null
let maskCanvas = null
let sourceImg = null

onMounted(() => {
  const c = canvasRef.value
  if (c) {
    c.width = 512; c.height = 512
    ctx = c.getContext('2d')
    ctx.fillStyle = '#1A1A1A'
    ctx.fillRect(0, 0, c.width, c.height)
    maskCanvas = document.createElement('canvas')
    maskCanvas.width = c.width; maskCanvas.height = c.height
    maskCtx = maskCanvas.getContext('2d')
  }
  // 외부에서 이미지 전달 수신 (Gallery/PNGInfo에서)
  onBackendEvent('inpaintImageLoaded', (path) => {
    loadImage('file:///' + path)
  })
})

function loadImage(src) {
  const img = new Image()
  img.onload = () => {
    sourceImg = img
    const c = canvasRef.value
    c.width = img.width; c.height = img.height
    maskCanvas.width = img.width; maskCanvas.height = img.height
    redraw()
    hasImage.value = true
  }
  img.src = src
}

function redraw() {
  if (!ctx || !sourceImg) return
  ctx.drawImage(sourceImg, 0, 0)
  // 마스크 오버레이 (빨간 반투명)
  ctx.save()
  ctx.globalAlpha = 0.4
  ctx.drawImage(maskCanvas, 0, 0)
  ctx.restore()
}

function startDraw(e) { drawing.value = true; drawAt(e) }
function stopDraw() { drawing.value = false }
function draw(e) { if (drawing.value) drawAt(e) }

function drawAt(e) {
  if (!maskCtx || !hasImage.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const sx = canvasRef.value.width / rect.width
  const sy = canvasRef.value.height / rect.height
  const x = (e.clientX - rect.left) * sx
  const y = (e.clientY - rect.top) * sy
  maskCtx.beginPath()
  maskCtx.arc(x, y, brushSize.value * sx, 0, Math.PI * 2)
  if (tool.value === 'eraser') {
    maskCtx.globalCompositeOperation = 'destination-out'
    maskCtx.fill()
    maskCtx.globalCompositeOperation = 'source-over'
  } else {
    maskCtx.fillStyle = 'rgba(255, 0, 0, 1)'
    maskCtx.fill()
  }
  redraw()
}

function clearMask() {
  if (maskCtx) {
    maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height)
    redraw()
  }
}

function onDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (ev) => loadImage(ev.target.result)
    reader.readAsDataURL(file)
  }
}

function openFile() {
  requestAction('open_png_info_file')
}

function generate() {
  // 마스크를 흑백으로 변환 → base64
  const bwCanvas = document.createElement('canvas')
  bwCanvas.width = maskCanvas.width; bwCanvas.height = maskCanvas.height
  const bwCtx = bwCanvas.getContext('2d')
  const imgData = maskCtx.getImageData(0, 0, maskCanvas.width, maskCanvas.height)
  for (let i = 0; i < imgData.data.length; i += 4) {
    const hasMask = imgData.data[i + 3] > 0
    imgData.data[i] = imgData.data[i + 1] = imgData.data[i + 2] = hasMask ? 255 : 0
    imgData.data[i + 3] = 255
  }
  bwCtx.putImageData(imgData, 0, 0)
  const maskBase64 = bwCanvas.toDataURL('image/png')
  const srcBase64 = (() => {
    const c = document.createElement('canvas')
    c.width = sourceImg.width; c.height = sourceImg.height
    c.getContext('2d').drawImage(sourceImg, 0, 0)
    return c.toDataURL('image/png')
  })()
  requestAction('generate_inpaint', {
    image: srcBase64, mask: maskBase64,
    denoising: denoising.value, mask_blur: maskBlur.value, fill_mode: parseInt(fillMode.value),
  })
}
</script>

<style scoped>
.inpaint-view { height: 100%; display: flex; }
.canvas-area { flex: 1; display: flex; flex-direction: column; }
.canvas-toolbar {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-bottom: 1px solid #1A1A1A;
}
.canvas-toolbar button {
  padding: 6px 12px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.canvas-toolbar button.active { background: #E2B340; color: #000; }
.brush-size { color: #787878; font-size: 12px; display: flex; align-items: center; gap: 6px; margin-left: auto; }
.brush-size input { accent-color: #E2B340; width: 100px; }
.canvas-wrap {
  flex: 1; display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
}
canvas { max-width: 100%; max-height: 100%; cursor: crosshair; }
.canvas-hint {
  position: absolute; color: #484848; font-size: 14px; cursor: pointer;
  text-align: center; user-select: none;
}
.settings-panel {
  width: 260px; padding: 16px; border-left: 1px solid #1A1A1A;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto;
}
.settings-panel h3 { color: #E8E8E8; font-size: 14px; margin: 0 0 8px; }
.s-label { color: #585858; font-size: 11px; font-weight: 600; }
.slider-row { display: flex; align-items: center; gap: 6px; }
.slider-row input { flex: 1; accent-color: #E2B340; }
.slider-row span { color: #787878; font-size: 12px; min-width: 30px; text-align: right; }
.s-select {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; outline: none;
}
.btn-generate {
  padding: 12px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer; margin-top: auto;
}
.btn-generate:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
