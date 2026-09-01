<template>
  <div class="editor-view" @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @drop.prevent="onDrop">
    <template v-if="imagePath">
      <!-- 상단 도구바 -->
      <div class="top-bar">
        <div class="bar-group">
          <button class="bar-btn accent" @click="openFile" title="Ctrl+O"><Icon name="folder-open" /> 열기</button>
          <button class="bar-btn save" @click="saveImage" title="Ctrl+S"><Icon name="save" /> 저장</button>
          <button class="bar-btn" @click="saveAsImage" title="Ctrl+Shift+S"><Icon name="save" /> 다른 이름</button>
          <button class="bar-btn" @click="pasteFromClipboard" title="Ctrl+V"><Icon name="clipboard" /> 붙여넣기</button>
        </div>
        <div class="bar-group center">
          <button class="bar-btn" @click="onUndo" :disabled="undoStack.length <= 1 && !canvasRef?.maskUndoCount" title="Ctrl+Z (마스킹 우선)">
            <Icon name="undo" /> Undo <span class="bar-counter">({{ Math.max(0, undoStack.length - 1) }}/{{ MAX_UNDO }})</span>
          </button>
          <button class="bar-btn" @click="onRedo" :disabled="redoStack.length === 0 && !canvasRef?.maskRedoCount" title="Ctrl+Y (마스킹 우선)">
            <Icon name="redo" /> Redo <span class="bar-counter">({{ redoStack.length }})</span>
          </button>
          <span class="bar-sep">|</span>
          <span class="bar-filename" :title="imagePath">
            <span v-if="isDirty" class="dirty-mark">●</span>{{ baseName }}
          </span>
          <span class="bar-info">{{ imgWidth }}×{{ imgHeight }}{{ fileInfoExtra }}</span>
          <span v-if="autoSaveAgoText" class="bar-info autosave" :title="`마지막 자동저장: ${new Date(lastAutoSaveAt).toLocaleTimeString()}`"><Icon name="save" /> {{ autoSaveAgoText }}
          </span>
        </div>
        <div class="bar-group">
          <button class="bar-btn danger" @click="confirmClose"><Icon name="close" /> 닫기</button>
        </div>
      </div>

      <div class="editor-body">
        <!-- 캔버스 도구 툴바 — 도구를 고르려고 탭을 옮기지 않아도 되게 -->
        <EditorToolbar :model-value="currentTool" @select="selectTool" />

        <!-- 좌측: 서브탭 패널 — 너비는 localStorage 영속 -->
        <div class="side-panel" :style="{ width: sidePanelWidth + 'px' }">
          <div class="tab-buttons">
            <button v-for="(tab, i) in tabs" :key="i"
              class="tab-btn" :class="{ active: activeTab === i }"
              @click="switchTab(i)"
            >{{ tab.icon }} {{ tab.label }}</button>
          </div>
          <div class="tab-content">
            <MosaicPanel v-show="activeTab === 0" ref="mosaicPanelRef"
              :img-width="imgWidth" :img-height="imgHeight" :crop-pending="cropPending"
              :model-label="modelLabel"
              :detect-status="detectStatus"
              :perspective-active="perspectiveActive"
              @tool-changed="onToolChanged"
              @effect-apply="applyEffect"
              @add-model="openModelDialog"
              @clear-models="clearModels"
              @auto-censor="runAutoCensor"
              @auto-detect="runAutoDetect"
              @cancel-selection="canvasRef?.clearSelection()"
              @crop="doCrop" @crop-confirm="confirmCrop" @crop-cancel="cancelCrop"
              @resize="doResize"
              @perspective-start="onStartPerspective"
              @perspective-confirm="onConfirmPerspective"
              @perspective-cancel="onCancelPerspective"
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
              @filter-preview="previewFilter" @filter-cancel="clearPreview"
              @auto-correct="doOp('auto_correct')"
            />
            <AdvancedColorPanel v-show="activeTab === 2"
              :src="canvasSrc" :active="activeTab === 2"
              @preview="previewAdvAdj" @apply="applyAdvAdj" @reset="resetAdj"
            />
            <WatermarkPanel v-show="activeTab === 3"
              @apply-text="applyTextWm" @apply-image="applyImageWm"
              @load-watermark-image="loadWatermarkImage"
              :text-color="wmTextColor"
              @preview="previewWatermark" @preview-clear="clearPreview"
              @pick-text-color="() => pickColor('wmText')"
              @clamp-changed="v => wmClamp = v"
            />
            <DrawPanel v-show="activeTab === 4" ref="drawPanelRef"
              :gradient-end-color="drawGradientEnd"
              @tool-changed="onDrawToolChanged"
              @params-changed="onDrawToolChanged"
              @color-changed="p => drawParams.color = p.color"
              @pick-custom-color="() => pickColor('draw')"
              @pick-gradient-end-color="() => pickColor('gradient')"
              @layer-opacity-changed="v => drawLayerOpacity = v"
              @heal-apply="applyHeal"
              @flatten-layer="applyFlatten"
              @undo-stroke="undoDrawStroke"
              @clear-layer="clearDrawLayer"
            />
            <MovePanel v-show="activeTab === 5" ref="movePanelRef"
              :status-text="moveStatusText"
              :can-inpaint="canInpaint"
              @send-inpaint="onSendInpaint"
              :can-undo="undoStack.length > 1"
              @start-move="onStartMove"
              @confirm-move="onConfirmMove"
              @cancel-move="onCancelMove"
              @undo-move="onUndo"
              @rotation-changed="v => moveRotation = v"
              @scale-changed="v => moveScale = v"
            />
          </div>
        </div>

        <!-- 중앙: 캔버스 -->
        <EditorCanvas ref="canvasRef"
          :image-src="canvasSrc"
          :tool="currentTool"
          :brush-size="brushSize"
          :eraser-mode="eraserMode"
          :eraser-restore="eraserRestore"
          :magnetic-lasso="magneticLasso"
          :stamp-spacing="stampSpacing"
          :stamp-shape="stampShape"
          :bar-width="barWidth"
          :bar-height="barHeight"
          :draw-params="canvasDrawParams"
          :layer-opacity="drawLayerOpacity"
          @selection-changed="onSelectionChanged"
          @restore-ready="commitRestore"
          @color-picked="onEyedropperColor"
        />
      </div>
    </template>

    <template v-else>
      <div class="drop-area" :class="{ dragging: isDragging }">
        <div class="drop-icon"><Icon name="palette" /></div>
        <h2>Image Editor</h2>
        <p>이미지를 드래그앤드롭하거나 파일을 선택하세요</p>
        <div class="drop-actions">
          <button class="open-btn" @click="openFile"><Icon name="folder-open" /> 파일 선택</button>
          <button class="open-btn secondary" @click="pasteFromClipboard"><Icon name="clipboard" /> 클립보드</button>
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
import { ref, computed, watch, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend, onBackendEvent } from '../bridge.js'
import { mediaUrl } from '../utils/media.js'
import { isIdentity } from '../utils/curves'
import EditorCanvas from '../components/editor/EditorCanvas.vue'
import MosaicPanel from '../components/editor/MosaicPanel.vue'
import ColorPanel from '../components/editor/ColorPanel.vue'
import AdvancedColorPanel from '../components/editor/AdvancedColorPanel.vue'
import WatermarkPanel from '../components/editor/WatermarkPanel.vue'
import DrawPanel from '../components/editor/DrawPanel.vue'
import MovePanel from '../components/editor/MovePanel.vue'
import EditorToolbar from '../components/editor/EditorToolbar.vue'
import { toolById, toolByKey } from '../utils/editorTools'

