<template>
  <div class="backend-view">
    <div class="toolbar">
      <span class="label">Backend UI</span>
      <button class="btn" @click="action('show_api_manager')">백엔드 설정</button>
      <button class="btn" @click="reload">새로고침</button>
    </div>
    <iframe :src="backendUrl" class="backend-frame" v-if="backendUrl" ref="frameRef" />
    <div class="placeholder" v-else>
      <h2>Backend UI</h2>
      <p>백엔드(WebUI/ComfyUI)의 웹 인터페이스</p>
      <button class="btn-connect" @click="action('show_api_manager')">백엔드 연결</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { getBackend } from '../bridge.js'

const backendUrl = ref('')
const frameRef = ref(null)

function action(name) { requestAction(name) }
function reload() { if (frameRef.value) frameRef.value.src = backendUrl.value }

onMounted(async () => {
  const backend = await getBackend()
  if (backend.getSettings) {
    backend.getSettings((json) => {
      try {
        const s = JSON.parse(json)
        if (s.api_url) backendUrl.value = s.api_url
      } catch {}
    })
  }
})
</script>

<style scoped>
.backend-view { height: 100%; display: flex; flex-direction: column; }
.toolbar {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  border-bottom: 1px solid #1A1A1A;
}
.label { color: #787878; font-size: 12px; font-weight: 600; }
.btn {
  padding: 4px 12px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 11px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.backend-frame { flex: 1; border: none; }
.placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; color: #484848;
}
.placeholder h2 { font-size: 20px; margin-bottom: 8px; color: #787878; }
.placeholder p { font-size: 13px; margin-bottom: 16px; }
.btn-connect {
  padding: 10px 24px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer;
}
</style>
