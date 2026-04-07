<template>
  <div class="editor-view" @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @drop.prevent="onDrop">
    <template v-if="imagePath">
      <!-- 상단 도구바 -->
      <div class="toolbar">
        <div class="tool-group">
          <button class="t-btn" @click="doOp('rotate_cw')">↻ 회전</button>
          <button class="t-btn" @click="doOp('rotate_ccw')">↺ 반회전</button>
          <button class="t-btn" @click="doOp('flip_h')">⇔ 좌우반전</button>
          <button class="t-btn" @click="doOp('flip_v')">⇕ 상하반전</button>
        </div>
        <div class="tool-group">
          <button class="t-btn" @click="doOp('mosaic', { strength: mosaicStrength })">🔲 모자이크</button>
          <input type="range" min="5" max="50" v-model.number="mosaicStrength" class="sm-slider" title="모자이크 강도" />
          <span class="val">{{ mosaicStrength }}</span>
        </div>
        <div class="tool-group">
          <button class="t-btn" @click="doOp('blur', { strength: blurStrength })">💧 블러</button>
          <input type="range" min="3" max="51" step="2" v-model.number="blurStrength" class="sm-slider" title="블러 강도" />
          <span class="val">{{ blurStrength }}</span>
        </div>
        <div class="tool-group">
          <button class="t-btn" @click="doOp('grayscale')">⬛ 흑백</button>
          <button class="t-btn" @click="doOp('sepia')">🟤 세피아</button>
          <button class="t-btn" @click="doOp('sharpen')">🔪 샤프닝</button>
        </div>
        <div class="tool-group">
          <button class="t-btn" @click="doOp('brightness', { value: brightnessVal })">☀️ 밝기</button>
          <input type="range" min="-100" max="100" v-model.number="brightnessVal" class="sm-slider" />
          <span class="val">{{ brightnessVal }}</span>
        </div>
        <div class="tool-group">
          <button class="t-btn" @click="doOp('contrast', { value: contrastVal })">🎛 대비</button>
          <input type="range" min="50" max="200" v-model.number="contrastVal" class="sm-slider" />
          <span class="val">{{ (contrastVal / 100).toFixed(1) }}</span>
        </div>
        <div class="spacer" />
        <button class="t-btn" @click="undo" :disabled="historyIdx <= 0">↩ Undo</button>
        <button class="t-btn" @click="redo" :disabled="historyIdx >= history.length - 1">↪ Redo</button>
        <button class="t-btn save" @click="saveImage">💾 저장</button>
        <button class="t-btn" @click="resetEditor">✕ 닫기</button>
      </div>

      <!-- 이미지 표시 -->
      <div class="canvas-area">
        <img :src="imageDisplay" class="edit-image" />
        <div class="img-info">{{ imgWidth }} × {{ imgHeight }}</div>
      </div>
    </template>

    <!-- 이미지 없을 때 -->
    <template v-else>
      <div class="drop-area" :class="{ dragging: isDragging }">
        <div class="drop-icon">🎨</div>
        <h2>Image Editor</h2>
        <p>이미지를 드래그앤드롭하거나 파일을 선택하세요</p>
        <button class="open-btn" @click="openFile">파일 선택</button>
        <div class="feature-list">
          <span>회전</span><span>반전</span><span>모자이크</span><span>블러</span>
          <span>흑백</span><span>세피아</span><span>샤프닝</span><span>밝기/대비</span>
          <span>Undo/Redo</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'

const isDragging = ref(false)
const imagePath = ref('')
const imageDisplay = ref('')
const imgWidth = ref(0)
const imgHeight = ref(0)
const mosaicStrength = ref(20)
const blurStrength = ref(15)
const brightnessVal = ref(0)
const contrastVal = ref(100)

// Undo/Redo
const history = ref([])
const historyIdx = ref(-1)

function pushHistory(path) {
  // 현재 위치 이후 히스토리 제거
  history.value = history.value.slice(0, historyIdx.value + 1)
  history.value.push(path)
  historyIdx.value = history.value.length - 1
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
}

function undo() {
  if (historyIdx.value > 0) {
    historyIdx.value--
    const p = history.value[historyIdx.value]
    imagePath.value = p
    imageDisplay.value = 'file:///' + p + '?t=' + Date.now()
  }
}

function redo() {
  if (historyIdx.value < history.value.length - 1) {
    historyIdx.value++
    const p = history.value[historyIdx.value]
    imagePath.value = p
    imageDisplay.value = 'file:///' + p + '?t=' + Date.now()
  }
}

async function doOp(operation, params = {}) {
  const backend = await getBackend()
  if (!backend.editorProcess) return
  backend.editorProcess(imagePath.value, operation, JSON.stringify(params), (json) => {
    try {
      const result = JSON.parse(json)
      if (result.path) {
        pushHistory(result.path)
        imgWidth.value = result.width
        imgHeight.value = result.height
      } else if (result.error) {
        console.error('Editor error:', result.error)
      }
    } catch {}
  })
}

function loadImage(path) {
  history.value = [path]
  historyIdx.value = 0
  imagePath.value = path
  imageDisplay.value = 'file:///' + path
  // 크기 확인
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = 'file:///' + path
}

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file?.path) loadImage(file.path.replace(/\\/g, '/'))
}

function openFile() { requestAction('editor_open_file') }
function saveImage() { requestAction('editor_save', { path: imagePath.value }) }
function resetEditor() {
  imagePath.value = ''
  imageDisplay.value = ''
  history.value = []
  historyIdx.value = -1
}

onMounted(() => {
  onBackendEvent('editorImageLoaded', (path) => loadImage(path))
})
</script>

<style scoped>
.editor-view { width: 100%; height: 100%; display: flex; flex-direction: column; }

.toolbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px;
  padding: 6px 8px; background: #0D0D0D; flex-shrink: 0;
}
.tool-group { display: flex; align-items: center; gap: 3px; }
.t-btn {
  padding: 5px 10px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer; white-space: nowrap;
}
.t-btn:hover { background: #222; color: #E8E8E8; }
.t-btn:disabled { opacity: 0.3; }
.t-btn.save { background: #E2B340; color: #000; }
.t-btn.save:hover { background: #F0C850; }
.sm-slider { width: 60px; accent-color: #E2B340; }
.val { color: #585858; font-size: 10px; min-width: 24px; }
.spacer { flex: 1; }

.canvas-area {
  flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; padding: 8px; position: relative;
}
.edit-image { max-width: 100%; max-height: 100%; object-fit: contain; }
.img-info {
  position: absolute; bottom: 12px; right: 16px;
  color: #484848; font-size: 11px; background: rgba(0,0,0,0.5);
  padding: 2px 8px; border-radius: 4px;
}

.drop-area {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px; cursor: pointer;
}
.drop-area.dragging { background: #111; }
.drop-icon { font-size: 48px; opacity: 0.3; }
.drop-area h2 { color: #787878; font-size: 20px; }
.drop-area p { color: #484848; font-size: 13px; }
.open-btn {
  padding: 10px 24px; background: #E2B340; border: none; border-radius: 8px;
  color: #000; font-weight: 700; font-size: 14px; cursor: pointer;
}
.open-btn:hover { background: #F0C850; }
.feature-list {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; justify-content: center;
}
.feature-list span {
  padding: 5px 12px; background: #131313; border-radius: 6px;
  color: #585858; font-size: 11px;
}
</style>
