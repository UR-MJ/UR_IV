<template>
  <div class="web-view">
    <div class="toolbar">
      <input class="url-input" v-model="url" placeholder="URL 입력..." @keydown.enter="openUrl" />
      <button class="btn" @click="openUrl">열기</button>
      <button class="btn" @click="openDanbooru">Danbooru</button>
    </div>
    <div class="info">
      <p>QWebEngineView 내부에서 iframe은 보안 정책으로 차단됩니다.</p>
      <p>"열기" 버튼을 누르면 시스템 기본 브라우저에서 열립니다.</p>
      <div class="quick-links">
        <button class="link-btn" @click="open('https://danbooru.donmai.us/')">Danbooru</button>
        <button class="link-btn" @click="open('https://hijiribe.donmai.us/')">Hijiribe</button>
        <button class="link-btn" @click="open('https://civitai.com/')">CivitAI</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const url = ref('https://danbooru.donmai.us/')

function openUrl() { open(url.value) }
function openDanbooru() { open('https://danbooru.donmai.us/') }
function open(u: string) {
  let target = u.trim()
  if (target && !target.startsWith('http')) target = 'https://' + target
  requestAction('open_url', { url: target })
}
</script>

<style scoped>
.web-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.toolbar { display: flex; gap: 6px; padding: 8px 12px; }
.url-input {
  flex: 1; background: var(--bg-input); border: none; border-radius: 6px;
  padding: 8px 12px; color: var(--text-primary); font-size: 13px; outline: none;
}
/* 포커스는 면을 한 단계 들어 올려 표시한다 — 라이트에서도 같은 방향이 되도록 토큰으로 */
.url-input:focus { background: var(--bg-card); }
.btn {
  padding: 8px 16px; background: var(--bg-button); border: none; border-radius: 6px;
  color: var(--text-muted); font-size: 12px; cursor: pointer; white-space: nowrap;
}
.btn:hover { background: var(--bg-button-hover); color: var(--text-primary); }
.info {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: var(--text-muted); font-size: 13px; text-align: center;
}
.quick-links { display: flex; gap: 8px; margin-top: 12px; }
.link-btn {
  padding: 10px 20px; background: var(--bg-button); border: none; border-radius: 6px;
  color: var(--accent); font-size: 13px; font-weight: var(--fw-bold); cursor: pointer;
}
.link-btn:hover { background: var(--bg-button-hover); }
</style>
