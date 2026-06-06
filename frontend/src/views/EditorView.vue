<template>
  <div class="editor-view" @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @drop.prevent="onDrop">
    <template v-if="imagePath">
      <!-- 상단 도구바 -->
      <div class="top-bar">
        <div class="bar-group">
          <button class="bar-btn accent" @click="openFile" title="Ctrl+O">📂 열기</button>
          <button class="bar-btn save" @click="saveImage" title="Ctrl+S">💾 저장</button>
          <button class="bar-btn" @click="saveAsImage" title="Ctrl+Shift+S">💾→ 다른 이름</button>
          <button class="bar-btn" @click="pasteFromClipboard" title="Ctrl+V">📋 붙여넣기</button>
        </div>
        <div class="bar-group center">
          <button class="bar-btn" @click="onUndo" :disabled="undoStack.length <= 1 && !canvasRef?.maskUndoCount" title="Ctrl+Z (마스킹 우선)">
            ↩ Undo <span class="bar-counter">({{ Math.max(0, undoStack.length - 1) }}/{{ MAX_UNDO }})</span>
          </button>
          <button class="bar-btn" @click="onRedo" :disabled="redoStack.length === 0 && !canvasRef?.maskRedoCount" title="Ctrl+Y (마스킹 우선)">
            ↪ Redo <span class="bar-counter">({{ redoStack.length }})</span>
          </button>
          <span class="bar-sep">|</span>
          <span class="bar-filename" :title="imagePath">
            <span v-if="isDirty" class="dirty-mark">●</span>{{ baseName }}
          </span>
          <span class="bar-info">{{ imgWidth }}×{{ imgHeight }}{{ fileInfoExtra }}</span>
          <span v-if="autoSaveAgoText" class="bar-info autosave" :title="`마지막 자동저장: ${new Date(lastAutoSaveAt).toLocaleTimeString()}`">
            💾 {{ autoSaveAgoText }}
          </span>
        </div>
        <div class="bar-group">
          <button class="bar-btn danger" @click="confirmClose">✕ 닫기</button>
        </div>
      </div>

      <div class="editor-body">
        <!-- 좌측: 서브탭 패널 — 너비는 localStorage 영속 -->
        <div class="side-panel" :style="{ width: sidePanelWidth + 'px' }">
          <div class="tab-buttons">
            <button v-for="(tab, i) in tabs" :key="i"
              class="tab-btn" :class="{ active: activeTab === i }"
              @click="activeTab = i"
            >{{ tab.icon }} {{ tab.label }}</button>
          </div>
          <div class="tab-content">
            <MosaicPanel v-show="activeTab === 0"
              :model-label="modelLabel"
              :detect-status="detectStatus"
              @tool-changed="onToolChanged"
              @effect-apply="applyEffect"
              @add-model="openModelDialog"
              @clear-models="clearModels"
              @auto-censor="runAutoCensor"
              @auto-detect="runAutoDetect"
              @cancel-selection="canvasRef?.clearSelection()"
              @crop="doCrop"
              @resize="doResize"
              @perspective="doOp('perspective')"
              @rotate="op => doOp('rotate_' + op)"
              @flip="op => doOp('flip_' + (op === 'horizontal' ? 'h' : 'v'))"
              @remove-bg="params => doOp('remove_bg', params)"
              @params-changed="onParamsChanged"
              @eraser-mode-changed="m => eraserMode = m"
              @eraser-restore-changed="v => eraserRestore = v"
              @magnetic-changed="onMagneticChanged"
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
              @load-watermark-image="loadWatermarkImage"
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
          :brush-size="brushSize"
          :eraser-mode="eraserMode"
          :eraser-restore="eraserRestore"
          :magnetic-lasso="magneticLasso"
          :stamp-spacing="stampSpacing"
          :stamp-shape="stampShape"
          :bar-width="barWidth"
          :bar-height="barHeight"
          @selection-changed="onSelectionChanged"
        />
      </div>
    </template>

    <template v-else>
      <div class="drop-area" :class="{ dragging: isDragging }">
        <div class="drop-icon">🎨</div>
        <h2>Image Editor</h2>
        <p>이미지를 드래그앤드롭하거나 파일을 선택하세요</p>
        <div class="drop-actions">
          <button class="open-btn" @click="openFile">📂 파일 선택</button>
          <button class="open-btn secondary" @click="pasteFromClipboard">📋 클립보드</button>
        </div>
        <div class="drop-shortcuts">
          <kbd>Ctrl+O</kbd> 열기 &nbsp; <kbd>Ctrl+V</kbd> 붙여넣기
        </div>
        <!-- 최근 파일 -->
        <div v-if="recentFiles.length > 0" class="recent-files">
          <div class="recent-label">최근 편집</div>
          <div class="recent-list">
            <button v-for="path in recentFiles" :key="path"
              class="recent-item" :title="path"
              @click="loadImage(path)">
              <span class="recent-name">{{ path.replace(/\\/g, '/').split('/').pop() }}</span>
            </button>
          </div>
        </div>
        <div class="feature-list">
          <span>모자이크/블러</span><span>색감 조절</span><span>고급 색감</span>
          <span>워터마크</span><span>그리기</span><span>이동/변환</span>
          <span>크롭/리사이즈</span><span>회전/반전</span><span>배경 제거</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
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
// 마지막 사용 탭 영속화 (localStorage)
const activeTab = ref(parseInt(window.localStorage.getItem('editorActiveTab') || '0'))
// 파일 정보 (포맷/용량)
const fileSize = ref(0)
const fileFormat = ref('')
// 미저장 변경 추적
const isDirty = ref(false)
const initialImagePath = ref('')
// 사이드 패널 너비 (localStorage 영속, 200~500px)
const sidePanelWidth = ref(parseInt(window.localStorage.getItem('editorSidePanelWidth') || '280'))
watch(sidePanelWidth, (v) => {
  window.localStorage.setItem('editorSidePanelWidth', String(v))
})

