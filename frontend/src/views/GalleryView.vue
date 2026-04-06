<template>
  <div class="gallery-view">
    <div class="gallery-header">
      <h3>Gallery</h3>
      <button class="btn" @click="loadImages">새로고침</button>
      <span class="count">{{ images.length }}장</span>
    </div>
    <div class="gallery-grid">
      <div
        v-for="img in images"
        :key="img"
        class="gallery-item"
        @click="selectImage(img)"
        :class="{ selected: selected === img }"
      >
        <img :src="'file:///' + img" loading="lazy" />
      </div>
      <div v-if="images.length === 0" class="empty">이미지가 없습니다</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const images = ref([])
const selected = ref('')

async function loadImages() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try { images.value = JSON.parse(json) } catch {}
    })
  }
}

function selectImage(path) {
  selected.value = path
  requestAction('display_image', { path })
}

onMounted(loadImages)
</script>

<style scoped>
.gallery-view { height: 100%; display: flex; flex-direction: column; }
.gallery-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid #1A1A1A;
}
.gallery-header h3 { color: #E8E8E8; font-size: 14px; }
.count { color: #585858; font-size: 12px; }
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.gallery-grid {
  flex: 1; display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 4px; padding: 8px; overflow-y: auto; align-content: start;
}
.gallery-item {
  aspect-ratio: 1; border-radius: 4px; overflow: hidden;
  cursor: pointer; border: 2px solid transparent; transition: border-color 0.15s;
}
.gallery-item:hover { border-color: #333; }
.gallery-item.selected { border-color: #E2B340; }
.gallery-item img { width: 100%; height: 100%; object-fit: cover; }
.empty {
  grid-column: 1 / -1; text-align: center; color: #484848;
  padding: 60px; font-size: 14px;
}
</style>
