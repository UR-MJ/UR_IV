<template>
  <div class="gallery-view">
    <!-- 상단 바 -->
    <div class="gallery-header">
      <h3>Gallery</h3>
      <button class="btn" @click="openFolder">📂 폴더 열기</button>
      <button class="btn" @click="loadImages">🔄 새로고침</button>
      <select class="sort-select" v-model="sortBy" @change="sortImages">
        <option value="date">날짜순</option>
        <option value="name">이름순</option>
        <option value="size">크기순</option>
      </select>
      <span class="count">{{ images.length }}장</span>
      <span class="folder-path" v-if="currentFolder">{{ currentFolder }}</span>
    </div>

    <!-- 이미지 그리드 -->
    <div class="gallery-grid">
      <div v-for="img in images" :key="img" class="gallery-item"
        @click="viewImage(img)"
        @contextmenu.prevent="showMenu($event, img)"
      >
        <img :src="'file:///' + img" loading="lazy" />
      </div>
      <div v-if="images.length === 0" class="empty">
        폴더를 선택하거나 이미지를 생성하세요
      </div>
    </div>

    <!-- 우클릭 메뉴 -->
    <div v-if="ctxMenu.show" class="ctx-menu" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
      <div class="ctx-item" @click="ctx('gallery_load_exif')">📋 EXIF 보기</div>
      <div class="ctx-item" @click="ctx('gallery_send_exif_to_t2i')">📤 EXIF → T2I 전송</div>
      <div class="ctx-item" @click="ctx('send_to_i2i')">🖼️ I2I로 보내기</div>
      <div class="ctx-item" @click="ctx('send_to_inpaint')">🎨 Inpaint로 보내기</div>
      <div class="ctx-item" @click="ctx('send_to_editor')">✏️ Editor로 보내기</div>
      <div class="ctx-item" @click="ctx('gallery_send_to_upscale')">🔍 Upscale로 보내기</div>
      <div class="ctx-item" @click="ctx('add_favorite')">⭐ 즐겨찾기 추가</div>
      <div class="ctx-item" @click="ctx('copy_to_clipboard')">📋 클립보드 복사</div>
      <div class="ctx-item delete" @click="ctx('delete_image')">🗑️ 삭제</div>
    </div>

    <!-- EXIF 뷰어 (하단 팝업) -->
    <div v-if="exifData" class="exif-panel">
      <div class="exif-header">
        <span>{{ exifData.filename }} — {{ exifData.size }}</span>
        <button class="btn-sm" @click="exifData = null">✕</button>
      </div>
      <div class="exif-body">
        <div class="exif-img">
          <img :src="'file:///' + exifData.path" />
        </div>
        <div class="exif-text">
          <div v-if="exifData.prompt" class="exif-section">
            <label>Prompt</label>
            <pre>{{ exifData.prompt }}</pre>
          </div>
          <div v-if="exifData.negative" class="exif-section">
            <label>Negative</label>
            <pre>{{ exifData.negative }}</pre>
          </div>
          <div v-if="exifData.params_line" class="exif-section">
            <label>Parameters</label>
            <pre>{{ exifData.params_line }}</pre>
          </div>
          <div v-if="!exifData.prompt && exifData.raw" class="exif-section">
            <label>Raw</label>
            <pre>{{ exifData.raw }}</pre>
          </div>
          <div class="exif-actions">
            <button class="btn" @click="sendExifToT2I">📤 T2I에 적용</button>
            <button class="btn" @click="action('send_to_i2i', { path: exifData.path })">🖼️ I2I</button>
            <button class="btn" @click="action('send_to_inpaint', { path: exifData.path })">🎨 Inpaint</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const images = ref([])
const currentFolder = ref('')
const sortBy = ref('date')
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const exifData = ref(null)

async function loadImages() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages(currentFolder.value, (json) => {
      try { images.value = JSON.parse(json) } catch {}
    })
  }
}

function sortImages() {
  // 정렬은 Python에서 이미 날짜순으로 반환하므로 클라이언트 정렬
  if (sortBy.value === 'name') {
    images.value.sort((a, b) => a.split('/').pop().localeCompare(b.split('/').pop()))
  } else if (sortBy.value === 'date') {
    loadImages() // 서버에서 날짜순 반환
  }
}

function openFolder() { requestAction('gallery_open_folder') }