// editorSidePanelWidth가 Settings에서 바뀐 경우 동기화
function _syncSidePanelWidthFromStorage() {
  const v = parseInt(window.localStorage.getItem('editorSidePanelWidth') || '280')
  if (v !== sidePanelWidth.value) sidePanelWidth.value = v
}
const currentTool = ref<any>('box')   // 문자열(toolMap) 또는 DrawPanel tool 객체 둘 다 담김(동적)
const brushSize = ref(20)
const eraserMode = ref('brush')
const eraserRestore = ref(false)
const magneticLasso = ref(false)
const stampSpacing = ref(30)
const stampShape = ref('circle')
const barWidth = ref(40)
const barHeight = ref(15)
const canvasRef = ref<any>(null)
const drawPanelRef = ref<any>(null)
const selection = ref<any>(null)
const modelLabel = ref('No Model Loaded')
const detectStatus = ref('')

const undoStack = ref<string[]>([])
const redoStack = ref<string[]>([])

const tabs = [
  { icon: '🔲', label: '모자이크' },
  { icon: '🎨', label: '색감' },
  { icon: '🔧', label: '고급색감' },
  { icon: '💧', label: '워터마크' },
  { icon: '✏️', label: '그리기' },
  { icon: '✂️', label: '이동' },
]

// 파일명 / 확장자 / 정보 표시용 computed
const baseName = computed(() => {
  if (!imagePath.value) return ''
  const p = imagePath.value.replace(/\\/g, '/')
  return p.substring(p.lastIndexOf('/') + 1) || imagePath.value
})
function _formatSize(bytes: number) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}
const fileInfoExtra = computed(() => {
  const parts = []
  if (fileFormat.value) parts.push(fileFormat.value)
  if (fileSize.value) parts.push(_formatSize(fileSize.value))
  return parts.length > 0 ? ' · ' + parts.join(' · ') : ''
})

