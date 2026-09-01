<template>
  <div class="tbf">
    <!-- 모두 비우기 버튼: 평소 왼쪽으로 반달처럼 살짝 튀어나옴, hover 시 원형+X -->
    <button v-if="blocks.length > 0"
      class="tbf-clear-all"
      @click.stop="clearAllBlocks"
      :title="`블록 ${blocks.length}개 모두 비우기 (Ctrl+Z로 복구 가능)`">
      <span class="tbf-clear-x"><Icon name="close" /></span>
    </button>
    <div class="tbf-blocks" @dragover.prevent="onDragOver" @drop="onDrop" @dragleave="dropIdx = -1">
      <template v-for="(tb, ti) in blocks" :key="ti">
        <!-- 드롭 위치 미리보기 -->
        <div class="tbf-drop-marker" v-if="dropIdx === ti && draggingFrom !== ti"></div>
        <!-- 편집 모드 -->
        <input v-if="editIdx === ti" class="tbf-edit" v-model="editText"
          @blur="finishEdit(ti)" @keydown.enter="finishEdit(ti)" @keydown.escape="editIdx = -1"
          ref="editInputRef" />
        <!-- 블록 -->
        <button v-else class="tbf-block" draggable="true"
          :class="[colorClass(tb.text), { disabled: tb.off, wildcard: isWc(tb.text) }]"
          @click.exact="startEdit(ti)"
          @dblclick="toggleBlock(ti)"
          @contextmenu.prevent="removeBlock(ti)"
          @dragstart="onDragStart(ti)" @dragend="draggingFrom = -1">
          <span class="wc-ico" v-if="isWc(tb.text)"><Icon name="dice" /></span>
          <span class="tbf-text">{{ tb.text }}</span>
        </button>
      </template>
      <!-- 끝에 드롭 -->
      <div class="tbf-drop-marker" v-if="dropIdx === blocks.length"></div>
      <!-- 추가 입력 -->
      <div class="tbf-add-wrap">
        <input class="tbf-add" v-model="newTag" :placeholder="placeholder"
          @input="onAddInput"
          @keydown="onAddKey"
          @blur="acItems = []" />
        <div class="ac-popup-block" v-if="acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item"
            :class="{ selected: acIdx === i }"
            @mousedown.prevent="acceptSuggestion(tag)">{{ tag.replace(/_/g, ' ') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { getBackend } from '../bridge.js'

interface TagBlock {
  text: string
  off: boolean
}

const props = withDefaults(defineProps<{
  modelValue?: string
  colorFn?: (text: string) => string
  placeholder?: string
}>(), {
  modelValue: '',
  colorFn: () => '',
  placeholder: '추가...',
})
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'open-wildcard': [name: string | undefined]
}>()

// 블록 데이터
const blocks = ref<TagBlock[]>([])
const newTag = ref('')
const editIdx = ref(-1)
const editText = ref('')
const editInputRef = ref<HTMLInputElement[] | null>(null)
const draggingFrom = ref(-1)
const dropIdx = ref(-1)

// 초기화 + 동기화
function parseText(text: string): TagBlock[] {
  if (!text) return []
  let depth = 0; let p = ''
  for (const ch of text) {
    if ('([{'.includes(ch)) depth++
    else if (')]}'.includes(ch)) depth = Math.max(0, depth - 1)
    p += (ch === ',' && depth > 0) ? '\x01' : ch
  }
  p = p.replace(/__([^_]+)__/g, m => m.replace(/,/g, '\x01'))
  return p.split(',').map(t => t.trim().replace(/\x01/g, ',')).filter(Boolean).map(t => ({ text: t, off: false }))
}

function syncToModel() {
  emit('update:modelValue', blocks.value.filter(b => !b.off).map(b => b.text).join(', '))
}

watch(() => props.modelValue, (v: string) => {
  const newBlocks = parseText(v)
  const offSet = new Set(blocks.value.filter(b => b.off).map(b => b.text))
  blocks.value = newBlocks.map(b => ({ ...b, off: offSet.has(b.text) }))
}, { immediate: true })

// 블록 조작
function toggleBlock(idx: number) {
  blocks.value[idx].off = !blocks.value[idx].off
  syncToModel()
}

function clearAllBlocks() {
  // 전체 블록 삭제 — Ctrl+Z로 복구 가능 (PromptPanel의 undoStack이 widget 변경 추적)
  blocks.value = []
  editIdx.value = -1
  newTag.value = ''
  acItems.value = []
  syncToModel()
}

function removeBlock(idx: number) {
  blocks.value.splice(idx, 1)
  syncToModel()
}

function addBlock() {
  const tag = newTag.value.trim()
  if (tag) { blocks.value.push({ text: tag, off: false }); newTag.value = ''; syncToModel() }
}

function startEdit(idx: number) {
  if (isWc(blocks.value[idx].text)) { emit('open-wildcard', blocks.value[idx].text.match(/__(.+?)__/)?.[1]); return }
  editIdx.value = idx
  editText.value = blocks.value[idx].text
  nextTick(() => { if (editInputRef.value?.[0]) editInputRef.value[0].focus() })
}

function finishEdit(idx: number) {
  if (editIdx.value !== idx) return
  const t = editText.value.trim()
  if (t) blocks.value[idx].text = t
  else blocks.value.splice(idx, 1)
  editIdx.value = -1
  syncToModel()
}

// 자동완성 (블록 모드)
const acItems = ref<string[]>([])
const acIdx = ref(0)
let acTimer: ReturnType<typeof setTimeout> | null = null

function onAddInput() {
  const prefix = newTag.value.trim()
  if (prefix.length < 2) { acItems.value = []; return }
  if (acTimer) clearTimeout(acTimer)
  acTimer = setTimeout(async () => {
    try {
      const backend: any = await getBackend()
      if (backend.getTagSuggestions) {
        backend.getTagSuggestions(prefix, (json: string) => {
          try {
            const arr = JSON.parse(json)
            acItems.value = Array.isArray(arr) ? arr.slice(0, 10) : []
            acIdx.value = 0
          } catch { acItems.value = [] }
        })
      }
    } catch { acItems.value = [] }
  }, 250)
}

function onAddKey(e: KeyboardEvent) {
  // 자동완성 활성일 때 키 처리
  if (acItems.value.length > 0) {
    if (e.key === 'ArrowDown') { e.preventDefault(); acIdx.value = Math.min(acIdx.value + 1, acItems.value.length - 1); return }
    if (e.key === 'ArrowUp')   { e.preventDefault(); acIdx.value = Math.max(0, acIdx.value - 1); return }
    if (e.key === 'Tab')       { e.preventDefault(); acceptSuggestion(acItems.value[acIdx.value]); return }
    if (e.key === 'Escape')    { acItems.value = []; return }
    // Enter는 자동완성 항목 선택 (위쪽으로 이동 안 했어도 첫 번째 선택)
    if (e.key === 'Enter')     { e.preventDefault(); acceptSuggestion(acItems.value[acIdx.value]); return }
  }
  // 자동완성 없으면 기존 addBlock 동작
  if (e.key === 'Enter') addBlock()
}

function acceptSuggestion(tag: string) {
  if (!tag) return
  newTag.value = tag.replace(/_/g, ' ')  // 표시는 공백으로
  acItems.value = []
  addBlock()
}

// 드래그 — 다중 행(wrap) 인식 + 행 내 X 기준 위치 판정
function onDragStart(idx: number) { draggingFrom.value = idx }
function onDragOver(e: DragEvent) {
  const container = e.currentTarget as HTMLElement
  // 실제 블록만 추출 (드롭 마커/입력 칸 제외)
  const els = Array.from(container.querySelectorAll('.tbf-block, .tbf-edit'))
  if (els.length === 0) { dropIdx.value = 0; return }

  const cx = e.clientX
  const cy = e.clientY

  // 각 블록의 위치/크기 수집
  const items = els.map((el, i) => {
    const box = el.getBoundingClientRect()
    return {
      idx: i,
      top: box.top,
      bottom: box.bottom,
      left: box.left,
      mid: box.left + box.width / 2,
      yCenter: (box.top + box.bottom) / 2,
    }
  })

  // 1) 커서 Y가 어느 행에 있는지 판정 — 행 Y 범위에 직접 들어있으면 그 행
  let inRow = items.filter(c => cy >= c.top && cy <= c.bottom)

  if (inRow.length === 0) {
    // 행 사이/위/아래에 있으면 가장 가까운 행 사용
    let closestY = items[0].yCenter
    let minDist = Math.abs(cy - closestY)
    for (const c of items) {
      const d = Math.abs(cy - c.yCenter)
      if (d < minDist) { minDist = d; closestY = c.yCenter }
    }
    // 그 yCenter와 비슷한 모든 항목 = 같은 행 (행 높이는 보통 ~30px이므로 8px 허용)
    inRow = items.filter(c => Math.abs(c.yCenter - closestY) < 8)
  }

  if (inRow.length === 0) {
    dropIdx.value = items.length
    return
  }

  // 2) 행 내에서 X 기준으로 삽입 위치 결정
  //    커서가 어떤 블록의 좌측 절반에 있으면 그 블록 앞,
  //    모두 통과(우측)하면 행의 마지막 블록 뒤
  let dropAt = inRow[inRow.length - 1].idx + 1
  for (const c of inRow) {
    if (cx < c.mid) {
      dropAt = c.idx
      break
    }
  }

  // 자기 자신 위에서는 마커 안 보이게 (시각적 안정)
  if (dropAt === draggingFrom.value || dropAt === draggingFrom.value + 1) {
    dropIdx.value = -1
  } else {
    dropIdx.value = dropAt
  }
}
function onDrop() {
  if (draggingFrom.value >= 0 && dropIdx.value >= 0 && draggingFrom.value !== dropIdx.value) {
    const [item] = blocks.value.splice(draggingFrom.value, 1)
    const target = dropIdx.value > draggingFrom.value ? dropIdx.value - 1 : dropIdx.value
    blocks.value.splice(target, 0, item)
    syncToModel()
  }
  draggingFrom.value = -1; dropIdx.value = -1
}

function colorClass(text: string) { return props.colorFn(text) }
function isWc(text: string) { return /__.+__/.test(text) }
</script>

<style scoped>
.tbf { position: relative; border: 1px solid var(--border); border-radius: var(--radius-base); padding: 6px; background: var(--bg-input); min-height: 36px; }

/* 모두 비우기 버튼 — 평소엔 반달, hover 시 원형 X */
.tbf-clear-all {
  position: absolute;
  left: -10px;             /* 왼쪽으로 튀어나오게 */
  top: 50%;
  transform: translateY(-50%);
  width: 14px;
  height: 28px;
  padding: 0;
  border: 1px solid rgba(248, 113, 113, 0.4);
  border-right: none;       /* 필드 경계와 매끄럽게 */
  border-radius: 50% 0 0 50%;  /* 반달 — 왼쪽이 둥글고 오른쪽이 직선 */
  background: rgba(248, 113, 113, 0.15);
  color: transparent;       /* X 숨김 */
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0;             /* 텍스트 안 보이게 */
  font-weight: bold;
  transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 10;
  overflow: hidden;
}
.tbf-clear-all:hover {
  left: -22px;              /* 더 튀어나오면서 */
  width: 26px;
  height: 26px;
  border-radius: 50%;       /* 원형 변형 */
  border: 1px solid #f87171;
  background: #f87171;
  color: #fff;
  font-size: 12px;
  box-shadow: 0 4px 14px rgba(248, 113, 113, 0.45), 0 0 0 2px rgba(248,113,113,0.15);
  overflow: visible;
}
.tbf-clear-all:active {
  transform: translateY(-50%) scale(0.9);
}
.tbf-clear-x {
  opacity: 0;
  transition: opacity 0.15s ease 0.05s;
}
.tbf-clear-all:hover .tbf-clear-x { opacity: 1; }
.tbf-blocks { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.tbf-block {
  padding: 3px 10px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: 11px; cursor: pointer;
  transition: all 0.12s; user-select: none; position: relative;
}
.tbf-block:hover { border-color: var(--text-muted); }
.tbf-block[draggable="true"] { cursor: grab; }
.tbf-block[draggable="true"]:active { cursor: grabbing; opacity: 0.5; }
.tbf-block.disabled { opacity: 0.35; }
.tbf-block.disabled .tbf-text { text-decoration: line-through; }
/* 색상 */
.tbf-block.bc-count { border-color: rgba(96,165,250,0.3); color: #60a5fa; }
.tbf-block.bc-nsfw { border-color: rgba(248,113,113,0.3); color: #f87171; }
.tbf-block.bc-body { border-color: rgba(251,146,60,0.3); color: #fb923c; }
.tbf-block.bc-clothing { border-color: rgba(167,139,250,0.3); color: #a78bfa; }
.tbf-block.bc-action { border-color: rgba(74,222,128,0.3); color: #4ade80; }
.tbf-block.bc-expression { border-color: rgba(251,191,36,0.3); color: #fbbf24; }
.tbf-block.bc-bg { border-color: rgba(56,189,248,0.3); color: #38bdf8; }
.tbf-block.bc-effect { border-color: rgba(192,132,252,0.3); color: #c084fc; }
.tbf-block.bc-objects { border-color: rgba(148,163,184,0.3); color: #94a3b8; }
.tbf-block.bc-color { border-color: rgba(244,114,182,0.3); color: #f472b6; }
.tbf-block.bc-trait { border-color: rgba(52,211,153,0.3); color: #34d399; }
.tbf-block.wc-block { border-color: rgba(250,204,21,0.4); background: rgba(250,204,21,0.08); color: var(--accent); border-style: dashed; }
.wc-ico { margin-right: 2px; font-size: 9px; }
/* 드롭 마커 */
.tbf-drop-marker {
  width: 4px; height: 24px; background: var(--accent); border-radius: 3px; flex-shrink: 0;
  box-shadow: 0 0 8px var(--accent), 0 0 4px var(--accent);
  animation: tbf-marker-pulse 0.8s ease-in-out infinite;
}
@keyframes tbf-marker-pulse {
  0%, 100% { opacity: 1; transform: scaleY(1); }
  50% { opacity: 0.6; transform: scaleY(0.85); }
}
/* 편집 */
.tbf-edit { padding: 3px 8px; font-size: 11px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 4px; color: var(--text-primary); width: 120px; }
/* 추가 */
.tbf-add-wrap { position: relative; display: inline-block; }
.tbf-add { padding: 3px 8px; font-size: 10px; background: transparent; border: 1px dashed var(--border); border-radius: 4px; color: var(--text-muted); width: 80px; min-width: 60px; }
.tbf-add:focus { border-color: var(--accent); color: var(--text-primary); width: 140px; }
.ac-popup-block {
  position: absolute; top: 100%; left: 0; z-index: 100;
  margin-top: 2px; min-width: 180px; max-height: 200px; overflow-y: auto;
  background: var(--bg-secondary); border: 1px solid var(--accent);
  border-radius: 6px; padding: 2px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
}
.ac-popup-block .ac-item {
  padding: 5px 10px; font-size: 11px; color: var(--text-primary);
  cursor: pointer; border-radius: 4px;
}
.ac-popup-block .ac-item:hover, .ac-popup-block .ac-item.selected {
  background: rgba(96,165,250,0.2); color: #93c5fd;
}
/* neg */
.neg .tbf-block { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
</style>
