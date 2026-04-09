<template>
  <div class="gallery-workspace">
    <!-- Top Filter & Action Bar -->
    <header class="gallery-toolbar">
      <div class="folder-info" @click="openFolder">
        <span class="icon">📁</span>
        <span class="path">{{ currentFolder || 'Select Output Folder' }}</span>
      </div>
      
      <div class="spacer"></div>
      
      <div class="control-group">
        <button class="icon-btn" @click="loadImages(true)" title="Refresh (캐시 무시)">🔄</button>
        <div class="sep"></div>
        <div class="sort-chips">
          <button v-for="s in sortOptions" :key="s.val"
            class="mini-chip" :class="{ active: sortBy === s.val }"
            @click="sortBy = s.val; sortImages()"
          >{{ s.label }}</button>
        </div>
        <span class="count-badge">{{ images.length }} ITEMS</span>
      </div>
    </header>

    <!-- Masonry-style Grid -->
    <section class="gallery-content">
      <div class="masonry-grid">
        <div v-for="img in pagedImages" :key="img" class="gallery-card"
          @click="viewImage(img)"
          @contextmenu.prevent="showMenu($event, img)"
        >
          <img :src="'file:///' + img" loading="lazy" />
          <div class="card-hover-actions">
            <button class="tiny-btn" @click.stop="quickAction('add_favorite', img)">⭐</button>
            <button class="tiny-btn" @click.stop="quickAction('copy_to_clipboard', img)">📋</button>
          </div>
        </div>
      </div>
      <!-- 무한 스크롤 센티넬 -->
      <div ref="sentinelRef" class="sentinel" v-if="visibleCount < images.length"></div>
      <div class="load-more-info" v-if="visibleCount < images.length">
        {{ visibleCount }} / {{ images.length }} loaded
      </div>
      
      <div v-if="isLoading" class="empty-placeholder">
        <div class="spinner"></div>
        <p>Loading...</p>
      </div>
      <div v-else-if="images.length === 0" class="empty-placeholder">
        <div class="icon">🖼️</div>
        <h2>GALLERY IS EMPTY</h2>
        <p>No images found in the current directory</p>
      </div>
    </section>

    <!-- 이미지 확대 뷰 (풀스크린 오버레이) -->
    <transition name="fade">
      <div v-if="largeView" class="large-view-overlay" @click.self="largeView = null">
        <div class="large-view-panel">
          <div class="large-view-header">
            <span class="large-filename">{{ largeView.filename }}</span>
            <div class="large-actions">
              <button class="lv-btn" @click="editFilename">✏️ 이름 변경</button>
              <button class="lv-btn save" @click="saveExif">💾 EXIF 저장</button>
              <button class="lv-btn" @click="action('send_to_i2i', { path: largeView.path })">I2I</button>
              <button class="lv-btn" @click="action('send_to_inpaint', { path: largeView.path })">INPAINT</button>
              <button class="lv-btn" @click="action('send_to_editor', { path: largeView.path })">EDITOR</button>
              <button class="lv-btn accent" @click="sendExifToT2I">USE PROMPT</button>
              <button class="lv-close" @click="largeView = null">✕</button>
            </div>
          </div>
          <div class="large-view-body">
            <div class="large-img-area">
              <img :src="'file:///' + largeView.path + '?t=' + Date.now()" />
            </div>
            <div class="large-exif">
              <div class="meta-row"><span>SIZE</span><p>{{ largeView.size }}</p></div>
              <div v-if="largeView.prompt" class="meta-block">
                <label>PROMPT</label>
                <div class="code-box editable" contenteditable @blur="onExifEdit($event, 'prompt')">{{ largeView.prompt }}</div>
              </div>
              <div v-if="largeView.negative" class="meta-block mt-8">
                <label class="danger">NEGATIVE</label>
                <div class="code-box">{{ largeView.negative }}</div>
              </div>
              <div v-if="largeView.raw && !largeView.prompt" class="meta-block">
                <label>RAW</label>
                <div class="code-box">{{ largeView.raw }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Slide-out EXIF Panel (간단 사이드바 — 하위호환) -->
    <transition name="slide">
      <aside v-if="exifData && !largeView" class="exif-sidebar">
        <div class="exif-close" @click="exifData = null">➔</div>
        <div class="exif-content">
          <div class="exif-preview" @click="largeView = exifData">
            <img :src="'file:///' + exifData.path" />
            <div class="click-hint">클릭하여 확대</div>
          </div>
          <div class="exif-meta">
            <h3>METADATA</h3>
            <div class="meta-row"><span>FILE</span><p>{{ exifData.filename }}</p></div>
            <div class="meta-row"><span>SIZE</span><p>{{ exifData.size }}</p></div>

            <div v-if="exifData.prompt" class="meta-block">
              <label>PROMPT</label>
              <div class="code-box">{{ exifData.prompt }}</div>
            </div>
            <div v-if="exifData.negative" class="meta-block mt-12">
              <label class="danger">NEGATIVE</label>
              <div class="code-box">{{ exifData.negative }}</div>
            </div>
          </div>
          <div class="exif-footer">
            <button class="main-apply-btn" @click="sendExifToT2I">USE PROMPT IN T2I</button>
            <div class="grid-2 mt-8">
              <button class="mini-action" @click="action('send_to_i2i', { path: exifData.path })">I2I</button>
              <button class="mini-action" @click="action('send_to_inpaint', { path: exifData.path })">INPAINT</button>
            </div>
          </div>
        </div>
      </aside>
    </transition>

    <!-- Context Menu -->
    <transition name="pop">
      <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
        <div class="ctx-item" @click="ctx('gallery_load_exif')">📋 INSPECT EXIF</div>
        <div class="ctx-item" @click="ctx('send_to_i2i')">🖼️ SEND TO I2I</div>
        <div class="ctx-item" @click="ctx('send_to_inpaint')">🎨 SEND TO INPAINT</div>
        <div class="ctx-item" @click="ctx('send_to_editor')">✏️ SEND TO EDITOR</div>
        <div class="ctx-item" @click="sendToCompare('before')">🔍 COMPARE (BEFORE)</div>
        <div class="ctx-item" @click="sendToCompare('after')">🔍 COMPARE (AFTER)</div>
        <div class="ctx-separator"></div>
        <div class="ctx-item delete" @click="ctx('delete_image')">🗑️ DELETE FOREVER</div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

import { computed, nextTick } from 'vue'

const images = ref([])
const currentFolder = ref('')
const visibleCount = ref(40)
const sentinelRef = ref(null)
let observer = null

const pagedImages = computed(() => images.value.slice(0, visibleCount.value))
const sortBy = ref('date')
const sortOptions = [{label: 'DATE', val: 'date'}, {label: 'NAME', val: 'name'}]
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const exifData = ref(null)
const largeView = ref(null)
const isLoading = ref(false)

// ── 캐시 시스템 ──
const _cache = new Map()  // folder → { images, timestamp }
const CACHE_TTL = 5 * 60 * 1000  // 5분

async function editFilename() {
  if (!largeView.value) return
  const newName = window.prompt('파일 이름 변경:', largeView.value.filename)
  if (newName && newName !== largeView.value.filename) {
    const backend = await getBackend()
    if (backend.renameFile) {
      backend.renameFile(largeView.value.path, newName, (json) => {
        try {
          const r = JSON.parse(json)
          if (r.ok) { largeView.value.filename = newName; loadImages() }
          else alert(r.error || '이름 변경 실패')
        } catch {}
      })
    }
  }
}
function onExifEdit(e, field) {
  if (largeView.value) largeView.value[field] = e.target.textContent
}
async function saveExif() {
  if (!largeView.value) return
  const backend = await getBackend()
  if (!backend.saveImageExif) return
  // prompt + negative + raw 에서 A1111 형식으로 재구성
  const parts = []
  if (largeView.value.prompt) parts.push(largeView.value.prompt)
  if (largeView.value.negative) parts.push('Negative prompt: ' + largeView.value.negative)
  // raw에서 Steps: 이후 파라미터 라인 추출
  const rawMatch = (largeView.value.raw || '').match(/Steps:.*$/m)
  if (rawMatch) parts.push(rawMatch[0])
  const newParams = parts.join('\n')
  backend.saveImageExif(largeView.value.path, newParams, (json) => {
    try {
      const r = JSON.parse(json)
      if (r.ok) alert('EXIF 저장 완료')
      else alert(r.error || '저장 실패')
    } catch {}
  })
}

async function loadImages(forceRefresh = false) {
  const cacheKey = currentFolder.value || '__default__'

  // 캐시 히트 (5분 이내 + 강제 새로고침 아닌 경우)
  if (!forceRefresh && _cache.has(cacheKey)) {
    const cached = _cache.get(cacheKey)
    if (Date.now() - cached.timestamp < CACHE_TTL) {
      images.value = cached.images
      return
    }
  }

  isLoading.value = true
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages(currentFolder.value, (json) => {
      try {
        const list = JSON.parse(json)
        images.value = list
        // 캐시 저장
        _cache.set(cacheKey, { images: list, timestamp: Date.now() })
      } catch {}
      isLoading.value = false
    })
  } else {
    isLoading.value = false
  }
}