// 마지막 탭 영속
watch(activeTab, (v) => {
  window.localStorage.setItem('editorActiveTab', String(v))
})

// 최근 파일 관리 (드롭존용)
const recentFiles = ref<string[]>([])
function _loadRecentFiles() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('editorRecentFiles') || '[]')
    if (Array.isArray(saved)) recentFiles.value = saved.slice(0, 6)
  } catch {}
}
function _pushRecentFile(path: string) {
  if (!path) return
  const arr = recentFiles.value.filter(p => p !== path)
  arr.unshift(path)
  recentFiles.value = arr.slice(0, 6)
  window.localStorage.setItem('editorRecentFiles', JSON.stringify(recentFiles.value))
}

function loadImage(path: string) {
  if (!path) return
  undoStack.value = [path]
  redoStack.value = []
  imagePath.value = path
  initialImagePath.value = path
  isDirty.value = false
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
  canvasRef.value?.clearSelection(true)   // 새 이미지: stale 마스크 + undo/redo 스택 초기화
  _pushRecentFile(path)
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = 'file:///' + path
  // 파일 정보 조회 (포맷/용량)
  _loadFileInfo(path)
}

async function _loadFileInfo(path: string) {
  fileFormat.value = ''
  fileSize.value = 0
  try {
    const backend: any = await getBackend()
    if (backend.getFileInfo) {
      backend.getFileInfo(path, (json: string) => {
        try {
          const d = JSON.parse(json)
          if (d.size) fileSize.value = d.size
          if (d.format) fileFormat.value = d.format
        } catch {}
      })
    } else {
      // 폴백: 확장자만 표시
      const m = path.match(/\.([a-zA-Z0-9]+)$/)
      if (m) fileFormat.value = m[1].toUpperCase()
    }
  } catch {}
}

const MAX_UNDO = 30

function pushState(path: string, clearMask = true) {
  undoStack.value.push(path)
  // undo 한도 (MAX_UNDO + 초기 상태 1개)
  while (undoStack.value.length > MAX_UNDO + 1) undoStack.value.shift()
  redoStack.value = []
  imagePath.value = path
  isDirty.value = (path !== initialImagePath.value)
  // 타임스탬프 없이 경로만 변경 → watch에서 zoom/rotation 유지됨
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = 'file:///' + path
  if (clearMask) canvasRef.value?.clearSelection(true)   // 이미지 작업 후: 마스크 히스토리도 리셋
}

function doUndo() {
  if (undoStack.value.length <= 1) return
  redoStack.value.push(undoStack.value.pop() as string)
  const path = undoStack.value[undoStack.value.length - 1]
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
}
function doRedo() {
  if (redoStack.value.length === 0) return
  const path = redoStack.value.pop() as string
  undoStack.value.push(path)
  imagePath.value = path
  imageDisplay.value = 'file:///' + path + '?t=' + Date.now()
}
// 통합 undo/redo — 마스킹이 있으면 마스킹 먼저, 없으면 이미지 작업. (버튼·Ctrl+Z/Y 공용)
function onUndo() { if (canvasRef.value?.undoMask()) return; doUndo() }
function onRedo() { if (canvasRef.value?.redoMask()) return; doRedo() }

async function doOp(operation: string, params: any = {}) {
  if (!imagePath.value) return
  const backend: any = await getBackend()
  const cleanPath = imagePath.value.replace('file:///', '')
  backend.editorProcess(cleanPath, operation, JSON.stringify(params), (json: string) => {
    try {
      const result = JSON.parse(json)
      if (result.path) pushState(result.path)
      else if (result.error) console.error('[Editor] error:', result.error)
    } catch (e) { console.error('[Editor] parse error:', e) }
  })
}

