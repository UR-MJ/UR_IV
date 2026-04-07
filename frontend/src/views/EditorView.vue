<template>
  <div class="editor-view" @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @drop.prevent="onDrop">
    <template v-if="imagePath">
      <!-- 상단 도구바 -->
      <div class="top-bar">
        <button class="t-btn" @click="openFile">📂 열기</button>
        <button class="t-btn save" @click="saveImage">💾 저장</button>
        <button class="t-btn" @click="doUndo" :disabled="undoStack.length <= 1">↩ Undo</button>
        <button class="t-btn" @click="doRedo" :disabled="redoStack.length === 0">↪ Redo</button>
        <div class="spacer" />
        <span class="info">{{ imgWidth }}×{{ imgHeight }}</span>
        <button class="t-btn" @click="resetEditor">✕ 닫기</button>
      </div>

      <div class="editor-body">
        <!-- 좌측: 서브탭 패널 -->
        <div class="side-panel">
          <div class="tab-buttons">
            <button v-for="(tab, i) in tabs" :key="i"
              class="tab-btn" :class="{ active: activeTab === i }"
              @click="activeTab = i"
            >{{ tab.icon }} {{ tab.label }}</button>
          </div>
          <div class="tab-content">
            <MosaicPanel v-show="activeTab === 0"
              @tool-changed="onToolChanged"
              @apply-effect="applyEffect"
              @cancel-selection="canvasRef?.clearSelection()"
              @crop="doCrop" @resize="doResize"
              @rotate="dir => doOp(dir === 'cw' ? 'rotate_cw' : 'rotate_ccw')"
              @flip="dir => doOp(dir === 'h' ? 'flip_h' : 'flip_v')"
              @perspective="doOp('perspective')"
              @remove-bg="doOp('remove_bg')"
              @auto-detect="p => doOp('auto_detect', p)"
              @auto-censor="p => doOp('auto_censor', p)"
            />
            <ColorPanel v-show="activeTab === 1"
              @adjustment-changed="previewAdj" @apply="applyAdj"
              @reset="resetAdj" @filter-apply="applyFilter"
              @auto-correct="doOp('auto_correct')"
            />
            <AdvancedColorPanel v-show="activeTab === 2"
              @preview="previewAdvAdj" @apply="applyAdvAdj" @reset="resetAdj"
            />
            <WatermarkPanel v-show="activeTab === 3"
              @apply-text="applyTextWm" @apply-image="applyImageWm"
            />
            <DrawPanel v-show="activeTab === 4" ref="drawPanelRef"
              @tool-changed="currentTool = $event"
              @flatten="doOp('flatten')"
            />
            <MovePanel v-show="activeTab === 5"
              @start-move="doOp('start_move')"
              @confirm="doOp('confirm_move')" @cancel="doOp('cancel_move')"
            />
          </div>
        </div>

        <!-- 중앙: 캔버스 -->
        <EditorCanvas ref="canvasRef"
          :image-src="imageDisplay"
          :tool="currentTool"
          :brush-size="20"
          @selection-changed="onSelectionChanged"
        />
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
          <span>모자이크/블러</span><span>색감 조절</span><span>고급 색감</span>
          <span>워터마크</span><span>그리기</span><span>이동/변환</span>
          <span>크롭/리사이즈</span><span>회전/반전</span><span>배경 제거</span>
          <span>Undo/Redo</span><span>단축키</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'
import EditorCanvas from '../components/editor/EditorCanvas.vue'
import MosaicPanel from '../components/editor/MosaicPanel.vue'
import ColorPanel from '../components/editor/ColorPanel.vue'
import AdvancedColorPanel from '../components/editor/AdvancedColorPanel.vue'
import WatermarkPanel from '../components/editor/WatermarkPanel.vue'
import DrawPanel from '../components/editor/DrawPanel.vue'
import MovePanel from '../components/editor/MovePanel.vue'

const isDragging = ref(false)
const imagePath = ref('')
const imageDisplay = ref('')
const imgWidth = ref(0)
const imgHeight = ref(0)
const activeTab = ref(0)
const currentTool = ref('box')
const canvasRef = ref(null)
const drawPanelRef = ref(null)
const selection = ref(null)

const undoStack = ref([])
const redoStack = ref([])

const tabs = [
  { icon: '🔲', label: '모자이크' },
  { icon: '🎨', label: '색감' },
  { icon: '🔧', label: '고급색감' },
  { icon: '💧', label: '워터마크' },
  { icon: '✏️', label: '그리기' },
  { icon: '✂️', label: '이동' },
]

function loadImage(path) {
  undoStack.value = [path]
  redoStack.value = []
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = 'file:///' + path
}

