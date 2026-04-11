<template>
  <div class="inpaint-workspace">
    <!-- Left Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <div class="glass-card">
          <label>Source Image</label>
          <div class="source-thumb" @click="triggerFileInput">
            <img v-if="imageSrc" :src="imageSrc" />
            <div v-else class="upload-hint">DROP OR CLICK</div>
          </div>
        </div>

        <div class="glass-card">
          <label>Brush Size</label>
          <div class="brush-row">
            <input type="range" min="5" max="200" v-model.number="brushSize" />
            <span class="brush-val">{{ brushSize }}px</span>
          </div>
        </div>

        <div class="glass-card">
          <label>Denoising Strength</label>
          <div class="brush-row">
            <input type="range" min="0" max="1" step="0.01" v-model.number="denoising" />
            <span class="brush-val">{{ denoising.toFixed(2) }}</span>
          </div>
        </div>

        <div class="glass-card">
          <label>Override Prompt</label>
          <textarea v-model="prompt" rows="3" placeholder="Describe the change..."></textarea>
        </div>

        <div class="glass-card">
          <label>Mask Settings</label>
          <div class="mask-opts">
            <select v-model="maskContent">
              <option v-for="(mc, i) in maskContents" :key="i" :value="i">{{ mc }}</option>
            </select>
            <select v-model="inpaintArea">
              <option v-for="(ia, i) in inpaintAreas" :key="i" :value="i">{{ ia }}</option>
            </select>
          </div>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="mask-actions">
          <button class="action-btn" @click="clearMask">CLEAR MASK</button>
          <button class="action-btn" @click="undoMask">UNDO</button>
        </div>
        <button class="btn-generate" @click="generate" :disabled="!imageSrc">
          START INPAINTING
        </button>
      </div>
    </aside>

    <!-- Canvas Area -->
    <section class="canvas-area">
      <div class="canvas-container" :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true" @dragleave="isDragging = false"
        @drop.prevent="handleDrop" @click="!imageSrc && triggerFileInput()"
      >
        <div v-if="!imageSrc" class="drop-empty">
          <div class="icon">✎</div>
          <h2>MASK EDITOR</h2>
          <p>Drop image or click to start</p>
        </div>

        <template v-else>
          <!-- 이미지 캔버스 -->
          <canvas ref="imgCanvasRef" class="paint-canvas" :style="canvasTransform"></canvas>
          <!-- 마스크 오버레이 캔버스 -->
          <canvas ref="maskCanvasRef" class="paint-canvas mask-layer" :style="canvasTransform"
            @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
            @mouseleave="onMouseUp" @wheel.prevent="onWheel" @contextmenu.prevent
          ></canvas>
          <div class="canvas-info">
            {{ imgW }} × {{ imgH }} | {{ Math.round(zoom * 100) }}%
            <template v-if="hasMask"> | MASK</template>
          </div>
        </template>
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileSelect" />
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'

const isDragging = ref(false)
const imageSrc = ref('')
const imagePath = ref('')
const fileInput = ref(null)
const imgCanvasRef = ref(null)
const maskCanvasRef = ref(null)
const brushSize = ref(40)
const prompt = ref('')
const denoising = ref(0.75)
const maskContent = ref(0)
const inpaintArea = ref(0)
const maskContents = ['FILL', 'ORIGINAL', 'LATENT NOISE', 'LATENT NOTHING']
const inpaintAreas = ['WHOLE IMAGE', 'ONLY MASKED']

const imgW = ref(0)
const imgH = ref(0)
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const hasMask = ref(false)

let imgCtx = null
let maskCtx = null
let sourceImg = null
let maskData = null  // Uint8Array
let drawing = false
let panning = false
let lastX = -1, lastY = -1
let panStartX = 0, panStartY = 0
let maskUndoStack = []

const canvasTransform = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
  cursor: panning ? 'grabbing' : 'none',
}))

// ── 이미지 로드 ──
function triggerFileInput() { fileInput.value?.click() }
function handleFileSelect(e) { const f = e.target.files?.[0]; if (f) loadFile(f) }
function handleDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) { imagePath.value = f.path || ''; loadFile(f); return }
  const path = e.dataTransfer?.getData('text/plain')
  if (path && path.includes('/')) loadFromPath(path)
}