// 마스크 기반 효과 적용 (base64 마스크 전송)
async function doOpWithMask(operation: string, params: any = {}) {
  if (!imagePath.value) return
  const maskB64 = canvasRef.value?.getMaskBase64()
  if (!maskB64) {
    // 마스크 없으면 선택 영역(rect)으로 fallback
    doOp(operation, params)
    return
  }
  const backend: any = await getBackend()
  const cleanPath = imagePath.value.replace('file:///', '')
  const fullParams = { ...params, mask_base64: maskB64 }
  backend.editorProcess(cleanPath, operation, JSON.stringify(fullParams), (json: string) => {
    try {
      const result = JSON.parse(json)
      if (result.path) pushState(result.path)
      else if (result.error) console.error('[Editor] error:', result.error)
    } catch (e) { console.error('[Editor] parse error:', e) }
  })
}

function onToolChanged(data: any) {
  const id = typeof data === 'object' ? data.tool : data
  const toolMap: Record<string, string> = { 0: 'box', 1: 'lasso', 2: 'brush', 3: 'eraser', 4: 'stamp' }
  currentTool.value = toolMap[id] ?? 'box'
  if (typeof data === 'object' && data.size) brushSize.value = data.size
}

// Edge map 캐시 — 같은 이미지에서 magnetic 토글 반복 시 재계산 회피
// 큰 이미지(4K+)에서 Canny가 200~500ms 걸려 누적되면 체감
let _edgeMapCache = { path: '', b64: '' }
async function onMagneticChanged(enabled: boolean) {
  magneticLasso.value = enabled
  if (enabled && imagePath.value) {
    const cleanPath = imagePath.value.replace('file:///', '')
    // 캐시 히트
    if (_edgeMapCache.path === cleanPath && _edgeMapCache.b64) {
      canvasRef.value?.loadEdgeMap(_edgeMapCache.b64)
      return
    }
    // 캐시 미스 — Python에서 생성
    const backend: any = await getBackend()
    if (backend.getEdgeMap) {
      backend.getEdgeMap(cleanPath, 50, 150, (b64: string) => {
        if (b64) {
          _edgeMapCache = { path: cleanPath, b64 }
          canvasRef.value?.loadEdgeMap(b64)
        }
      })
    }
  }
}
// 이미지가 바뀌면 edge cache 무효화
watch(imagePath, () => { _edgeMapCache = { path: '', b64: '' } })

function onParamsChanged(params: any) {
  if (params.toolSize) brushSize.value = params.toolSize
  if (params.stampSpacing) stampSpacing.value = params.stampSpacing
  if (params.stampShape) stampShape.value = params.stampShape
  if (params.barW) barWidth.value = params.barW
  if (params.barH) barHeight.value = params.barH
}

function applyEffect(effectData: any) {
  const sel = canvasRef.value?.getSelection()
  const effectMap: Record<string, string> = { 0: 'mosaic', 1: 'censor_bar', 2: 'blur' }
  const op = effectMap[effectData.effect] ?? 'mosaic'
  if (sel) {
    // 마스크 기반 처리
    doOpWithMask(op, { ...effectData, selection: sel })
  }
}

async function openModelDialog() {
  // 먼저 자동 감지 새로고침
  const backend: any = await getBackend()
  if (backend.refreshYoloModels) {
    backend.refreshYoloModels((label: string) => { if (label) modelLabel.value = label })
  }
  // 새 모델 추가도 가능
  requestAction('editor_add_yolo_model')
}
function clearModels() { requestAction('editor_clear_yolo_models') }

