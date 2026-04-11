<template>
  <div class="tbf">
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
          <span class="wc-ico" v-if="isWc(tb.text)">🎲</span>
          <span class="tbf-text">{{ tb.text }}</span>
        </button>
      </template>
      <!-- 끝에 드롭 -->
      <div class="tbf-drop-marker" v-if="dropIdx === blocks.length"></div>
      <!-- 추가 입력 -->
      <input class="tbf-add" v-model="newTag" :placeholder="placeholder"
        @keydown.enter="addBlock" />
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  colorFn: { type: Function, default: () => '' },
  placeholder: { type: String, default: '추가...' },
})
const emit = defineEmits(['update:modelValue', 'open-wildcard'])

// 블록 데이터
const blocks = ref([])
const newTag = ref('')
const editIdx = ref(-1)
const editText = ref('')
const editInputRef = ref(null)
const draggingFrom = ref(-1)
const dropIdx = ref(-1)

// 초기화 + 동기화
function parseText(text) {
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

watch(() => props.modelValue, (v) => {
  const newBlocks = parseText(v)
  const offSet = new Set(blocks.value.filter(b => b.off).map(b => b.text))
  blocks.value = newBlocks.map(b => ({ ...b, off: offSet.has(b.text) }))
}, { immediate: true })

// 블록 조작
function toggleBlock(idx) {
  blocks.value[idx].off = !blocks.value[idx].off
  syncToModel()
}

function removeBlock(idx) {
  blocks.value.splice(idx, 1)
  syncToModel()
}

function addBlock() {
  const tag = newTag.value.trim()
  if (tag) { blocks.value.push({ text: tag, off: false }); newTag.value = ''; syncToModel() }
}

function startEdit(idx) {
  if (isWc(blocks.value[idx].text)) { emit('open-wildcard', blocks.value[idx].text.match(/__(.+?)__/)?.[1]); return }
  editIdx.value = idx
  editText.value = blocks.value[idx].text
  nextTick(() => { if (editInputRef.value?.[0]) editInputRef.value[0].focus() })
}

function finishEdit(idx) {
  if (editIdx.value !== idx) return
  const t = editText.value.trim()
  if (t) blocks.value[idx].text = t
  else blocks.value.splice(idx, 1)
  editIdx.value = -1
  syncToModel()
}

// 드래그
function onDragStart(idx) { draggingFrom.value = idx }
function onDragOver(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const children = e.currentTarget.children
  let closest = blocks.value.length
  for (let i = 0; i < children.length; i++) {
    const child = children[i]
    if (!child.classList.contains('tbf-block') && !child.classList.contains('tbf-edit')) continue
    const box = child.getBoundingClientRect()
    if (e.clientX < box.left + box.width / 2) { closest = Math.min(closest, parseInt(child.dataset?.idx || i)); break }
  }
  dropIdx.value = closest
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

function colorClass(text) { return props.colorFn(text) }
function isWc(text) { return /__.+__/.test(text) }
</script>

<style scoped>
.tbf { border: 1px solid var(--border); border-radius: var(--radius-base); padding: 6px; background: var(--bg-input); min-height: 36px; }
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
.tbf-drop-marker { width: 3px; height: 22px; background: var(--accent); border-radius: 2px; flex-shrink: 0; }
/* 편집 */
.tbf-edit { padding: 3px 8px; font-size: 11px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 4px; color: var(--text-primary); width: 120px; }
/* 추가 */
.tbf-add { padding: 3px 8px; font-size: 10px; background: transparent; border: 1px dashed var(--border); border-radius: 4px; color: var(--text-muted); width: 80px; min-width: 60px; }
.tbf-add:focus { border-color: var(--accent); color: var(--text-primary); width: 140px; }
/* neg */
.neg .tbf-block { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
</style>