function pushState(path) {
  undoStack.value.push(path)
  redoStack.value = []
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = 'file:///' + path
}

function doUndo() {
  if (undoStack.value.length <= 1) return
  redoStack.value.push(undoStack.value.pop())
  const path = undoStack.value[undoStack.value.length - 1]
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
}

function doRedo() {
  if (redoStack.value.length === 0) return
  const path = redoStack.value.pop()
  undoStack.value.push(path)
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
}

async function doOp(operation, params = {}) {
  const backend = await getBackend()
  if (!backend.editorProcess) return
  backend.editorProcess(imagePath.value, operation, JSON.stringify(params), (json) => {
    try {
      const result = JSON.parse(json)
      if (result.path) pushState(result.path)
    } catch {}
  })
}

function onToolChanged(toolId) {
  const toolMap = { 0: 'box', 1: 'lasso', 2: 'brush', 3: 'eraser' }
  currentTool.value = toolMap[toolId] || 'box'
}

function applyEffect(effectData) {
  const sel = canvasRef.value?.getSelection()
  const effectMap = { 0: 'mosaic', 1: 'censor_bar', 2: 'blur' }
  const op = effectMap[effectData.effect] || 'mosaic'
  doOp(op, { ...effectData, selection: sel })
}
function doCrop() {
  const sel = canvasRef.value?.getSelection()
  if (sel) doOp('crop', { x1: sel.x, y1: sel.y, x2: sel.x + sel.w, y2: sel.y + sel.h })
}
function doResize(params) { doOp('resize', params) }
function previewAdj(adj) { /* live preview via canvas filter */ }
function applyAdj(adj) { doOp('color_adjust', adj) }
function resetAdj() { /* reset preview */ }
function applyFilter(filter) { doOp(filter.name, filter) }
function previewAdvAdj(adj) { /* live preview */ }
function applyAdvAdj(adj) { doOp('adv_color', adj) }
function applyTextWm(params) { doOp('text_watermark', params) }
function applyImageWm(params) { doOp('image_watermark', params) }
function onSelectionChanged(sel) { selection.value = sel }

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
  undoStack.value = []
  redoStack.value = []
}

onMounted(() => {
  onBackendEvent('editorImageLoaded', (path) => loadImage(path))

  // 단축키
  document.addEventListener('keydown', (e) => {
    if (!imagePath.value) return
    if (e.ctrlKey && e.key === 'z') { e.preventDefault(); doUndo() }
    if (e.ctrlKey && e.key === 'y') { e.preventDefault(); doRedo() }
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); saveImage() }
    if (e.key === 'Escape') canvasRef.value?.clearSelection()
  })
})
</script>

<style scoped>
.editor-view { width: 100%; height: 100%; display: flex; flex-direction: column; }

.top-bar {
  display: flex; align-items: center; gap: 4px; padding: 4px 8px;
  background: #0D0D0D; flex-shrink: 0;
}
.t-btn {
  padding: 5px 10px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer; white-space: nowrap;
}
.t-btn:hover { background: #222; color: #E8E8E8; }
.t-btn:disabled { opacity: 0.3; }
.t-btn.save { background: #E2B340; color: #000; }
.spacer { flex: 1; }
.info { color: #484848; font-size: 11px; }

.editor-body { flex: 1; display: flex; overflow: hidden; }

.side-panel {
  width: 280px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
}
.tab-buttons {
  display: flex; flex-wrap: wrap; gap: 2px; padding: 4px;
  background: #0A0A0A; flex-shrink: 0;
}
.tab-btn {
  padding: 5px 8px; background: #131313; border: none; border-radius: 4px;
  color: #585858; font-size: 10px; cursor: pointer; white-space: nowrap;
}
.tab-btn:hover { background: #1A1A1A; color: #E8E8E8; }
.tab-btn.active { background: #1A1A1A; color: #E2B340; }
.tab-content { flex: 1; overflow-y: auto; overflow-x: hidden; }

.drop-area {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
}
.drop-area.dragging { background: #111; }
.drop-icon { font-size: 48px; opacity: 0.3; }
.drop-area h2 { color: #787878; font-size: 20px; }
.drop-area p { color: #484848; font-size: 13px; }
.open-btn {
  padding: 10px 24px; background: #E2B340; border: none; border-radius: 8px;
  color: #000; font-weight: 700; font-size: 14px; cursor: pointer;
}
.feature-list {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; justify-content: center;
}
.feature-list span {
  padding: 5px 12px; background: #131313; border-radius: 6px;
  color: #585858; font-size: 11px;
}
</style>