async function runAutoCensor(params: any) {
  if (!imagePath.value) return
  detectStatus.value = '감지 중...'
  const backend: any = await getBackend()
  const cleanPath = imagePath.value.replace('file:///', '')
  const samModel = params?.samModel || 'auto'
  const payload: Record<string, any> = {
    confidence: (params?.confidence || 25) / 100,
    sam_model: samModel,
  }
  // SAM3일 때만 exclude_prompt 전달 (다른 SAM 모델은 텍스트 프롬프트를 받지 않음)
  if (samModel === 'sam3' && params?.excludePrompt && String(params.excludePrompt).trim()) {
    payload.exclude_prompt = String(params.excludePrompt).trim()
  }
  backend.editorProcess(cleanPath, 'auto_censor', JSON.stringify(payload), (json: string) => {
    try {
      const result = JSON.parse(json)
      if (result.path) { pushState(result.path); detectStatus.value = '완료' }
      else { detectStatus.value = result.error || '실패' }
    } catch { detectStatus.value = '오류' }
  })
}

async function runAutoDetect(params: any) {
  if (!imagePath.value) return
  detectStatus.value = '감지 중...'
  const backend: any = await getBackend()
  const cleanPath = imagePath.value.replace('file:///', '')
  const samModel = params?.samModel || 'auto'
  const payload: Record<string, any> = {
    confidence: (params?.confidence || 25) / 100,
    sam_model: samModel,
  }
  if (samModel === 'sam3' && params?.excludePrompt && String(params.excludePrompt).trim()) {
    payload.exclude_prompt = String(params.excludePrompt).trim()
  }
  backend.editorProcess(cleanPath, 'auto_detect', JSON.stringify(payload), (json: string) => {
    try {
      const result = JSON.parse(json)
      if (result.mask_base64) {
        // 마스크를 캔버스에 로드
        canvasRef.value?.loadMaskFromBase64(result.mask_base64)
        detectStatus.value = `${result.detect_count || 0}개 감지됨`
      } else if (result.error) {
        detectStatus.value = result.error
      }
    } catch { detectStatus.value = '오류' }
  })
}

function doCrop() {
  const sel = canvasRef.value?.getSelection()
  if (sel) doOp('crop', { selection: sel })
}
function doResize(params?: any) { doOp('resize', params) }
function applyAdj(adj: any) { doOp('color_adjust', adj) }
// previewAdj / previewAdvAdj — 미구현 빈 함수였음. 실시간 프리뷰는 향후 구현 예정 (TODO).
// resetAdj — ColorPanel 내부에서 자체 reset만 수행하면 됨 (백엔드 호출 불필요).
function previewAdj(_adj: any) { /* TODO: 실시간 색감 프리뷰 (마스크 영역만 임시 렌더) */ }
function resetAdj() { /* ColorPanel이 자체적으로 처리 — 백엔드 액션 없음 */ }
function previewAdvAdj(_adj: any) { /* TODO: Advanced 색감 실시간 프리뷰 */ }
function applyFilter(filter: any) { doOp(filter.name || filter.type, filter) }
function applyAdvAdj(adj: any) { doOp('adv_color', adj) }
function applyTextWm(params: any) { doOp('text_watermark', params) }
function applyImageWm(params: any) { doOp('image_watermark', params) }
function loadWatermarkImage() { requestAction('editor_load_watermark_image') }
function onSelectionChanged(sel: any) { selection.value = sel }

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && (file as any).path) loadImage((file as any).path.replace(/\\/g, '/'))
}

function openFile() { requestAction('editor_open_file') }
function saveImage() {
  requestAction('editor_save', { path: imagePath.value })
  // 저장 완료 신호는 별도지만, 사용자 입장에서는 곧바로 깨끗 상태
  isDirty.value = false
  initialImagePath.value = imagePath.value
}
function saveAsImage() {
  requestAction('editor_save_as', { path: imagePath.value })
}

