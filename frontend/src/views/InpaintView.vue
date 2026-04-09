<template>
  <div class="inpaint-workspace">
    <!-- Left Sidebar: Controls -->
    <aside class="sidebar">
      <div class="sidebar-scroll">
        <!-- Mask Settings -->
        <div class="glass-card">
          <label>Inpaint Masking</label>
          <div class="brush-row">
            <label class="mini">Brush Size</label>
            <input type="range" min="1" max="100" v-model.number="brushSize" class="modern-slider" />
            <span class="val">{{ brushSize }}</span>
          </div>
          <div class="btn-row mt-12">
            <button class="ghost-btn" @click="clearMask">CLEAR MASK</button>
            <button class="ghost-btn" @click="undoMask">UNDO</button>
          </div>
        </div>

        <!-- Inpaint Modes -->
        <div class="glass-card">
          <label>Mask Content</label>
          <div class="chip-grid">
            <button v-for="(m, i) in maskContents" :key="i"
              class="chip-btn" :class="{ active: maskContent === i }"
              @click="maskContent = i"
            >{{ m }}</button>
          </div>
          
          <label class="mt-12">Inpaint Area</label>
          <div class="chip-grid">
            <button v-for="(a, i) in inpaintAreas" :key="i"
              class="chip-btn" :class="{ active: inpaintArea === i }"
              @click="inpaintArea = i"
            >{{ a }}</button>
          </div>
        </div>

        <!-- Prompt & Denoising -->
        <div class="glass-card">
          <label>Denoising Strength</label>
          <div class="premium-slider">
            <input type="range" min="0" max="1" step="0.01" v-model.number="denoising" />
            <div class="slider-display">
              <span class="val">{{ denoising.toFixed(2) }}</span>
            </div>
          </div>
          <textarea v-model="prompt" class="mt-12" rows="3" placeholder="Describe the change..."></textarea>
        </div>
      </div>

      <div class="sidebar-footer">
        <button class="btn-generate primary" @click="generate" :disabled="!imageSrc">
          START INPAINTING
        </button>
      </div>
    </aside>

    <!-- Main Content: Canvas -->
    <section class="canvas-area">
      <div class="canvas-container" :class="{ 'drag-over': isDragging }"
        @dragover.prevent="isDragging = true" @dragleave="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <div v-if="!imageSrc" class="drop-empty" @click="triggerFileInput">
          <div class="icon">✎</div>
          <h2>MASK EDITOR</h2>
          <p>Drop image to start painting</p>
        </div>
        
        <div v-else class="editor-wrap">
          <canvas ref="canvasRef" @mousedown="startDrawing" @mousemove="draw" @mouseup="stopDrawing" @mouseleave="stopDrawing"></canvas>
          <div class="canvas-toolbar">
            <button class="tool-btn" @click="triggerFileInput" title="Change Image">📁</button>
            <div class="sep"></div>
            <div class="brush-preview" :style="{ width: brushSize + 'px', height: brushSize + 'px' }"></div>
          </div>
        </div>
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFileSelect" />
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'

const isDragging = ref(false)
const imageSrc = ref('')
const imagePath = ref('')
const fileInput = ref(null)
const canvasRef = ref(null)
const ctx = ref(null)
const isDrawing = ref(false)
const brushSize = ref(30)

const prompt = ref('')
const denoising = ref(0.75)
const maskContent = ref(0)
const inpaintArea = ref(0)

const maskContents = ['FILL', 'ORIGINAL', 'LATENT NOISE', 'LATENT NOTHING']
const inpaintAreas = ['WHOLE IMAGE', 'ONLY MASKED']

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
  reader.onload = (ev) => {
    imageSrc.value = ev.target.result
    initCanvas(ev.target.result)
  }
  reader.readAsDataURL(file)
  if (file.path) imagePath.value = file.path.replace(/\\/g, '/')
}

async function loadFromPath(path) {
  imagePath.value = path
  const backend = await getBackend()
  if (backend.loadImageBase64) {
    backend.loadImageBase64(path, (b64) => {
      if (b64) { imageSrc.value = b64; initCanvas(b64) }
    })
  }
}

onMounted(() => {
  onBackendEvent('inpaintImageLoaded', (path) => loadFromPath(path))
})

