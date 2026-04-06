<template>
  <div class="backend-view">
    <div class="toolbar">
      <span class="label">Backend UI</span>
      <button class="btn" @click="action('show_api_manager')">백엔드 설정</button>
      <button class="btn" @click="openInBrowser">브라우저에서 열기</button>
    </div>
    <div class="info">
      <p>백엔드 웹 UI는 시스템 브라우저에서 확인하세요.</p>
      <div class="url-display">{{ backendUrl }}</div>
      <button class="open-btn" @click="openInBrowser">
        {{ backendUrl }} 열기
      </button>
      <button class="open-btn secondary" @click="action('show_api_manager')">
        백엔드 연결 설정
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const backendUrl = ref('http://127.0.0.1:7860')

function action(name) { requestAction(name) }
function openInBrowser() {
  requestAction('open_url', { url: backendUrl.value })
}
</script>

<style scoped>
.backend-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.toolbar {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
}
.label { color: #787878; font-size: 13px; font-weight: 600; }
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.info {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px;
  color: #585858; font-size: 13px;
}
.url-display {
  font-family: 'Consolas', monospace; font-size: 15px; color: #E2B340;
  padding: 10px 20px; background: #131313; border-radius: 6px;
}
.open-btn {
  padding: 12px 32px; background: #E2B340; border: none; border-radius: 8px;
  color: #000; font-weight: 700; font-size: 14px; cursor: pointer;
}
.open-btn:hover { background: #F0C850; }
.open-btn.secondary { background: #181818; color: #787878; }
.open-btn.secondary:hover { background: #222; color: #E8E8E8; }
</style>
