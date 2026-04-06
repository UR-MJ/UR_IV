<template>
  <div class="web-view">
    <div class="toolbar">
      <input class="url-input" v-model="url" placeholder="URL 입력..." @keydown.enter="navigate" />
      <button class="btn" @click="navigate">이동</button>
    </div>
    <iframe :src="currentUrl" class="web-frame" v-if="currentUrl" />
    <div class="placeholder" v-else>
      <h2>Web Browser</h2>
      <p>Danbooru 등 웹사이트 탐색</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const url = ref('https://danbooru.donmai.us/')
const currentUrl = ref('')

function navigate() {
  let u = url.value.trim()
  if (u && !u.startsWith('http')) u = 'https://' + u
  currentUrl.value = u
}
</script>

<style scoped>
.web-view { height: 100%; display: flex; flex-direction: column; }
.toolbar {
  display: flex; gap: 6px; padding: 6px 10px; border-bottom: 1px solid #1A1A1A;
}
.url-input {
  flex: 1; background: #131313; border: none; border-radius: 4px;
  padding: 6px 10px; color: #E8E8E8; font-size: 12px; outline: none;
}
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 4px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.web-frame { flex: 1; border: none; background: #fff; }
.placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; color: #484848;
}
.placeholder h2 { font-size: 20px; margin-bottom: 8px; color: #787878; }
</style>