const isDragging = ref(false)
const imagePath = ref('')
const imageDisplay = ref('')
// 프리뷰가 살아있는 동안 캔버스는 이 base64 를 보여준다. 파일도 undo 도 건드리지 않는다.
const previewSrc = ref('')
const canvasSrc = computed(() => previewSrc.value || imageDisplay.value)
// 확정 이미지가 바뀌면 프리뷰는 무조건 무효다. 결과 핸들러 안에서 인라인으로
// 지우면 도착 순서(늦게 온 프리뷰, keep-alive 로 살아있는 옛 리스너)에 흔들린다.
watch(imageDisplay, () => { previewSrc.value = '' })
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
const mosaicPanelRef = ref<any>(null)
const movePanelRef = ref<any>(null)
const selection = ref<any>(null)
const modelLabel = ref('No Model Loaded')
const detectStatus = ref('')

// 마스크 영역 이동(MovePanel) 상태 — 드래그 미리보기는 캔버스가, 확정은 백엔드가 한다
const moveStatusText = ref('마스킹을 먼저 해주세요')
const moveRotation = ref(0)
const moveScale = ref(100)
const moveFillColor = ref('black')
// 드로잉 레이어 불투명도 (병합 시 사용)
const drawLayerOpacity = ref(100)
// DrawPanel이 보내는 도구 파라미터. currentTool 에는 문자열만 넣는다(캔버스가 문자열 비교).
const drawParams = ref<{ tool: string; color: string; size: number; opacity: number; filled: boolean }>({
  tool: 'pen', color: '#ffffff', size: 10, opacity: 1, filled: false,
})
const wmClamp = ref(true)          // 워터마크 '이미지 영역 내 제한'
const wmImagePath = ref('')        // 이미지 워터마크로 고른 파일 경로
const wmTextColor = ref('#FFFFFF') // 텍스트 워터마크 색 (WatermarkPanel의 textColor prop)
const drawGradientEnd = ref('#000000')  // 그라디언트 끝 색 (DrawPanel의 gradientEndColor prop)
// 캔버스로 내려보내는 최종 그리기 파라미터 — 끝 색은 따로 관리되므로 여기서 합친다
const canvasDrawParams = computed(() => ({ ...drawParams.value, gradientEnd: drawGradientEnd.value }))

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
  imageDisplay.value = mediaUrl(path, true)
  canvasRef.value?.clearSelection(true)   // 새 이미지: stale 마스크 + undo/redo 스택 초기화
  _pushRecentFile(path)
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = mediaUrl(path)
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
  imageDisplay.value = mediaUrl(path, true)
  const img = new Image()
  img.onload = () => { imgWidth.value = img.naturalWidth; imgHeight.value = img.naturalHeight }
  img.src = mediaUrl(path)
  if (clearMask) canvasRef.value?.clearSelection(true)   // 이미지 작업 후: 마스크 히스토리도 리셋
}