function sortImages() {
  if (sortBy.value === 'name') {
    images.value.sort((a, b) => a.split('/').pop().localeCompare(b.split('/').pop()))
  } else loadImages()
}

const openFolder = () => requestAction('gallery_open_folder')
const viewImage = async (path) => {
  const backend = await getBackend()
  if (backend.getImageExif) backend.getImageExif(path, (json) => {
    try {
      const d = JSON.parse(json)
      exifData.value = d
      largeView.value = d  // 클릭 시 바로 확대 뷰
    } catch {}
  })
}

function showMenu(e, path) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function ctx(actionName) {
  const path = ctxMenu.value.path
  requestAction(actionName, { path })
  if (actionName === 'gallery_load_exif') viewImage(path)
  // 삭제 시 즉시 목록에서 제거 (스크롤 유지)
  if (actionName === 'delete_image') {
    images.value = images.value.filter(img => img !== path)
    // 캐시도 업데이트
    const cacheKey = currentFolder.value || '__default__'
    if (_cache.has(cacheKey)) _cache.get(cacheKey).images = images.value
  }
  ctxMenu.value.show = false
}
const quickAction = (name, path) => requestAction(name, { path })
const sendToCompare = (slot) => { requestAction('send_to_compare', { path: ctxMenu.value.path, slot }); ctxMenu.value.show = false }
const sendExifToT2I = () => { if (exifData.value) requestAction('gallery_send_exif_to_t2i', { exif: exifData.value.raw || '', path: exifData.value.path }) }
const action = (name, payload = {}) => requestAction(name, payload)
const hideMenu = () => ctxMenu.value.show = false

