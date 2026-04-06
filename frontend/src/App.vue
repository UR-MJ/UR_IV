<template>
  <div class="app">
    <TabBar @tab-changed="onTabChanged" />
    <div class="main">
      <!-- 좌측 패널 (T2I만) -->
      <div class="left-panel" v-if="showLeftPanel">
        <PromptPanel />
        <!-- 도구 버튼 -->
        <div class="tools-section">
          <button class="tool-btn" @click="action('save_settings')">💾 저장</button>
          <button class="tool-btn" @click="action('save_preset')">📥 프리셋 저장</button>
          <button class="tool-btn" @click="action('load_preset')">📤 프리셋 로드</button>
          <button class="tool-btn" @click="action('show_prompt_history')">📋 히스토리</button>
          <button class="tool-btn" @click="action('open_lora_manager')">LoRA</button>
          <button class="tool-btn" @click="action('open_tag_weight_editor')">⚖ 가중치</button>
          <button class="tool-btn" @click="action('shuffle')">🔀 셔플</button>
          <button class="tool-btn" @click="action('ab_test')">A/B</button>
          <button class="tool-btn" @click="action('random_prompt')">🎲 랜덤</button>
        </div>
      </div>

      <!-- 중앙 콘텐츠 -->
      <div class="content">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component"
              :image-url="currentImage"
              :resolution="resolution"
              :seed="seed"
              :status="status"
            />
          </keep-alive>
        </router-view>
      </div>

      <!-- 우측 히스토리 (T2I만) -->
      <div class="right-panel" v-if="showLeftPanel">
        <div class="history-header">
          <span>히스토리</span>
          <span class="count">{{ historyImages.length }}</span>
        </div>
        <div class="history-list">
          <div v-for="img in historyImages" :key="img" class="hist-item"
            @click="action('display_image', { path: img })">
            <img :src="'file:///' + img" loading="lazy" />
          </div>
        </div>
      </div>
    </div>

    <!-- 하단 대기열 (고정) -->
    <QueuePanel />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { initBridge, onBackendEvent, getBackend } from './bridge.js'
import { requestAction } from './stores/widgetStore.js'
import PromptPanel from './components/PromptPanel.vue'
import TabBar from './components/TabBar.vue'
import QueuePanel from './components/QueuePanel.vue'

const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('이미지를 생성하세요')
const showLeftPanel = ref(true)
const historyImages = ref([])

function onTabChanged(tabName) {
  showLeftPanel.value = tabName === 't2i'
}

function action(name, payload = {}) {
  requestAction(name, payload)
}

async function loadHistory() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try { historyImages.value = JSON.parse(json).slice(0, 30) } catch {}
    })
  }
}

onMounted(async () => {
  await initBridge()
  loadHistory()

  onBackendEvent('imageGenerated', (data) => {
    const parsed = JSON.parse(data)
    currentImage.value = parsed.path
    resolution.value = `${parsed.width} × ${parsed.height}`
    seed.value = String(parsed.seed)
    status.value = ''
    // 히스토리에 추가
    if (parsed.path) {
      historyImages.value.unshift(parsed.path)
      if (historyImages.value.length > 30) historyImages.value.pop()
    }
  })
  onBackendEvent('generationStarted', () => { status.value = '생성 중...' })
  onBackendEvent('generationError', (msg) => { status.value = `오류: ${msg}` })
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0A0A0A; }
body {
  color: #E8E8E8;
  font-family: 'Pretendard', 'Malgun Gothic', 'Segoe UI', sans-serif;
}
.app { width: 100%; height: 100%; display: flex; flex-direction: column; }
.main { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.left-panel {
  width: 340px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
}
.tools-section {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 6px 8px;
  background: #0A0A0A; flex-shrink: 0;
}
.tool-btn {
  padding: 4px 10px; background: #181818; border: none; border-radius: 4px;
  color: #585858; font-size: 10px; cursor: pointer; white-space: nowrap;
}
.tool-btn:hover { background: #222; color: #E8E8E8; }
.content { flex: 1; overflow: hidden; min-width: 0; }
.right-panel {
  width: 180px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
}
.history-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 10px; flex-shrink: 0;
}
.history-header span { color: #585858; font-size: 11px; font-weight: 600; }
.count { color: #484848; }
.history-list { flex: 1; overflow-y: auto; padding: 4px; display: flex; flex-direction: column; gap: 4px; }
.hist-item { border-radius: 4px; overflow: hidden; cursor: pointer; flex-shrink: 0; }
.hist-item:hover { opacity: 0.8; }
.hist-item img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #E2B340; }
</style>