// 클립보드에서 이미지 붙여넣기 — navigator.clipboard.read() → base64 → Python에 저장 요청
// 화이트리스트: cv2.imread가 처리 가능한 포맷만 (HEIC/AVIF 등은 거부)
const _CLIPBOARD_ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/bmp', 'image/webp']
async function pasteFromClipboard() {
  try {
    if (!navigator.clipboard || !navigator.clipboard.read) {
      requestAction('show_toast', { type: 'info', msg: '브라우저가 클립보드 API를 지원하지 않습니다 — 파일로 열어주세요' })
      return
    }
    const items = await navigator.clipboard.read()
    for (const item of items) {
      // 화이트리스트에 있는 타입만 — image/heic, image/avif 등 cv2 미지원 거부
      const imageType = item.types.find(t => _CLIPBOARD_ALLOWED_TYPES.includes(t.toLowerCase()))
      if (!imageType) {
        // 이미지가 있지만 지원 안 하는 포맷
        const anyImage = item.types.find(t => t.startsWith('image/'))
        if (anyImage) {
          requestAction('show_toast', {
            type: 'warning',
            msg: `지원 안 하는 이미지 포맷: ${anyImage} (PNG/JPG/BMP/WEBP만 가능)`,
          })
          return
        }
        continue
      }
      {
        const blob = await item.getType(imageType)
        const buf = await blob.arrayBuffer()
        const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)))
        const backend: any = await getBackend()
        if (backend.editorPasteImage) {
          backend.editorPasteImage(b64, imageType, (json: string) => {
            try {
              const r = JSON.parse(json)
              if (r.path) {
                loadImage(r.path)
                requestAction('show_toast', { type: 'success', msg: '클립보드 이미지 로드 완료' })
              } else {
                requestAction('show_toast', { type: 'error', msg: r.error || '붙여넣기 실패' })
              }
            } catch {}
          })
        }
        return
      }
    }
    requestAction('show_toast', { type: 'info', msg: '클립보드에 이미지가 없습니다' })
  } catch (e: any) {
    requestAction('show_toast', { type: 'error', msg: `클립보드 접근 실패: ${e.message || e}` })
  }
}

function confirmClose() {
  if (isDirty.value) {
    if (!window.confirm('저장하지 않은 변경 사항이 있습니다.\n정말 닫으시겠습니까?')) return
  }
  resetEditor()
}
function resetEditor() {
  imagePath.value = ''; imageDisplay.value = ''
  undoStack.value = []; redoStack.value = []
  isDirty.value = false; initialImagePath.value = ''
}

// 앱 시작 시 YOLO 라벨 로드
async function refreshYoloLabel() {
  const backend: any = await getBackend()
  if (backend.getYoloModelLabel) {
    backend.getYoloModelLabel((label: string) => { if (label) modelLabel.value = label })
  }
}

// Ctrl 빠른 두 번 누름 감지 — 변환(zoom/rotation/pan) 초기화
let _lastCtrlTime = 0
const CTRL_DOUBLE_TAP_MS = 300

function onEditorKeyDown(e: KeyboardEvent) {
  // ── Ctrl 단독 두 번 빠르게 → 변환 reset (모자이크/그리기는 유지)
  // (다른 Ctrl 조합은 _lastCtrlTime 갱신 안 함 — Ctrl+Z 등과 충돌 회피)
  if (e.key === 'Control' && !e.altKey && !e.shiftKey) {
    const now = Date.now()
    if (now - _lastCtrlTime < CTRL_DOUBLE_TAP_MS) {
      _lastCtrlTime = 0
      if (imagePath.value && canvasRef.value?.resetTransform) {
        canvasRef.value.resetTransform()
        requestAction('show_toast', { type: 'info', msg: '확대/회전/위치 초기화' })
      }
    } else {
      _lastCtrlTime = now
    }
    return
  }

  // Ctrl+O / Ctrl+V는 이미지 없어도 동작 (열기/붙여넣기)
  if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'o') {
    e.preventDefault(); openFile(); return
  }
  if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'v') {
    e.preventDefault(); pasteFromClipboard(); return
  }
  // 이미지가 없으면 그 외 단축키는 무시
  if (!imagePath.value) return
  // 저장
  if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 's') { e.preventDefault(); saveAsImage(); return }
  if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 's') { e.preventDefault(); saveImage(); return }
  // Undo / Redo (마스크 우선, 그 다음 작업)
  // stopImmediatePropagation으로 다른 핸들러(PromptPanel 등)가 같은 키를 가로채지 못하게
  // — Editor 탭에서는 Editor undo가 우선권을 가짐 (사용자 명시 요구사항)
  if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'z') {
    e.preventDefault(); e.stopImmediatePropagation()
    onRedo(); return
  }
  if (e.ctrlKey && e.key.toLowerCase() === 'z') {
    e.preventDefault(); e.stopImmediatePropagation()
    onUndo(); return
  }
  if (e.ctrlKey && e.key.toLowerCase() === 'y') {
    e.preventDefault(); e.stopImmediatePropagation()
    onRedo(); return
  }
  if (e.key === 'Escape') canvasRef.value?.clearSelection()
}

