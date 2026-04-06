<template>
  <div class="app">
    <ImageViewer
      :image-url="currentImage"
      :resolution="resolution"
      :seed="seed"
      :status="status"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { initBridge, onBackendEvent } from './bridge.js'
import ImageViewer from './components/ImageViewer.vue'

const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('이미지를 생성하세요')

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
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
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

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #E2B340; }
</style>