onMounted(async () => {
  document.addEventListener('click', hideMenu)
  // 마지막 폴더 경로 로드
  const bk = await getBackend()
  if (bk.getLastGalleryFolder) {
    bk.getLastGalleryFolder((f) => { if (f) { currentFolder.value = f } })
  }
  loadImages()
  onBackendEvent('galleryFolderLoaded', (f) => { currentFolder.value = f; visibleCount.value = 40; loadImages(true) })

  // 무한 스크롤
  nextTick(() => {
    observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && visibleCount.value < images.value.length) {
        visibleCount.value = Math.min(visibleCount.value + 30, images.value.length)
        nextTick(() => { if (sentinelRef.value) observer.observe(sentinelRef.value) })
      }
    }, { threshold: 0.1 })
    if (sentinelRef.value) observer.observe(sentinelRef.value)
  })
})
onUnmounted(() => document.removeEventListener('click', hideMenu))
</script>

<style scoped>
.gallery-workspace { height: 100%; display: flex; flex-direction: column; background: var(--bg-primary); position: relative; overflow: hidden; }

/* Toolbar */
.gallery-toolbar {
  height: 54px; display: flex; align-items: center; padding: 0 20px;
  background: var(--bg-secondary); border-bottom: 1px solid var(--border);
}
.folder-info { display: flex; align-items: center; gap: 10px; cursor: pointer; opacity: 0.7; transition: var(--transition); }
.folder-info:hover { opacity: 1; }
.folder-info .path { font-size: 11px; font-weight: 800; letter-spacing: 1px; color: var(--text-muted); text-transform: uppercase; max-width: 400px; overflow: hidden; text-overflow: ellipsis; }

.control-group { display: flex; align-items: center; gap: 12px; }
.icon-btn { background: transparent; border: none; font-size: 16px; cursor: pointer; }
.sort-chips { display: flex; gap: 4px; }
.mini-chip { padding: 4px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; }
.mini-chip.active { border-color: var(--accent); color: var(--accent); }
.count-badge { font-size: 10px; font-weight: 900; color: var(--text-muted); margin-left: 8px; }

/* Grid */
.gallery-content { flex: 1; overflow-y: auto; padding: 20px; }
.masonry-grid { columns: 5 200px; column-gap: 12px; }
.gallery-card {
  break-inside: avoid; margin-bottom: 12px; border-radius: var(--radius-card);
  overflow: hidden; border: 1px solid var(--border); position: relative;
  cursor: pointer; transition: var(--transition); background: var(--bg-card);
}
.gallery-card img { width: 100%; display: block; transition: var(--transition); }
.gallery-card:hover { transform: translateY(-4px); border-color: var(--text-muted); }
.gallery-card:hover img { filter: brightness(0.7); }

