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

<script setup lang="ts">
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const backendUrl = ref('http://127.0.0.1:7860')

function action(name: string) { requestAction(name) }
function openInBrowser() {
  requestAction('open_url', { url: backendUrl.value })
}
</script>

<style scoped>
.backend-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.toolbar {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
}
.label { color: var(--text-muted); font-size: 13px; font-weight: var(--fw-bold); }
.btn {
  padding: 6px 14px; background: var(--bg-button); border: none; border-radius: 6px;
  color: var(--text-muted); font-size: 12px; cursor: pointer;
}
.btn:hover { background: var(--bg-button-hover); color: var(--text-primary); }
.info {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px;
  color: var(--text-muted); font-size: 13px;
}
.url-display {
  font-family: 'Consolas', monospace; font-size: 15px; color: var(--accent);
  padding: 10px 20px; background: var(--bg-secondary); border-radius: 6px;
}
/* 주 버튼이라 면은 --accent 가 아니라 --accent-fill 이다. 사용자가 고른 강조색이
   중간 밝기면 그 위 글자가 안 읽혀서, 면만 밀어 4.5:1 을 맞춘 값이 --accent-fill. */
.open-btn {
  padding: 12px 32px; background: var(--accent-fill); border: none; border-radius: 8px;
  color: var(--on-accent); font-weight: var(--fw-bold); font-size: 14px; cursor: pointer;
}
.open-btn:hover { background: var(--accent-fill-hover); }
.open-btn.secondary { background: var(--bg-button); color: var(--text-muted); }
.open-btn.secondary:hover { background: var(--bg-button-hover); color: var(--text-primary); }
</style>
