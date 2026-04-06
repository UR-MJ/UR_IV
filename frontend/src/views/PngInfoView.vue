<template>
  <div class="pnginfo-view">
    <div class="drop-zone"
      @dragover.prevent
      @drop.prevent="onDrop"
      @click="openFile"
    >
      <template v-if="imagePath">
        <img :src="'file:///' + imagePath" class="preview-img" />
      </template>
      <template v-else>
        <div class="drop-hint">
          <div class="icon">📄</div>
          <div>이미지를 드래그하거나 클릭하여 선택</div>
        </div>
      </template>
    </div>
    <div class="info-panel">
      <div class="info-header">
        <h3>메타데이터</h3>
        <button class="btn" @click="copyInfo" v-if="infoText">복사</button>
      </div>
      <pre class="info-text" v-if="infoText">{{ infoText }}</pre>
      <div class="info-empty" v-else>메타데이터가 없습니다</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const imagePath = ref('')
const infoText = ref('')

async function loadInfo(path) {
  imagePath.value = path
  const backend = await getBackend()
  if (backend.getPngInfo) {
    backend.getPngInfo(path, (json) => {
      try {
        const data = JSON.parse(json)
        if (data.parameters) {
          infoText.value = data.parameters
        } else if (data.prompt) {
          infoText.value = JSON.stringify(JSON.parse(data.prompt), null, 2)
        } else if (data.error) {
          infoText.value = `오류: ${data.error}`
        } else {
          infoText.value = '메타데이터가 없습니다'
        }
      } catch {
        infoText.value = json
      }
    })
  }
}

function onDrop(e) {
  const files = e.dataTransfer?.files
  if (files?.length) {
    const path = files[0].path || files[0].name
    if (path) loadInfo(path.replace(/\\/g, '/'))
  }
}

function openFile() {
  requestAction('open_png_info_file')
}

function copyInfo() {
  navigator.clipboard?.writeText(infoText.value)
}
</script>

<style scoped>
.pnginfo-view {
  height: 100%; display: flex; gap: 0;
}
.drop-zone {
  flex: 1; display: flex; align-items: center; justify-content: center;
  border-right: 1px solid #1A1A1A; cursor: pointer;
  min-width: 300px;
}
.drop-hint {
  text-align: center; color: #484848; user-select: none;
}
.drop-hint .icon { font-size: 48px; opacity: 0.3; margin-bottom: 12px; }
.drop-hint div { font-size: 13px; }
.preview-img {
  max-width: 100%; max-height: 100%; object-fit: contain; padding: 16px;
}
.info-panel {
  flex: 1; display: flex; flex-direction: column; min-width: 300px;
}
.info-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid #1A1A1A;
}
.info-header h3 { color: #E8E8E8; font-size: 14px; }
.btn {
  padding: 4px 12px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.info-text {
  flex: 1; padding: 16px; overflow-y: auto; font-size: 12px;
  color: #B0B0B0; white-space: pre-wrap; word-break: break-all;
  font-family: 'Consolas', monospace; line-height: 1.6; margin: 0;
}
.info-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: #484848; font-size: 14px;
}
</style>