.card-hover-actions {
  position: absolute; top: 10px; right: 10px; display: flex; gap: 6px;
  opacity: 0; transition: var(--transition);
}
.gallery-card:hover .card-hover-actions { opacity: 1; }
.tiny-btn { width: 30px; height: 30px; border-radius: 50%; background: rgba(0,0,0,0.6); border: 1px solid rgba(255,255,255,0.1); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.tiny-btn:hover { background: var(--accent); color: black; }

/* EXIF Sidebar */
.exif-sidebar {
  position: absolute; top: 0; right: 0; bottom: 0; width: 380px;
  background: var(--bg-secondary); border-left: 1px solid var(--border);
  box-shadow: -20px 0 50px rgba(0,0,0,0.5); z-index: 100;
  display: flex; flex-direction: column;
}
.exif-close { position: absolute; top: 20px; left: -20px; width: 40px; height: 40px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transform: rotate(0deg); }

.exif-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.exif-preview { width: 100%; aspect-ratio: 1; overflow: hidden; }
.exif-preview img { width: 100%; height: 100%; object-fit: contain; background: #000; }

.exif-meta { padding: 24px; }
.exif-meta h3 { font-size: 12px; letter-spacing: 4px; color: var(--text-muted); margin-bottom: 20px; }
.meta-row { display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.meta-row span { font-size: 10px; font-weight: 900; color: var(--text-muted); }
.meta-row p { font-size: 12px; font-weight: 700; color: var(--text-primary); }

.meta-block label { font-size: 10px; font-weight: 900; color: var(--accent); margin-bottom: 8px; }
.code-box { background: var(--bg-input); padding: 12px; border-radius: 8px; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.6; color: var(--text-secondary); word-break: break-all; }

.exif-footer { padding: 20px; background: var(--bg-card); border-top: 1px solid var(--border); }
.main-apply-btn { width: 100%; height: 46px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 12px; letter-spacing: 1px; cursor: pointer; }
.mini-action { flex: 1; height: 36px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); font-size: 10px; font-weight: 800; cursor: pointer; }

/* Context Menu */
.modern-ctx-menu { position: fixed; background: #181818; border: 1px solid #222; border-radius: 10px; padding: 6px; z-index: 1000; min-width: 200px; box-shadow: 0 12px 32px rgba(0,0,0,0.8); }
.ctx-item { padding: 10px 14px; font-size: 11px; font-weight: 600; color: #909090; cursor: pointer; border-radius: 6px; }
.ctx-item:hover { background: #252525; color: #FFF; }
.ctx-item.delete { color: #f87171; }

/* Large View Overlay */
.large-view-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.85); z-index: 200; display: flex; align-items: center; justify-content: center; }
.large-view-panel { width: 90%; height: 90%; background: var(--bg-secondary); border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--border); }
.large-view-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid var(--border); }
.large-filename { font-size: 12px; font-weight: 700; color: var(--text-primary); }
.large-actions { display: flex; gap: 4px; }
.lv-btn { padding: 5px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }
.lv-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }
.lv-btn.accent { background: var(--accent); color: #000; border: none; }
.lv-btn.save { background: #4ade80; color: #000; border: none; }
.lv-close { background: none; border: none; color: #f87171; font-size: 18px; cursor: pointer; padding: 0 8px; }
.large-view-body { flex: 1; display: flex; overflow: hidden; }
.large-img-area { flex: 1; display: flex; align-items: center; justify-content: center; background: #000; overflow: hidden; padding: 16px; }
.large-img-area img { max-width: 100%; max-height: 100%; object-fit: contain; }
.large-exif { width: 340px; overflow-y: auto; padding: 16px; border-left: 1px solid var(--border); }
.code-box.editable { cursor: text; border: 1px solid transparent; }
.code-box.editable:focus { border-color: var(--accent-dim); outline: none; }
.click-hint { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); font-size: 10px; color: var(--text-muted); background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px; opacity: 0; transition: 0.2s; }
.exif-preview { position: relative; cursor: pointer; }
.exif-preview:hover .click-hint { opacity: 1; }
.mt-8 { margin-top: 8px; }
.sentinel { height: 20px; }
.load-more-info { text-align: center; padding: 8px; font-size: 10px; color: var(--text-muted); }
.spinner { width: 32px; height: 32px; border: 3px solid #222; border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 12px; }
@keyframes spin { to { transform: rotate(360deg); } }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* Transitions */
.slide-enter-active, .slide-leave-active { transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