function loadFile(file) {
  const reader = new FileReader()
  reader.onload = (ev) => { imageSrc.value = ev.target.result; initCanvas(ev.target.result) }
  reader.readAsDataURL(file)
  if (file.path) imagePath.value = file.path.replace(/\\/g, '/')
}

async function loadFromPath(path) {
  imagePath.value = path
  const backend = await getBackend()
  if (backend.loadImageBase64) {
    backend.loadImageBase64(path, (b64) => { if (b64) { imageSrc.value = b64; initCanvas(b64) } })
  }
}

function initCanvas(src) {
  const img = new Image()
  img.onload = () => {
    sourceImg = img
    imgW.value = img.naturalWidth; imgH.value = img.naturalHeight
    zoom.value = 1; panX.value = 0; panY.value = 0

    // 이미지 캔버스
    const ic = imgCanvasRef.value; if (!ic) return
    ic.width = img.naturalWidth; ic.height = img.naturalHeight
    imgCtx = ic.getContext('2d')
    imgCtx.drawImage(img, 0, 0)

    // 마스크 캔버스
    const mc = maskCanvasRef.value; if (!mc) return
    mc.width = img.naturalWidth; mc.height = img.naturalHeight
    maskCtx = mc.getContext('2d')
    maskCtx.clearRect(0, 0, mc.width, mc.height)

    // 마스크 데이터 초기화
    maskData = new Uint8Array(img.naturalWidth * img.naturalHeight)
    hasMask.value = false
    maskUndoStack = []
  }
  img.src = src
}

// ── 좌표 변환 ──
function getPos(e) {
  if (!maskCanvasRef.value) return { x: 0, y: 0 }
  const rect = maskCanvasRef.value.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) / rect.width * maskCanvasRef.value.width,
    y: (e.clientY - rect.top) / rect.height * maskCanvasRef.value.height,
  }
}

// ── 마우스 이벤트 ──
function onMouseDown(e) {
  if (e.altKey || e.button === 1) {
    panning = true; panStartX = e.clientX - panX.value; panStartY = e.clientY - panY.value; return
  }
  // undo 저장
  if (maskData) maskUndoStack.push(new Uint8Array(maskData))
  if (maskUndoStack.length > 10) maskUndoStack.shift()

  drawing = true
  const pos = getPos(e)
  lastX = pos.x; lastY = pos.y
  paintCircle(pos.x, pos.y)
  renderMask()
}

function onMouseMove(e) {
  if (panning) { panX.value = e.clientX - panStartX; panY.value = e.clientY - panStartY; return }
  // 커서 그리기 (큰 브러시)
  if (maskCtx && !drawing) {
    renderMask()
    const pos = getPos(e)
    const r = brushSize.value
    maskCtx.strokeStyle = 'rgba(226, 179, 64, 0.6)'
    maskCtx.lineWidth = 2
    maskCtx.beginPath(); maskCtx.arc(pos.x, pos.y, r, 0, Math.PI * 2); maskCtx.stroke()
  }
  if (!drawing) return
  const pos = getPos(e)
  paintLine(lastX, lastY, pos.x, pos.y)
  lastX = pos.x; lastY = pos.y
  renderMask()
}

function onMouseUp() {
  if (panning) { panning = false; return }
  drawing = false
}

function onWheel(e) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  zoom.value = Math.max(0.2, Math.min(5, zoom.value * delta))
}

// ── 마스크 페인트 ──
function paintCircle(cx, cy) {
  if (!maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const r = brushSize.value
  for (let y = Math.max(0, Math.floor(cy - r)); y < Math.min(h, Math.ceil(cy + r)); y++) {
    for (let x = Math.max(0, Math.floor(cx - r)); x < Math.min(w, Math.ceil(cx + r)); x++) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r ** 2) maskData[y * w + x] = 255
    }
  }
  hasMask.value = true
}

