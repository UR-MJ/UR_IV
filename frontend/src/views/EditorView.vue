<template>
  <div class="editor-view"
    @dragover.prevent="isDragging = true"
    @dragleave="isDragging = false"
    @drop.prevent="onDrop"
  >
    <template v-if="imageSrc">
      <div class="editor-toolbar">
        <button class="tool-btn" v-for="t in tools" :key="t.id"
          :class="{ active: activeTool === t.id }"
          @click="activeTool = t.id"
        >{{ t.icon }} {{ t.label }}</button>
        <div class="spacer" />
        <button class="tool-btn" @click="requestAction('editor_save')">💾 저장</button>
        <button class="tool-btn" @click="imageSrc = ''">✕ 닫기</button>
      </div>
      <div class="editor-canvas">
        <img :src="imageSrc" class="edit-image" />
      </div>
    </template>
    <template v-else>
      <div class="drop-area" :class="{ dragging: isDragging }">
        <div class="drop-icon">🎨</div>
        <h2>Image Editor</h2>
        <p>이미지를 드래그앤드롭하여 편집을 시작하세요</p>
        <button class="open-btn" @click="openFile">파일 선택</button>
        <div class="features">
          <span v-for="f in tools" :key="f.id" class="feature-tag">{{ f.icon }} {{ f.label }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { onBackendEvent } from '../bridge.js'

const isDragging = ref(false)
const imageSrc = ref('')
const activeTool = ref('draw')

const tools = [
  { id: 'draw', icon: '🎨', label: '드로잉' },
  { id: 'crop', icon: '✂️', label: '크롭' },
  { id: 'mosaic', icon: '🔲', label: '모자이크' },
  { id: 'text', icon: '📝', label: '텍스트' },
  { id: 'color', icon: '🖌️', label: '색상 보정' },
  { id: 'perspective', icon: '📐', label: '원근' },
]

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    const reader = new FileReader()
    reader.onload = (ev) => { imageSrc.value = ev.target.result }
    reader.readAsDataURL(file)
    // Python에도 알림
    if (file.path) requestAction('editor_load_image', { path: file.path })
  }
}

function openFile() {
  requestAction('editor_open_file')
}

onMounted(() => {
  onBackendEvent('editorImageLoaded', (path) => {
    imageSrc.value = 'file:///' + path
  })
})
</script>

<style scoped>
.editor-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.drop-area {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  cursor: pointer; transition: background 0.2s;
}
.drop-area.dragging { background: #111; }
.drop-icon { font-size: 48px; opacity: 0.3; }
.drop-area h2 { color: #787878; font-size: 20px; }
.drop-area p { color: #484848; font-size: 13px; }
.open-btn {
  padding: 10px 24px; background: #E2B340; border: none; border-radius: 8px;
  color: #000; font-weight: 700; font-size: 14px; cursor: pointer; margin-top: 8px;
}
.open-btn:hover { background: #F0C850; }
.features {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; justify-content: center;
}
.feature-tag {
  padding: 6px 12px; background: #131313; border-radius: 6px;
  color: #585858; font-size: 11px;
}
.editor-toolbar {
  display: flex; gap: 4px; padding: 6px 8px; background: #0D0D0D; flex-shrink: 0;
}
.tool-btn {
  padding: 6px 12px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer; white-space: nowrap;
}
.tool-btn.active { background: #E2B340; color: #000; }
.tool-btn:hover { background: #222; color: #E8E8E8; }
.spacer { flex: 1; }
.editor-canvas {
  flex: 1; display: flex; align-items: center; justify-content: center;
  overflow: hidden; padding: 8px;
}
.edit-image { max-width: 100%; max-height: 100%; object-fit: contain; }
</style>