function doUndo() {
  if (undoStack.value.length <= 1) return
  redoStack.value.push(undoStack.value.pop() as string)
  const path = undoStack.value[undoStack.value.length - 1]
  imagePath.value = path
  imageDisplay.value = mediaUrl(path, true)
}
function doRedo() {
  if (redoStack.value.length === 0) return
  const path = redoStack.value.pop() as string
  undoStack.value.push(path)
  imagePath.value = path
  imageDisplay.value = mediaUrl(path, true)
}
// 통합 undo/redo — 마스킹이 있으면 마스킹 먼저, 없으면 이미지 작업. (버튼·Ctrl+Z/Y 공용)
function onUndo() { if (canvasRef.value?.undoMask()) return; doUndo() }
function onRedo() { if (canvasRef.value?.redoMask()) return; doRedo() }

// 에디터 작업 순서 보장 — editorProcess는 클릭마다 백그라운드 스레드를 띄우고 job_id를
// 반환한다. 느린 작업 A 뒤에 빠른 B를 실행하면 A 결과가 *나중*에 도착해 B를 덮을 수 있다.
// 시작 시 받은 job_id 중 최대값(_latestEditorJob)만 유효로 보고, 더 낮은 job 결과는 버린다.
let _latestEditorJob = 0
function _captureJob(result: any) {
  if (result && typeof result.job_id === 'number' && result.job_id > _latestEditorJob) {
    _latestEditorJob = result.job_id
  }
}

async function doOp(operation: string, params: any = {}) {
  if (!imagePath.value) return
  // 확정 작업이면 예약된 프리뷰를 먼저 취소한다(결과 역전 방지).
  if (!params.preview) cancelPendingPreview()
  const backend: any = await getBackend()
  const cleanPath = imagePath.value.replace('file:///', '')
  // 처리는 비동기 — 결과는 editorResult 이벤트로 도착. 콜백은 즉시 거절(경로/파라미터 오류)만 + job_id 캡처.
  backend.editorProcess(cleanPath, operation, JSON.stringify(params), (json: string) => {
    try {
      const result = JSON.parse(json)
      _captureJob(result)
      if (result.error) console.error('[Editor] error:', result.error)
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
      _captureJob(result)
      if (result.error) console.error('[Editor] error:', result.error)
    } catch (e) { console.error('[Editor] parse error:', e) }
  })
}

