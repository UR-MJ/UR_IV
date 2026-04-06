<template>
  <div class="history-panel">
    <div class="history-header">
      <span class="title">히스토리</span>
      <span class="count">{{ images.length }}장</span>
    </div>
    <div class="history-list">
      <div
        v-for="img in images"
        :key="img"
        class="history-item"
        @click="$emit('select', img)"
      >
        <img :src="'file:///' + img" loading="lazy" />
      </div>
      <div v-if="images.length === 0" class="empty">생성된 이미지가 없습니다</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'

defineEmits(['select'])
const images = ref([])

async function loadImages() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try { images.value = JSON.parse(json).slice(0, 50) } catch {}
    })
  }
}

onMounted(() => {
  loadImages()
  // 새 이미지 생성 시 자동 추가
  onBackendEvent('imageGenerated', (data) => {
    try {
      const parsed = JSON.parse(data)
      if (parsed.path) {
        images.value.unshift(parsed.path)
        if (images.value.length > 50) images.value.pop()
      }
    } catch {}
  })
})
</script>

<style scoped>
.history-panel {
  width: 200px;
  min-width: 160px;
  background: #0D0D0D;
  border-left: 1px solid #1A1A1A;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #1A1A1A;
}
.title { color: #787878; font-size: 12px; font-weight: 600; }
.count { color: #484848; font-size: 11px; }
.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.history-item {
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s;
  flex-shrink: 0;
}
.history-item:hover { border-color: #333; }
.history-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}
.empty {
  color: #383838;
  font-size: 11px;
  text-align: center;
  padding: 20px 8px;
}
</style>
