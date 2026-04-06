<template>
  <div class="tab-view">
    <div class="favorites-container">
      <div class="favorites-header">
        <h2>Favorites</h2>
        <button class="btn-refresh" @click="loadFavorites">
          <span class="btn-icon">&#x21bb;</span> 새로고침
        </button>
      </div>

      <div v-if="loading" class="status-message">불러오는 중...</div>
      <div v-else-if="!favorites.length" class="status-message">즐겨찾기가 없습니다</div>

      <div v-else class="image-grid">
        <div
          v-for="(path, idx) in favorites"
          :key="idx"
          class="grid-item"
          @click="displayImage(path)"
        >
          <img :src="'file:///' + path.replace(/\\\\/g, '/')" :alt="path" loading="lazy" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const favorites = ref([])
const loading = ref(false)

async function loadFavorites() {
  loading.value = true
  try {
    const backend = getBackend()
    const result = await backend.getFavorites()
    favorites.value = JSON.parse(result)
  } catch (e) {
    console.error('Failed to load favorites:', e)
    favorites.value = []
  } finally {
    loading.value = false
  }
}

function displayImage(path) {
  requestAction('display_image', { path })
}

onMounted(() => {
  loadFavorites()
})
</script>

<style scoped>
.tab-view {
  width: 100%;
  height: 100%;
  background: #0A0A0A;
  color: #E8E8E8;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.favorites-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  gap: 12px;
}
.favorites-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.favorites-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #E8E8E8;
  margin: 0;
}
.btn-refresh {
  background: transparent;
  border: 1px solid #1A1A1A;
  color: #E2B340;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}
.btn-refresh:hover {
  background: #1A1A1A;
}
.btn-icon {
  font-size: 14px;
}
.status-message {
  color: #585858;
  font-size: 13px;
  text-align: center;
  padding-top: 60px;
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}
.grid-item {
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 4px;
  border: 1px solid #1A1A1A;
  cursor: pointer;
  transition: border-color 0.15s;
}
.grid-item:hover {
  border-color: #E2B340;
}
.grid-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
</style>