function initCanvas(src) {
  const img = new Image()
  img.onload = () => {
    const canvas = canvasRef.value
    if (!canvas) return
    canvas.width = img.width
    canvas.height = img.height
    ctx.value = canvas.getContext('2d')
    ctx.value.drawImage(img, 0, 0)
    // 마스크 데이터를 위한 투명 레이어 설정 등 필요
  }
  img.src = src
}

function startDrawing(e) {
  isDrawing.value = true
  draw(e)
}
function draw(e) {
  if (!isDrawing.value || !ctx.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const scaleX = canvasRef.value.width / rect.width
  const scaleY = canvasRef.value.height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY

  ctx.value.globalCompositeOperation = 'destination-out' // 예시: 일단 지우기 형태로 마스크 시각화
  ctx.value.beginPath()
  ctx.value.arc(x, y, brushSize.value / 2, 0, Math.PI * 2)
  ctx.value.fill()
}
function stopDrawing() { isDrawing.value = false }
function clearMask() { /* 마스크 초기화 로직 */ }
function undoMask() { /* 실행 취소 */ }

function getMaskBase64() {
  if (!canvasRef.value || !ctx.value) return ''
  // 마스크 캔버스에서 그려진 영역을 흑백 마스크로 변환
  const c = canvasRef.value
  const maskCanvas = document.createElement('canvas')
  maskCanvas.width = c.width; maskCanvas.height = c.height
  const mCtx = maskCanvas.getContext('2d')
  // 캔버스 현재 상태에서 원본 이미지 뺀 차이 = 마스크
  const imgData = ctx.value.getImageData(0, 0, c.width, c.height)
  const maskData = mCtx.createImageData(c.width, c.height)
  for (let i = 0; i < imgData.data.length; i += 4) {
    // alpha가 줄어든 부분(destination-out으로 지운 부분)이 마스크
    const alpha = imgData.data[i + 3]
    const v = alpha < 200 ? 255 : 0  // 투명한 부분 = 마스크 영역
    maskData.data[i] = v; maskData.data[i+1] = v; maskData.data[i+2] = v; maskData.data[i+3] = 255
  }
  mCtx.putImageData(maskData, 0, 0)
  return maskCanvas.toDataURL('image/png')
}

function generate() {
  const mask = getMaskBase64()
  requestAction('generate_inpaint', {
    image: imageSrc.value,
    image_path: imagePath.value,
    mask: mask,
    prompt: prompt.value,
    denoising: denoising.value,
    mask_content: maskContent.value,
    inpaint_area: inpaintArea.value
  })
}
</script>

<style scoped>
.inpaint-workspace { height: 100%; display: flex; background: var(--bg-primary); }

/* Sidebar & Cards (Reuse I2I style) */
.sidebar { width: 340px; display: flex; flex-direction: column; background: var(--bg-secondary); border-right: 1px solid var(--border); }
.sidebar-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.sidebar-footer { padding: 16px; background: var(--bg-card); border-top: 1px solid var(--border); }
.glass-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 14px; }

.brush-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.mini { font-size: 9px; min-width: 60px; }
.val { font-size: 12px; font-weight: 800; color: var(--accent); min-width: 24px; }

.chip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.chip-btn { height: 32px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; transition: var(--transition); }
.chip-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }

.ghost-btn { flex: 1; height: 30px; background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }

/* Canvas Area */
.canvas-area { flex: 1; padding: 24px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.canvas-container { width: 100%; height: 100%; background: #000; border-radius: 20px; position: relative; border: 1px solid var(--border); overflow: hidden; }
.editor-wrap { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; position: relative; }
canvas { max-width: 100%; max-height: 100%; object-fit: contain; cursor: crosshair; }

.canvas-toolbar {
  position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
  background: rgba(20,20,20,0.8); backdrop-filter: blur(10px); padding: 8px 16px;
  border-radius: var(--radius-pill); border: 1px solid var(--border);
  display: flex; align-items: center; gap: 16px;
}
.tool-btn { background: transparent; border: none; font-size: 18px; cursor: pointer; }
.brush-preview { border-radius: 50%; border: 1px solid var(--accent); background: var(--accent-dim); pointer-events: none; }

.drop-empty { text-align: center; cursor: pointer; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.drop-empty h2 { letter-spacing: 4px; color: var(--text-secondary); margin: 16px 0 8px; }

.btn-generate.primary { width: 100%; height: 46px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 12px; letter-spacing: 1px; cursor: pointer; }
</style>
