<template>
  <div class="fav-view">
    <div class="fav-header">
      <h3>Favorites</h3>
      <button class="btn" @click="loadFavorites">🔄 새로고침</button>
      <span class="count">{{ favorites.length }}장</span>
    </div>
    <div class="fav-grid">
      <div v-for="(img, i) in favorites" :key="img" class="fav-item"
        @click="viewImage(img)"
        @contextmenu.prevent="showMenu($event, img, i)"
      >
        <img :src="'file:///' + img" loading="lazy" />
      </div>
      <div v-if="favorites.length === 0" class="empty">즐겨찾기가 없습니다</div>
    </div>

    <!-- 우클릭 메뉴 -->
    <div v-if="ctxMenu.show" class="ctx-menu" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
      <div class="ctx-item" @click="ctx('display_image')">🖼️ 뷰어로 보기</div>
      <div class="ctx-item" @click="ctx('send_to_i2i')">🖼️ I2I로 보내기</div>
      <div class="ctx-item" @click="ctx('send_to_inpaint')">🎨 Inpaint</div>
      <div class="ctx-item" @click="ctx('send_to_editor')">✏️ Editor</div>
      <div class="ctx-item" @click="ctx('copy_to_clipboard')">📋 복사</div>
      <div class="ctx-item delete" @click="removeFav">⭐ 즐겨찾기 제거</div>
    </div>

    <!-- EXIF 패널 -->
    <div v-if="exifData" class="exif-panel">
      <div class="exif-bar">
        <span>{{ exifData.filename }}</span>
        <button class="btn-sm" @click="exifData = null">✕</button>
      </div>
      <div class="exif-content">
        <img :src="'file:///' + exifData.path" class="exif-img" />
        <div class="exif-text">
          <pre v-if="exifData.prompt">{{ exifData.prompt }}</pre>
          <pre v-else-if="exifData.raw">{{ exifData.raw }}</pre>
          <p v-else>메타데이터 없음</p>
          <div class="exif-btns">
            <button class="btn" @click="action('gallery_send_exif_to_t2i', { exif: exifData.raw, path: exifData.path })">📤 T2I</button>
            <button class="btn" @click="action('send_to_i2i', { path: exifData.path })">I2I</button>
            <button class="btn" @click="action('send_to_inpaint', { path: exifData.path })">Inpaint</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const favorites = ref([])
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '', index: -1 })
const exifData = ref(null)

async function loadFavorites() {
  const backend = await getBackend()
  if (backend.getFavorites) {
    backend.getFavorites((json) => {
      try { favorites.value = JSON.parse(json) } catch {}
    })
  }
}

async function viewImage(path) {
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => {
      try { exifData.value = JSON.parse(json) } catch {}
    })
  }
}

function showMenu(e, path, i) {
  let x = e.clientX, y = e.clientY
  if (x + 200 > window.innerWidth) x = window.innerWidth - 210
  if (y + 250 > window.innerHeight) y = window.innerHeight - 260
  ctxMenu.value = { show: true, x, y, path, index: i }
}

function ctx(actionName) {
  requestAction(actionName, { path: ctxMenu.value.path })
  ctxMenu.value.show = false
}

function removeFav() {
  const path = ctxMenu.value.path
  favorites.value = favorites.value.filter(f => f !== path)
  // Python에서 파일 업데이트
  requestAction('remove_favorite', { path })
  ctxMenu.value.show = false
}

function action(name, payload = {}) { requestAction(name, payload) }

function hideMenu() { ctxMenu.value.show = false }
onMounted(() => {
  document.addEventListener('click', hideMenu)
  loadFavorites()
})
onUnmounted(() => document.removeEventListener('click', hideMenu))
</script>

<style scoped>
.fav-view { width: 100%; height: 100%; display: flex; flex-direction: column; position: relative; }
.fav-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; flex-shrink: 0; }
.fav-header h3 { color: #E8E8E8; font-size: 14px; margin: 0; }
.count { color: #585858; font-size: 12px; }
.btn { padding: 5px 12px; background: #181818; border: none; border-radius: 4px; color: #787878; font-size: 11px; cursor: pointer; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn-sm { padding: 2px 8px; background: none; border: none; color: #585858; cursor: pointer; }
.fav-grid {
  flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 6px; padding: 8px; overflow-y: auto; align-content: start;
}
.fav-item { height: 150px; border-radius: 4px; overflow: hidden; cursor: pointer; border: 2px solid transparent; }
.fav-item:hover { border-color: #E2B340; }
.fav-item img { width: 100%; height: 100%; object-fit: cover; }
.empty { grid-column: 1 / -1; text-align: center; color: #484848; padding: 60px; }
.ctx-menu { position: fixed; background: #1A1A1A; border-radius: 6px; padding: 4px; z-index: 9999; min-width: 170px; box-shadow: 0 4px 16px rgba(0,0,0,0.7); }
.ctx-item { padding: 7px 14px; font-size: 12px; color: #B0B0B0; cursor: pointer; border-radius: 4px; }
.ctx-item:hover { background: #222; color: #E8E8E8; }
.ctx-item.delete { color: #E2B340; }
.exif-panel { position: absolute; bottom: 0; left: 0; right: 0; max-height: 45%; background: #0D0D0D; display: flex; flex-direction: column; }
.exif-bar { display: flex; justify-content: space-between; padding: 6px 12px; }
.exif-bar span { color: #787878; font-size: 12px; }
.exif-content { flex: 1; display: flex; overflow: hidden; padding: 0 8px 8px; }
.exif-img { width: 150px; object-fit: contain; border-radius: 4px; flex-shrink: 0; }
.exif-text { flex: 1; overflow-y: auto; padding: 0 8px; }
.exif-text pre { color: #B0B0B0; font-size: 11px; white-space: pre-wrap; word-break: break-all; margin: 0; }
.exif-btns { display: flex; gap: 4px; margin-top: 8px; }
</style>