// editorResult — 백그라운드 처리 완료 수신 (onMounted에서 연결)
function onEditorResult(json: string) {
  try {
    const result = JSON.parse(json)
    // 순서 역전 차단 — 더 새 작업(job_id↑)이 이미 시작됐으면 늦게 온 옛 결과는 버림
    if (typeof result.job_id === 'number' && result.job_id < _latestEditorJob) {
      return
    }
    if (result.preview) {
      // 원본이 그새 교체됐으면(적용/회전 등) 이 프리뷰는 이미 낡았다 — 버린다.
      if (_previewForPath && _previewForPath !== imagePath.value) return
      // 프리뷰는 화면에만 반영한다 — 파일 교체도 undo 푸시도 하지 않는다.
      previewSrc.value = result.image_base64 || ''
      return
    }
    if (result.path) {
      previewSrc.value = ''   // 확정 결과가 왔으니 프리뷰는 걷는다
      pushState(result.path)
      if (result.operation === 'auto_censor') detectStatus.value = '완료'
    } else if (result.mask_base64) {
      canvasRef.value?.loadMaskFromBase64(result.mask_base64)
      detectStatus.value = `${result.detect_count || 0}개 감지됨`
    } else if (result.error) {
      // 콘솔에만 찍으면 사용자는 '무반응'으로 느낀다 — 토스트로 올린다
      console.error('[Editor] error:', result.error)
      requestAction('show_toast', { type: 'error', msg: result.error })
      if (result.operation === 'auto_censor' || result.operation === 'auto_detect') {
        detectStatus.value = result.error
      }
    }
  } catch (e) { console.error('[Editor] parse error:', e) }
}

function onToolChanged(data: any) {
  const id = typeof data === 'object' ? data.tool : data
  const toolMap: Record<string, string> = { 0: 'box', 1: 'lasso', 2: 'brush', 3: 'eraser', 4: 'stamp' }
  currentTool.value = toolMap[id] ?? 'box'
  if (typeof data === 'object' && data.size) brushSize.value = data.size
}

// ── 세로 툴바 ──
// 도구를 고르면 (1) 캔버스 모드를 바꾸고 (2) 그 도구의 옵션이 있는 탭을 연다.
// 패널이 다른 탭을 보여주고 있으면 "골랐는데 설정이 어디 갔지"가 되기 때문이다.
const TOOL_TAB: Record<string, number> = { mask: 0, draw: 4 }