// 자동 저장 — 5분마다 변경 있으면 임시본 기록
let _autoSaveTimer: ReturnType<typeof setInterval> | null = null
const AUTO_SAVE_INTERVAL_MS = 5 * 60 * 1000
// 마지막 자동저장 시각 — 상태바에 "마지막 저장: N분 전" 표시
const lastAutoSaveAt = ref(0)
const _nowTick = ref(0)  // 1분마다 증가 — autoSaveAgoText 재계산 트리거
const autoSaveAgoText = computed(() => {
  // 의존성: lastAutoSaveAt + _nowTick
  void _nowTick.value
  if (!lastAutoSaveAt.value) return ''
  const sec = Math.floor((Date.now() - lastAutoSaveAt.value) / 1000)
  if (sec < 60) return `${sec}초 전`
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`
  return `${Math.floor(sec / 3600)}시간 전`
})
// 표시 부드럽게 갱신 — 매 분
let _autoSaveTickTimer: ReturnType<typeof setInterval> | null = null
async function _tryAutoSave() {
  if (!isDirty.value || !imagePath.value) return
  try {
    const backend: any = await getBackend()
    if (backend.editorAutoSave) {
      backend.editorAutoSave(imagePath.value.replace('file:///', ''), (json: string) => {
        try {
          const r = JSON.parse(json)
          if (r.path) {
            console.log('[Editor] auto-saved →', r.path)
            lastAutoSaveAt.value = Date.now()
          }
        } catch {}
      })
    }
  } catch {}
}

async function _checkAutoSaveRecovery() {
  try {
    const backend: any = await getBackend()
    if (backend.editorCheckAutoSave) {
      backend.editorCheckAutoSave((json: string) => {
        try {
          const r = JSON.parse(json)
          if (r.path && r.exists) {
            if (window.confirm(
              `이전 세션에 저장되지 않은 작업이 있습니다.\n` +
              `(${r.basename || ''}, ${r.age_minutes || '?'}분 전)\n\n` +
              `복구할까요?`
            )) {
              loadImage(r.path)
              requestAction('show_toast', { type: 'success', msg: '이전 작업 복구됨' })
            } else if (backend.editorClearAutoSave) {
              backend.editorClearAutoSave(() => {})
            }
          }
        } catch {}
      })
    }
  } catch {}
}

onMounted(() => {
  onBackendEvent('editorImageLoaded', (path: string) => loadImage(path))
  onBackendEvent('yoloModelUpdated', (label: string) => { modelLabel.value = label })
  // 앱 시작 시 YOLO 모델 자동 감지 + 최근 파일 로드 + 크래시 복구 확인
  refreshYoloLabel()
  _loadRecentFiles()
  _checkAutoSaveRecovery()
  document.addEventListener('keydown', onEditorKeyDown)
  // 5분마다 자동 저장 시도
  _autoSaveTimer = setInterval(_tryAutoSave, AUTO_SAVE_INTERVAL_MS)
  // 60초마다 "N분 전" 표시 갱신 (computed 의존성 _nowTick)
  _autoSaveTickTimer = setInterval(() => { _nowTick.value++ }, 60_000)
  // 사이드 패널 폭이 Settings에서 변경되면 동기화
  window.addEventListener('storage', _syncSidePanelWidthFromStorage)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onEditorKeyDown)
  if (_autoSaveTimer) clearInterval(_autoSaveTimer)
  if (_autoSaveTickTimer) clearInterval(_autoSaveTickTimer)
  window.removeEventListener('storage', _syncSidePanelWidthFromStorage)
})
</script>

<style scoped>
.editor-view { width: 100%; height: 100%; display: flex; flex-direction: column; }

.top-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px; background: #0D0D0D; flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}
.bar-group { display: flex; align-items: center; gap: 6px; }
.bar-group.center { flex: 1; justify-content: center; }
.bar-btn {
  padding: 8px 16px; background: #181818; border: 1px solid var(--border); border-radius: 6px;
  color: #909090; font-size: 12px; font-weight: 600; cursor: pointer; white-space: nowrap;
  transition: var(--transition);
}
.bar-btn:hover { background: #222; color: #E8E8E8; border-color: #333; }
.bar-btn:disabled { opacity: 0.3; }
.bar-btn.accent { border-color: var(--accent-dim); color: var(--accent); }
.bar-btn.save { background: var(--accent); color: #000; border: none; font-weight: 800; }
.bar-btn.save:hover { background: var(--accent-hover); }
.bar-btn.danger { color: #f87171; border-color: rgba(248,113,113,0.2); }
.bar-sep { color: #333; margin: 0 4px; }
.bar-info { color: #585858; font-size: 11px; font-family: 'Consolas', monospace; }
.bar-info.autosave { color: #4ade80; opacity: 0.75; }
.bar-info.autosave:hover { opacity: 1; cursor: help; }
.bar-filename {
  color: #c8c8c8; font-size: 12px; font-weight: 600;
  max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 8px;
}
.dirty-mark { color: #fbbf24; margin-right: 4px; font-size: 14px; vertical-align: middle; }
.bar-counter { color: #585858; font-size: 9px; font-family: 'Consolas', monospace; margin-left: 4px; }

.editor-body { flex: 1; display: flex; overflow: hidden; }

.side-panel {
  width: 280px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
}
.tab-buttons { display: flex; flex-wrap: wrap; gap: 2px; padding: 4px; background: #0A0A0A; flex-shrink: 0; }
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
.drop-actions { display: flex; gap: 8px; }
.open-btn {
  padding: 10px 24px; background: #E2B340; border: none; border-radius: 8px;
  color: #000; font-weight: 700; font-size: 14px; cursor: pointer;
}
.open-btn.secondary { background: #2A2A2A; color: #E2B340; border: 1px solid #E2B340; }
.drop-shortcuts { color: #585858; font-size: 11px; margin-top: 4px; }
.drop-shortcuts kbd {
  background: #1A1A1A; color: #E2B340; padding: 1px 6px; border-radius: 3px;
  font-family: Consolas, monospace; font-size: 10px; margin: 0 2px;
}
.recent-files { width: 100%; max-width: 540px; margin-top: 14px; }
.recent-label { color: #787878; font-size: 10px; letter-spacing: 1px;
  font-weight: 800; padding: 0 4px 6px; }
.recent-list { display: flex; flex-wrap: wrap; gap: 6px; }
.recent-item {
  padding: 6px 12px; background: #1A1A1A; border: 1px solid #2A2A2A;
  border-radius: 6px; color: #c8c8c8; font-size: 11px; cursor: pointer;
  max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.recent-item:hover { background: #222; border-color: #E2B340; color: #E2B340; }
.recent-name { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.feature-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; justify-content: center; }
.feature-list span { padding: 5px 12px; background: #131313; border-radius: 6px; color: #585858; font-size: 11px; }
</style>
