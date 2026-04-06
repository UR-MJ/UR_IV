<template>
  <div class="app">
    <!-- 상단: 좌측 패널 | 중앙(탭바+콘텐츠) | 히스토리 -->
    <div class="upper">
      <!-- 좌측 패널 (T2I에서만 표시) -->
      <div class="left-panel" v-show="showLeftPanel">
        <PromptPanel />
      </div>

      <!-- 중앙 -->
      <div class="center">
        <TabBar @tab-changed="onTabChanged" />
        <div class="center-content">
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
      </div>

      <!-- 히스토리 -->
      <HistoryPanel @select="onHistorySelect" />
    </div>

    <!-- 하단: 대기열 -->
    <QueuePanel @add-current="onAddCurrentToQueue" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { initBridge, onBackendEvent } from './bridge.js'
import { requestAction } from './stores/widgetStore.js'
import PromptPanel from './components/PromptPanel.vue'
import TabBar from './components/TabBar.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import QueuePanel from './components/QueuePanel.vue'

const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('이미지를 생성하세요')
const showLeftPanel = ref(true)

function onTabChanged(tabName) {
  showLeftPanel.value = tabName === 't2i'
}

function onHistorySelect(path) {
  requestAction('display_image', { path })
}

function onAddCurrentToQueue() {
  requestAction('add_current_to_queue')
}

onMounted(async () => {
  await initBridge()

  onBackendEvent('imageGenerated', (data) => {
    const parsed = JSON.parse(data)
    currentImage.value = parsed.path
    resolution.value = `${parsed.width} × ${parsed.height}`
    seed.value = String(parsed.seed)
    status.value = ''
  })

  onBackendEvent('generationStarted', () => {
    status.value = '생성 중...'
  })

  onBackendEvent('generationError', (msg) => {
    status.value = `오류: ${msg}`
  })
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background-color: #0A0A0A;
  color: #E8E8E8;
  font-family: 'Pretendard', 'Malgun Gothic', 'Segoe UI', sans-serif;
  overflow: hidden;
}
.app {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
}
.upper {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.left-panel {
  width: 380px;
  min-width: 300px;
  background: #0D0D0D;
  border-right: 1px solid #1A1A1A;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.center {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}
.center-content {
  flex: 1;
  overflow: hidden;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #E2B340; }
</style>