async function viewImage(path) {
  // EXIF 로드 + 표시
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => {
      try { exifData.value = JSON.parse(json) } catch {}
    })
  }
}

function showMenu(e, path) {
  let x = e.clientX, y = e.clientY
  if (x + 200 > window.innerWidth) x = window.innerWidth - 210
  if (y + 300 > window.innerHeight) y = window.innerHeight - 310
  ctxMenu.value = { show: true, x, y, path }
}

function ctx(actionName) {
  requestAction(actionName, { path: ctxMenu.value.path })
  // EXIF 보기는 별도 처리
  if (actionName === 'gallery_load_exif') viewImage(ctxMenu.value.path)
  ctxMenu.value.show = false
}

function sendExifToT2I() {
  if (exifData.value) {
    requestAction('gallery_send_exif_to_t2i', {
      exif: exifData.value.raw || '',
      path: exifData.value.path,
    })
  }
}

function action(name, payload = {}) { requestAction(name, payload) }

function hideMenu() { ctxMenu.value.show = false }
onMounted(() => {
  document.addEventListener('click', hideMenu)
  loadImages()
  onBackendEvent('galleryFolderLoaded', (folder) => {
    currentFolder.value = folder
    loadImages()
  })
  onBackendEvent('exifLoaded', (json) => {
    try { exifData.value = JSON.parse(json) } catch {}
  })
})
onUnmounted(() => document.removeEventListener('click', hideMenu))
</script>

<style scoped>
.gallery-view { width: 100%; height: 100%; display: flex; flex-direction: column; position: relative; }
.gallery-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px; flex-shrink: 0;
}
.gallery-header h3 { color: #E8E8E8; font-size: 14px; margin: 0; }
.count { color: #585858; font-size: 12px; }
.folder-path { color: #484848; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; }
.btn { padding: 5px 12px; background: #181818; border: none; border-radius: 4px; color: #787878; font-size: 11px; cursor: pointer; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn-sm { padding: 2px 8px; background: none; border: none; color: #585858; cursor: pointer; font-size: 14px; }
.sort-select { background: #181818; border: none; border-radius: 4px; padding: 4px 8px; color: #787878; font-size: 11px; }

.gallery-grid {
  flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 6px; padding: 8px; overflow-y: auto; align-content: start;
}
.gallery-item {
  height: 150px; border-radius: 4px; overflow: hidden; cursor: pointer;
  border: 2px solid transparent; transition: border-color 0.15s;
}
.gallery-item:hover { border-color: #333; }
.gallery-item img { width: 100%; height: 100%; object-fit: cover; }
.empty { grid-column: 1 / -1; text-align: center; color: #484848; padding: 60px; font-size: 14px; }

/* 우클릭 메뉴 */
.ctx-menu {
  position: fixed; background: #1A1A1A; border-radius: 6px; padding: 4px;
  z-index: 9999; min-width: 180px; box-shadow: 0 4px 16px rgba(0,0,0,0.7);
}
.ctx-item { padding: 7px 14px; font-size: 12px; color: #B0B0B0; cursor: pointer; border-radius: 4px; }
.ctx-item:hover { background: #222; color: #E8E8E8; }
.ctx-item.delete { color: #E05252; }
.ctx-item.delete:hover { background: #2a1515; }

/* EXIF 패널 */
.exif-panel {
  position: absolute; bottom: 0; left: 0; right: 0;
  max-height: 50%; background: #0D0D0D; border-top: 1px solid #1A1A1A;
  display: flex; flex-direction: column; overflow: hidden;
}
.exif-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; flex-shrink: 0;
}
.exif-header span { color: #787878; font-size: 12px; }
.exif-body { flex: 1; display: flex; overflow: hidden; }
.exif-img { width: 200px; flex-shrink: 0; padding: 8px; }
.exif-img img { width: 100%; object-fit: contain; border-radius: 4px; }
.exif-text { flex: 1; overflow-y: auto; padding: 8px; }
.exif-section { margin-bottom: 8px; }
.exif-section label { color: #E2B340; font-size: 11px; font-weight: 600; display: block; margin-bottom: 2px; }
.exif-section pre {
  color: #B0B0B0; font-size: 11px; white-space: pre-wrap; word-break: break-all;
  background: #111; padding: 6px; border-radius: 4px; margin: 0;
}
.exif-actions { display: flex; gap: 6px; margin-top: 8px; }
</style>