function paintLine(x0, y0, x1, y1) {
  const dist = Math.hypot(x1 - x0, y1 - y0)
  const steps = Math.max(1, Math.ceil(dist / Math.max(1, brushSize.value * 0.3)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    paintCircle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
  }
}

function renderMask() {
  if (!maskCtx || !maskData || !sourceImg) return
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  maskCtx.clearRect(0, 0, w, h)
  const id = maskCtx.createImageData(w, h)
  for (let i = 0; i < maskData.length; i++) {
    if (maskData[i] > 0) {
      id.data[i * 4] = 226; id.data[i * 4 + 1] = 179
      id.data[i * 4 + 2] = 64; id.data[i * 4 + 3] = 100
    }
  }
  maskCtx.putImageData(id, 0, 0)
}

function clearMask() {
  if (maskData) { maskUndoStack.push(new Uint8Array(maskData)); maskData.fill(0) }
  hasMask.value = false
  renderMask()
}

function undoMask() {
  if (maskUndoStack.length === 0 || !maskData) return
  maskData.set(maskUndoStack.pop())
  hasMask.value = maskData.some(v => v > 0)
  renderMask()
}

// ── 생성 ──
function getMaskBase64() {
  if (!maskData || !sourceImg) return ''
  const w = sourceImg.naturalWidth, h = sourceImg.naturalHeight
  const tc = document.createElement('canvas'); tc.width = w; tc.height = h
  const tctx = tc.getContext('2d')
  const id = tctx.createImageData(w, h)
  for (let i = 0; i < maskData.length; i++) {
    const v = maskData[i]
    id.data[i * 4] = v; id.data[i * 4 + 1] = v; id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 255
  }
  tctx.putImageData(id, 0, 0)
  return tc.toDataURL('image/png')
}

function generate() {
  requestAction('generate_inpaint', {
    image: imageSrc.value,
    image_path: imagePath.value,
    mask: getMaskBase64(),
    prompt: prompt.value,
    denoising: denoising.value,
    mask_content: maskContent.value,
    inpaint_area: inpaintArea.value,
  })
}

onMounted(() => {
  onBackendEvent('inpaintImageLoaded', (path) => loadFromPath(path))
})
</script>

<style scoped>
.inpaint-workspace { height: 100%; display: flex; background: var(--bg-primary); }

.sidebar { width: 300px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); }
.sidebar-scroll { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.sidebar-footer { padding: 12px; background: var(--bg-card); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.glass-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 12px; }

.source-thumb { height: 120px; border-radius: 6px; overflow: hidden; cursor: pointer; background: var(--bg-input); display: flex; align-items: center; justify-content: center; }
.source-thumb img { width: 100%; height: 100%; object-fit: contain; }
.upload-hint { color: var(--text-muted); font-size: 11px; font-weight: 700; }

.brush-row { display: flex; align-items: center; gap: 8px; }
.brush-row input[type="range"] { flex: 1; accent-color: var(--accent); }
.brush-val { font-size: 11px; color: var(--accent); min-width: 40px; text-align: right; font-family: monospace; }

.mask-opts { display: flex; flex-direction: column; gap: 6px; }
.mask-actions { display: flex; gap: 4px; }
.action-btn { flex: 1; padding: 6px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }
.btn-generate { width: 100%; height: 44px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 800; font-size: 13px; cursor: pointer; }
.btn-generate:disabled { opacity: 0.4; }

.canvas-area { flex: 1; display: flex; align-items: center; justify-content: center; overflow: hidden; background: #080808; position: relative; }
.canvas-container { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; position: relative; }
.canvas-container.drag-over { background: rgba(250,204,21,0.05); }
.drop-empty { text-align: center; cursor: pointer; }
.drop-empty .icon { font-size: 48px; opacity: 0.3; }
.drop-empty h2 { color: var(--text-muted); letter-spacing: 4px; }
.drop-empty p { color: #484848; font-size: 12px; }

.paint-canvas { position: absolute; max-width: 85%; max-height: 85%; }
.mask-layer { pointer-events: auto; cursor: crosshair; }
.canvas-info {
  position: absolute; bottom: 8px; right: 12px;
  color: #585858; font-size: 11px; background: rgba(0,0,0,0.6);
  padding: 2px 8px; border-radius: 4px; pointer-events: none;
}
</style>