function selectTool(id: string) {
  const tool = toolById(id)
  if (!tool) return
  clearPreview()
  currentTool.value = id
  const tab = TOOL_TAB[tool.kind]
  if (tab !== undefined && activeTab.value !== tab) activeTab.value = tab
  if (tool.kind === 'draw') {
    // 캔버스가 보는 값과 패널 하이라이트를 함께 맞춘다 — 한쪽만 바꾸면 서로 다른 도구를 가리킨다
    drawParams.value = { ...drawParams.value, tool: id }
    drawPanelRef.value?.setTool?.(id)
  } else {
    mosaicPanelRef.value?.setTool?.(id)
  }
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

// ── 모자이크 지우개 커밋 ──
// 지우개는 화면 캔버스만 되돌린다(저장은 파일 경로 기반이라 그대로 두면 결과가 사라짐).
// 효과 적용 직전 이미지 경로를 pristinePath로 들고 있다가, 그 파일에서 픽셀을 되가져온다.
const pristinePath = ref('')
async function commitRestore() {
  const maskB64 = canvasRef.value?.getRestoreMaskBase64?.()
  if (!maskB64) return
  if (!pristinePath.value) {
    // 되돌릴 '적용 전' 이미지가 없다 — 화면만 되돌아간 상태이므로 사용자에게 알린다
    requestAction('show_toast', {
      type: 'info', msg: '되돌릴 이전 상태가 없습니다 (효과를 먼저 적용하세요)',
    })
    canvasRef.value?.clearRestoreMask?.()
    return
  }
  canvasRef.value?.keepPristineForNextLoad?.()
  doOp('restore', {
    mask_base64: maskB64,
    source_path: pristinePath.value.replace('file:///', ''),
  })
  canvasRef.value?.clearRestoreMask?.()
}

function applyEffect(effectData: any) {
  const sel = canvasRef.value?.getSelection()
  const effectMap: Record<string, string> = { 0: 'mosaic', 1: 'censor_bar', 2: 'blur' }
  const op = effectMap[effectData.effect] ?? 'mosaic'
  if (!sel) {
    // 예전엔 조용히 return 해서 "APPLY를 눌렀는데 아무 일도 안 남"이었다
    requestAction('show_toast', {
      type: 'warning',
      msg: '적용할 영역이 없습니다 — 브러시/올가미/박스로 먼저 마스킹하세요',
    })
    return
  }
  // 효과 적용 전 상태를 기억해 둔다 — 모자이크 지우개가 이 픽셀을 되살린다.
  // pristine 스냅샷도 이번 교체에 한해 유지해야 지우개가 '적용 전' 그림을 본다.
  pristinePath.value = imagePath.value
  canvasRef.value?.keepPristineForNextLoad?.()
  doOpWithMask(op, { ...effectData, selection: sel })
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
  // SAM3는 텍스트 기반 세그멘터 — detect prompt가 있으면 YOLO 없이도 단독 실행된다
  if (samModel === 'sam3' && params?.detectPrompt && String(params.detectPrompt).trim()) {
    payload.detect_prompt = String(params.detectPrompt).trim()
  }
  // 결과는 editorResult 이벤트로 도착 — 콜백은 즉시 거절만 처리 + job_id 캡처
  backend.editorProcess(cleanPath, 'auto_censor', JSON.stringify(payload), (json: string) => {
    try {
      const result = JSON.parse(json)
      _captureJob(result)
      if (result.error) detectStatus.value = result.error
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
  // SAM3는 텍스트 기반 세그멘터 — detect prompt가 있으면 YOLO 없이도 단독 실행된다
  if (samModel === 'sam3' && params?.detectPrompt && String(params.detectPrompt).trim()) {
    payload.detect_prompt = String(params.detectPrompt).trim()
  }
  // 결과(mask_base64)는 editorResult 이벤트로 도착 — 콜백은 즉시 거절만 처리 + job_id 캡처
  backend.editorProcess(cleanPath, 'auto_detect', JSON.stringify(payload), (json: string) => {
    try {
      const result = JSON.parse(json)
      _captureJob(result)
      if (result.error) detectStatus.value = result.error
    } catch { detectStatus.value = '오류' }
  })
}

// 예전에는 마스크 bbox 로 확인 없이 즉시 잘랐고, 선택이 없으면 아무 말 없이 무시했다.
const cropSel = ref<any>(null)
const cropPending = computed(() => {
  const s = cropSel.value
  if (!s) return ''
  // EditorCanvas.getSelection() 은 {x, y, w, h} 를 준다
  return `${Math.max(0, Math.round(s.w))} × ${Math.max(0, Math.round(s.h))}`
})
function doCrop() {
  const sel = canvasRef.value?.getSelection()
  if (!sel) {
    requestAction('show_toast', { type: 'warning', msg: '먼저 자를 영역을 선택하세요' })
    return
  }
  cropSel.value = sel
}
function confirmCrop() {
  if (!cropSel.value) return
  doOp('crop', { selection: cropSel.value })
  cropSel.value = null
}
function cancelCrop() { cropSel.value = null }

// ── 원근 보정 ──
// 꼭짓점 4개를 드래그해 '원본에서 직사각형이어야 할 영역'을 지정하면
// 백엔드(core/editor_ops.perspective)가 그 사다리꼴을 정직사각형으로 편다.
// 출력 크기는 넘기지 않는다 — 백엔드가 대변 길이 최댓값으로 추론한다.
const perspectiveActive = ref(false)
function onStartPerspective() {
  if (!imagePath.value) return
  perspectiveActive.value = true
  currentTool.value = 'perspective'
  canvasRef.value?.beginPerspective?.()
  requestAction('show_toast', {
    type: 'info', msg: '꼭짓점 4개를 펴고 싶은 사각형 모서리에 맞춘 뒤 "적용"을 누르세요',
  })
}
function onConfirmPerspective() {
  const corners = canvasRef.value?.endPerspective?.()
  perspectiveActive.value = false
  currentTool.value = 'box'
  if (!corners) {
    requestAction('show_toast', { type: 'warning', msg: '꼭짓점 정보가 없습니다' })
    return
  }
  doOp('perspective', { corners })
}
function onCancelPerspective() {
  canvasRef.value?.cancelPerspective?.()
  perspectiveActive.value = false
  currentTool.value = 'box'
}
function doResize(params?: any) { doOp('resize', params) }
function applyAdj(adj: any) { doOp('color_adjust', adj) }
// ── 실시간 프리뷰 ────────────────────────────────────────────────────────
// 예전에는 이 두 함수가 빈 TODO 였다. 패널은 열심히 emit 하는데 받는 쪽이
// 아무것도 안 해서, 슬라이더를 움직여도 화면이 그대로였다(= '적용해야 결과를 앎').
// 백엔드가 축소본으로 같은 연산을 돌려 base64 로 돌려준다 — CSS 필터 근사와 달리
// 12종 필터·HSV 채도·레벨까지 실제 결과와 일치한다.
let _previewTimer: ReturnType<typeof setTimeout> | null = null
// 프리뷰를 쏠 때의 원본 경로. 확정 작업이 끼어들어 이미지가 교체되면, 뒤늦게
// 도착하는 프리뷰는 '옛 이미지 기준' 결과라 화면에 올리면 안 된다.
// (job_id 가드는 이걸 못 잡는다 — 늦게 쏜 프리뷰가 job_id 는 더 크기 때문)
let _previewForPath = ''
function schedulePreview(operation: string, params: any) {
  if (!imagePath.value) return
  if (_previewTimer) clearTimeout(_previewTimer)
  _previewTimer = setTimeout(() => {
    _previewForPath = imagePath.value
    doOp(operation, { ...params, preview: true })
  }, 120)
}
// 대기 중인 프리뷰만 취소한다(화면은 그대로) — 확정 작업을 보낼 때 쓴다.
// 이걸 안 하면: 적용 클릭 → 패널이 adjustment-changed 도 함께 emit → 120ms 뒤
// 프리뷰가 한 번 더 나가고, 그게 적용보다 늦게 도착해 job_id 가 더 커서 가드도
// 통과하며 화면을 축소본으로 되돌린다(실제로 있었던 증상).
function cancelPendingPreview() {
  if (_previewTimer) { clearTimeout(_previewTimer); _previewTimer = null }
}
function clearPreview() {
  cancelPendingPreview()
  previewSrc.value = ''
}
// 조정값이 전부 중립이면 보여줄 게 없다 — 프리뷰를 요청하지 말고 걷는다.
// (ColorPanel.onApply 는 적용 후 resetSliders() 를 부르고, 그 watch 가
//  adjustment-changed {0,0,0} 을 다시 쏜다. 그걸 그대로 프리뷰로 만들면
//  방금 확정한 전체 해상도 결과를 축소본이 덮어쓴다.)
function previewAdj(adj: any) {
  if (!adj || (!adj.brightness && !adj.contrast && !adj.saturation)) { clearPreview(); return }
  schedulePreview('color_adjust', adj)
}
function previewAdvAdj(adj: any) {
  // 커브도 함께 봐야 한다 — 슬라이더가 전부 중립이어도 커브만 건드린 경우가 있다.
  const neutral = !adj || (!adj.blackPoint && (adj.whitePoint ?? 255) === 255
    && Math.abs((adj.gamma ?? 1) - 1) < 1e-6 && !adj.temperature && !adj.tint
    && isIdentity(adj.curves))
  if (neutral) { clearPreview(); return }
  schedulePreview('adv_color', adj)
}
function previewFilter(payload: any) {
  if (!payload || !payload.filter || !payload.strength) { clearPreview(); return }
  schedulePreview('filter', payload)
}
// WatermarkPanel 은 텍스트/이미지 두 설정을 같은 'preview' 로 보낸다 — text 유무로 가른다.
function previewWatermark(cfg: any) {
  if (!cfg) return
  if (typeof cfg.text === 'string') {
    schedulePreview('text_watermark', { ...cfg, clamp: wmClamp.value, color: wmTextColor.value })
  } else if (wmImagePath.value) {
    schedulePreview('image_watermark', { ...cfg, clamp: wmClamp.value, watermark_path: wmImagePath.value })
  }
}
function switchTab(i: number) { clearPreview(); activeTab.value = i }
function resetAdj() { clearPreview() }
// ColorPanel은 { filter, strength }를 보낸다. 예전 `filter.name || filter.type`은
// 둘 다 없어서 operation이 undefined로 나갔고, 백엔드는 모든 분기를 통과해
// 원본을 그대로 재저장했다 (= 필터 프리셋 전부 무반응).
function applyFilter(payload: any) {
  if (!payload?.filter) return
  doOp('filter', { filter: payload.filter, strength: payload.strength ?? 100 })
}
function applyAdvAdj(adj: any) { doOp('adv_color', adj) }

// ── 드로잉 레이어 병합 ──
// DrawPanel이 emit하는 이름은 'flatten-layer'인데 예전에는 '@flatten'에 물려 있어
// 버튼이 아예 아무것도 안 했다. 오버레이 캔버스를 base64로 실어 보낸다.
async function applyFlatten() {
  const overlay = canvasRef.value?.getDrawOverlayBase64?.()
  if (!overlay) {
    requestAction('show_toast', { type: 'info', msg: '병합할 드로잉이 없습니다' })
    return
  }
  doOp('flatten', { overlay_base64: overlay, opacity: drawLayerOpacity.value })
  // 레이어 비우기는 imagePath 감시가 맡는다 — 병합 결과가 새 경로로 돌아오면 지워진다.
  // 여기서 미리 지우면 백엔드가 실패했을 때 그린 게 통째로 날아간다.
}

// 확정 이미지가 바뀌면(병합·회전·자르기·undo 등) 드로잉 레이어는 더 이상 맞지 않는다.
// 예: 회전 후에도 레이어가 남아 있으면 안 돌아간 그림이 돌아간 이미지 위에 얹힌다.
watch(imagePath, () => canvasRef.value?.clearDrawLayer?.())

// ── 마스크 영역 이동 (MovePanel) ──
// MovePanel은 'confirm-move'/'cancel-move'를 emit하는데 예전에는 '@confirm'/'@cancel'에
// 물려 있어 전부 죽어 있었다. 게다가 백엔드에 start/confirm/cancel_move 핸들러가 없었다.
// 이제 이동은 캔버스에서 드래그로 미리보기하고, 확정할 때 한 번만 백엔드 move_region을 부른다.
function onStartMove(payload: any) {
  if (!canvasRef.value?.getSelection()) {
    requestAction('show_toast', { type: 'warning', msg: '이동할 영역을 먼저 마스킹하세요' })
    movePanelRef.value?.setMovingState?.(false)
    return
  }
  moveFillColor.value = payload?.fillColor || 'black'
  moveRotation.value = payload?.rotation ?? 0
  moveScale.value = payload?.scale ?? 100
  currentTool.value = 'move'
  canvasRef.value?.beginMove?.()
  moveStatusText.value = '영역을 드래그해 옮긴 뒤 "확정"을 누르세요'
}

function onConfirmMove(payload: any) {
  const offset = canvasRef.value?.endMove?.() || { dx: 0, dy: 0 }
  currentTool.value = 'box'
  moveStatusText.value = '마스킹을 먼저 해주세요'
  doOpWithMask('move_region', {
    dx: offset.dx, dy: offset.dy,
    rotation: payload?.rotation ?? moveRotation.value,
    scale: payload?.scale ?? moveScale.value,
    fillColor: moveFillColor.value,
  })
}

function onCancelMove() {
  canvasRef.value?.cancelMove?.()
  currentTool.value = 'box'
  moveStatusText.value = '마스킹을 먼저 해주세요'
}
function applyTextWm(params: any) { doOp('text_watermark', { ...params, clamp: wmClamp.value, color: wmTextColor.value }) }
function applyImageWm(params: any) {
  if (!wmImagePath.value) { requestAction('show_toast', { type: 'warning', msg: '먼저 워터마크 이미지를 불러오세요' }); return }
  doOp('image_watermark', { ...params, clamp: wmClamp.value, watermark_path: wmImagePath.value })
}
function loadWatermarkImage() { requestAction('editor_load_watermark_image') }

// DrawPanel은 {tool,color,size,opacity,filled} 객체를 보낸다. 예전에는 이 객체를
// currentTool 에 그대로 넣어서, EditorCanvas 의 문자열 비교(props.tool === 'box' 등)가
// 전부 어긋났다 — 그리기 탭이 죽는 것에 더해 선택 도구까지 함께 죽었다.
function onDrawToolChanged(p: any) {
  if (!p) return
  if (typeof p === 'string') { currentTool.value = p; return }
  drawParams.value = { ...drawParams.value, ...p }
  if (typeof p.tool === 'string') currentTool.value = p.tool
}

// 앱에 색상 선택 다이얼로그가 없다(QColorDialog 미사용). 브리지 왕복 없이
// 네이티브 컬러 입력을 띄운다. 실패하면 패널의 12색 팔레트가 그대로 대안이다.
function pickColor(target: 'draw' | 'gradient' | 'wmText') {
  const el = document.createElement('input')
  el.type = 'color'
  el.value = target === 'draw' ? drawParams.value.color : '#ffffff'
  el.style.position = 'fixed'; el.style.left = '-9999px'
  document.body.appendChild(el)
  el.addEventListener('change', () => {
    const v = el.value
    if (target === 'draw') { drawParams.value.color = v; drawPanelRef.value?.setColor?.(v) }
    else if (target === 'gradient') { drawGradientEnd.value = v }
    else { wmTextColor.value = v }
    el.remove()
  })
  el.addEventListener('cancel', () => el.remove())
  el.click()
}

// 마스크 영역을 인페인트로 넘긴다. 백엔드에 이미 send_to_inpaint 액션이 있다
// (generator_main.py: tabChanged → inpaintImageLoaded).
function onSendInpaint(_payload: any) {
  if (!imagePath.value) return
  requestAction('send_to_inpaint', { path: imagePath.value })
}

// 복원 브러시 — 칠한 자리를 주변 픽셀로 메운다(백엔드 inpaint).
// 레이어에 그리는 다른 도구와 달리 원본을 고치는 작업이라 확정 연산으로 나간다.
function applyHeal() {
  const mask = canvasRef.value?.getHealMaskBase64?.()
  if (!mask) {
    requestAction('show_toast', { type: 'info', msg: '복원할 자리를 먼저 칠하세요' })
    return
  }
  doOp('heal', { mask_base64: mask, radius: Math.max(1, Math.round(drawParams.value.size / 2)) })
  canvasRef.value?.clearHealMask?.()
}

/** 스포이트가 집은 색을 현재 색으로 되돌린다 — 패널 표시도 같이 맞춘다. */
function onEyedropperColor(hex: string) {
  drawParams.value = { ...drawParams.value, color: hex }
  drawPanelRef.value?.setColor?.(hex)
}

function undoDrawStroke() {
  if (!canvasRef.value?.undoDrawStroke?.()) {
    requestAction('show_toast', { type: 'info', msg: '되돌릴 획이 없습니다' })
  }
}

function clearDrawLayer() {
  canvasRef.value?.clearDrawLayer?.()
}
function onSelectionChanged(sel: any) { selection.value = sel }

// MovePanel 인페인트 버튼 활성 조건. canInpaint prop 자체가 전달되지 않아
// 기본값 false 로 영구 비활성이었다. 이 버튼은 이미지를 Inpaint 탭으로 넘기는
// 동작이므로(마스킹은 그 탭에서 한다) 이미지가 열려 있으면 충분하다.
const canInpaint = computed(() => !!imagePath.value)

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

// keep-alive로 에디터 뷰가 항상 mount된 상태(탭 워밍)라도, 전역 keydown 핸들러는
// 에디터 탭이 *활성*일 때만 동작해야 한다. (안 그러면 t2i 등에서 Ctrl+V/Z/Y/S/O를
// 에디터가 가로채 일반 붙여넣기/실행취소가 막힘 — 워밍 도입 후 회귀)
let _editorActive = false
onActivated(() => { _editorActive = true })
onDeactivated(() => { _editorActive = false })

function onEditorKeyDown(e: KeyboardEvent) {
  if (!_editorActive) return   // 에디터 탭이 아닐 땐 단축키 가로채지 않음
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
  if (e.key === 'Escape') {
    // 원근 보정 중이면 그것부터 취소 (마스크를 날리지 않게)
    if (perspectiveActive.value) { onCancelPerspective(); return }
    canvasRef.value?.clearSelection()
  }

  // 도구 단축키 (B=브러시, P=펜 …). 글자 하나짜리라 입력 중에는 절대 가로채면 안 된다
  // — 프롬프트나 텍스트 도구에 'b' 를 치는 순간 도구가 바뀌면 못 쓴다.
  const el = document.activeElement as HTMLElement | null
  const typing = !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
  // 원근 보정·영역 이동 중에는 도구를 갈아타면 진행 중인 조작이 날아간다
  if (!typing && !perspectiveActive.value && currentTool.value !== 'move') {
    const tool = toolByKey(e.key, { ctrl: e.ctrlKey, alt: e.altKey, meta: e.metaKey })
    if (tool) {
      e.preventDefault()
      selectTool(tool.id)
      requestAction('show_toast', { type: 'info', msg: `${tool.label} (${tool.shortcut})` })
      return
    }
  }
  // 원근 보정 중 Enter = 적용
  if (e.key === 'Enter' && perspectiveActive.value) {
    e.preventDefault()
    onConfirmPerspective()
  }
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
  onBackendEvent('editorWatermarkImageLoaded', (path: string) => { wmImagePath.value = path })
  onBackendEvent('yoloModelUpdated', (label: string) => { modelLabel.value = label })
  onBackendEvent('editorResult', onEditorResult)
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
