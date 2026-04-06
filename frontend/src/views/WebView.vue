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

<script setup>
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const url = ref('https://danbooru.donmai.us/')

function openUrl() { open(url.value) }
function openDanbooru() { open('https://danbooru.donmai.us/') }
function open(u) {
  let target = u.trim()
  if (target && !target.startsWith('http')) target = 'https://' + target
  requestAction('open_url', { url: target })
}
</script>

<style scoped>
.web-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.toolbar { display: flex; gap: 6px; padding: 8px 12px; }
.url-input {
  flex: 1; background: #131313; border: none; border-radius: 6px;
  padding: 8px 12px; color: #E8E8E8; font-size: 13px; outline: none;
}
.url-input:focus { background: #1A1A1A; }
.btn {
  padding: 8px 16px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer; white-space: nowrap;
}
.btn:hover { background: #222; color: #E8E8E8; }
.info {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: #585858; font-size: 13px; text-align: center;
}
.quick-links { display: flex; gap: 8px; margin-top: 12px; }
.link-btn {
  padding: 10px 20px; background: #181818; border: none; border-radius: 6px;
  color: #E2B340; font-size: 13px; font-weight: 600; cursor: pointer;
}
.link-btn:hover { background: #222; }
</style>
