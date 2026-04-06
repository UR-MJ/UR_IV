<template>
  <div class="app">
    <!-- 좌측 패널 (T2I에서만 표시) -->
    <div class="left-panel" v-if="showLeftPanel">
      <PromptPanel />
    </div>

    <!-- 중앙 영역 -->
    <div class="center">
      <TabBar @tab-changed="onTabChanged" />
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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { initBridge, onBackendEvent } from './bridge.js'
import PromptPanel from './components/PromptPanel.vue'
import TabBar from './components/TabBar.vue'

const route = useRoute()
const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('이미지를 생성하세요')
const showLeftPanel = ref(true)

function onTabChanged(tabName) {
  showLeftPanel.value = tabName === 't2i'
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
}
.left-panel {
  width: 380px;
  min-width: 320px;
  height: 100vh;
  background: #0D0D0D;
  border-right: 1px solid #1A1A1A;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.center {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.content {
  flex: 1;
  overflow: hidden;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #E2B340; }
</style>
