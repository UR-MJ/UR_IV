<template>
  <div class="pnginfo-view">
    <!-- 좌측: 이미지 -->
    <div class="image-area"
      @dragover.prevent @drop.prevent="onDrop" @dblclick="openFile"
    >
      <img v-if="imagePath" :src="'file:///' + imagePath" class="preview-img" />
      <div v-else class="drop-hint">
        <div class="icon">📄</div>
        <div>이미지를 드래그하거나 더블클릭</div>
      </div>
    </div>

    <!-- 우측: 정보 + 버튼 -->
    <div class="info-panel">
      <div class="info-header">
        <h3>PNG Info</h3>
        <button class="btn" @click="openFile">📂 열기</button>
        <button class="btn" @click="copyAll" v-if="exif.raw">📋 복사</button>
      </div>

      <div class="info-body" v-if="exif.raw">
        <div v-if="exif.prompt" class="section">
          <label>Prompt</label>
          <pre>{{ exif.prompt }}</pre>
        </div>
        <div v-if="exif.negative" class="section">
          <label>Negative</label>
          <pre>{{ exif.negative }}</pre>
        </div>
        <div v-if="exif.params_line" class="section">
          <label>Parameters</label>
          <pre>{{ exif.params_line }}</pre>
        </div>
        <div v-if="!exif.prompt" class="section">
          <label>Raw</label>
          <pre>{{ exif.raw }}</pre>
        </div>

        <!-- 전송 버튼 -->
        <div class="action-bar">
          <button class="btn accent" @click="sendPrompt">📤 T2I에 프롬프트 전송</button>
          <button class="btn" @click="sendGenerate">⚡ 이 설정으로 즉시 생성</button>
          <button class="btn" @click="action('send_to_i2i', { path: imagePath })">🖼️ I2I</button>
          <button class="btn" @click="action('send_to_inpaint', { path: imagePath })">🎨 Inpaint</button>
          <button class="btn" @click="action('send_to_editor', { path: imagePath })">✏️ Editor</button>
          <button class="btn" @click="action('add_favorite', { path: imagePath })">⭐ 즐겨찾기</button>
        </div>
      </div>
      <div v-else class="info-empty">
        이미지를 선택하면 메타데이터가 표시됩니다
      </div>

      <div class="file-info" v-if="exif.filename">
        {{ exif.filename }} — {{ exif.size }} — {{ exif.filesize }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const imagePath = ref('')
const exif = ref({})

async function loadImage(path) {
  imagePath.value = path
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => {
      try { exif.value = JSON.parse(json) } catch {}
    })
  }
}

function onDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    const path = file.path || ''
    if (path) loadImage(path.replace(/\\/g, '/'))
  }
}

function openFile() { requestAction('open_png_info_file') }

function copyAll() {
  navigator.clipboard?.writeText(exif.value.raw || '')
}

function sendPrompt() {
  requestAction('pnginfo_send_prompt', {
    prompt: exif.value.prompt || '',
    negative: exif.value.negative || '',
  })
}

function sendGenerate() {
  requestAction('pnginfo_generate', exif.value)
}

function action(name, payload = {}) { requestAction(name, payload) }

onMounted(() => {
  onBackendEvent('inpaintImageLoaded', (path) => loadImage(path))
})
</script>

<style scoped>
.pnginfo-view { width: 100%; height: 100%; display: flex; }
.image-area {
  flex: 1; display: flex; align-items: center; justify-content: center;
  cursor: pointer; min-width: 300px; padding: 16px;
}
.preview-img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 4px; }
.drop-hint { text-align: center; color: #484848; user-select: none; }
.drop-hint .icon { font-size: 48px; opacity: 0.3; margin-bottom: 12px; }

.info-panel {
  width: 400px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden;
}
.info-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px; flex-shrink: 0;
}
.info-header h3 { color: #E8E8E8; font-size: 14px; margin: 0; flex: 1; }
.btn { padding: 5px 12px; background: #181818; border: none; border-radius: 4px; color: #787878; font-size: 11px; cursor: pointer; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn.accent { background: #E2B340; color: #000; }

.info-body { flex: 1; overflow-y: auto; padding: 8px 12px; }
.section { margin-bottom: 10px; }
.section label { color: #E2B340; font-size: 11px; font-weight: 600; display: block; margin-bottom: 2px; }
.section pre {
  color: #B0B0B0; font-size: 11px; white-space: pre-wrap; word-break: break-all;
  background: #111; padding: 6px 8px; border-radius: 4px; margin: 0; max-height: 150px; overflow-y: auto;
}
.action-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 12px; }
.info-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #484848; font-size: 14px; }
.file-info { padding: 6px 12px; color: #484848; font-size: 10px; flex-shrink: 0; }
</style>
