<template>
  <div class="gallery-workspace">
    <!-- Top Filter & Action Bar -->
    <header class="gallery-toolbar">
      <div class="folder-info no-click">
        <span class="icon">⭐</span>
        <span class="path">FAVORITES</span>
      </div>

      <div class="spacer"></div>

      <!-- EXIF 검색 -->
      <div class="search-box">
        <input v-model="exifSearch" placeholder="🔍 EXIF 검색..." class="search-input"
          @keydown.enter="runExifSearch" />
        <button class="search-go" @click="runExifSearch" :disabled="exifSearching">{{ exifSearching ? '...' : 'GO' }}</button>
        <button class="search-clear" v-if="exifFiltered" @click="clearExifSearch">✕</button>
      </div>

      <div class="control-group">
        <button class="icon-btn" @click="loadFavorites" title="Refresh">🔄</button>
        <div class="sep"></div>
        <div class="sort-chips">
          <button v-for="s in sortOptions" :key="s.val"
            class="mini-chip" :class="{ active: sortBy === s.val }"
            @click="sortBy = s.val; sortImages()"
          >{{ s.label }}</button>
        </div>
        <div class="sep"></div>
        <!-- 썸네일 크기 슬라이더 -->
        <div class="thumb-size-ctl" :title="`썸네일 크기: ${thumbSize}px`">
          <span class="thumb-icon-small">▫</span>
          <input type="range" v-model.number="thumbSize" min="100" max="380" step="20" class="thumb-slider" />
          <span class="thumb-icon-large">▪</span>
          <span class="thumb-size-val">{{ thumbSize }}px</span>
        </div>
        <span class="count-badge">{{ exifFiltered ? filteredImages.length + '/' : '' }}{{ images.length }}</span>
      </div>
    </header>

    <!-- Masonry-style Grid -->
    <section class="gallery-content" ref="galleryContentRef" @scroll="onGalleryScroll">
      <div class="masonry-grid" :style="{ 'columns': `auto ${thumbSize}px` }">
        <div v-for="img in displayImages" :key="img" class="gallery-card"
          @click="viewImage(img)"
          @contextmenu.prevent="showMenu($event, img)"
        >
          <img :src="thumbCache[img] || BLANK" loading="lazy" />
          <div class="card-hover-actions">
            <button class="tiny-btn" @click.stop="removeFav(img)" title="즐겨찾기 제거">⭐</button>
            <button class="tiny-btn" @click.stop="quickAction('copy_to_clipboard', img)" title="복사">📋</button>
          </div>
        </div>
      </div>
      <div class="load-more-info" v-if="visibleCount < (exifFiltered ? filteredImages.length : images.length)">
        {{ visibleCount }} / {{ exifFiltered ? filteredImages.length : images.length }} — 스크롤하여 더 보기
      </div>

      <div v-if="images.length === 0" class="empty-placeholder">
        <div class="icon">⭐</div>
        <h2>NO FAVORITES</h2>
        <p>아직 즐겨찾기한 이미지가 없습니다</p>
      </div>
    </section>

    <!-- 이미지 확대 뷰 (풀스크린 오버레이) -->
    <transition name="fade">
      <div v-if="largeView" class="large-view-overlay" @click.self="closeLargeView">
        <div class="large-view-panel">
          <div class="large-view-header">
            <span class="large-filename">{{ largeView.filename }}</span>
            <div class="large-actions">
              <button class="lv-btn" @click="action('send_to_i2i', { path: largeView.path })">I2I</button>
              <button class="lv-btn" @click="action('send_to_inpaint', { path: largeView.path })">INPAINT</button>
              <button class="lv-btn" @click="action('send_to_editor', { path: largeView.path })">EDITOR</button>
              <button class="lv-btn unfav" @click="removeFav(largeView.path)">⭐ UNFAV</button>
              <button class="lv-btn accent" @click="sendExifToT2I">USE PROMPT</button>
              <button class="lv-close" @click="closeLargeView">✕</button>
            </div>
          </div>
          <div class="large-view-body">
            <div class="large-img-area">
              <img :src="'file:///' + largeView.path + '?t=' + Date.now()" />
            </div>
            <div class="large-exif">
              <div class="meta-row"><span>SIZE</span><p>{{ largeView.size }}</p></div>
              <div v-if="largeView.prompt" class="meta-block">
                <div class="meta-head"><label>PROMPT</label><button class="copy-btn" @click="copySection(largeView.prompt, 'Prompt')">📋</button></div>
                <div class="code-box">{{ largeView.prompt }}</div>
              </div>
              <div v-if="largeView.negative" class="meta-block mt-8">
                <div class="meta-head"><label class="danger">NEGATIVE</label><button class="copy-btn" @click="copySection(largeView.negative, 'Negative')">📋</button></div>
                <div class="code-box">{{ largeView.negative }}</div>
              </div>
              <div v-if="largeView.raw && !largeView.prompt" class="meta-block">
                <div class="meta-head"><label>RAW</label><button class="copy-btn" @click="copySection(largeView.raw, 'Raw')">📋</button></div>
                <div class="code-box">{{ largeView.raw }}</div>
              </div>
              <div v-if="largeViewParams" class="meta-block mt-8">
                <label>PARAMETERS</label>
                <div class="code-box params">{{ largeViewParams }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Slide-out EXIF Panel (사이드바) -->
    <transition name="slide">
      <aside v-if="exifData && !largeView && showMetadata" class="exif-sidebar">
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
              <div class="meta-head"><label>PROMPT</label><button class="copy-btn" @click="copySection(exifData.prompt, 'Prompt')">📋</button></div>
              <div class="code-box">{{ exifData.prompt }}</div>
            </div>
            <div v-if="exifData.negative" class="meta-block mt-12">
              <div class="meta-head"><label class="danger">NEGATIVE</label><button class="copy-btn" @click="copySection(exifData.negative, 'Negative')">📋</button></div>
              <div class="code-box">{{ exifData.negative }}</div>
            </div>
            <div v-if="sidebarParams" class="meta-block mt-12">
              <label>PARAMETERS</label>
              <div class="code-box params">{{ sidebarParams }}</div>
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
      <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="ctxMenuStyle">
        <div class="ctx-item" @click="ctx('gallery_load_exif')">📋 INSPECT EXIF</div>
        <div class="ctx-item" @click="ctx('send_to_i2i')">🖼️ SEND TO I2I</div>
        <div class="ctx-item" @click="ctx('send_to_inpaint')">🎨 SEND TO INPAINT</div>
        <div class="ctx-item" @click="ctx('send_to_editor')">✏️ SEND TO EDITOR</div>
        <div class="ctx-item" @click="ctx('copy_to_clipboard')">📋 COPY</div>
        <div class="ctx-item" @click="sendToCompare('before')">🔍 COMPARE (BEFORE)</div>
        <div class="ctx-item" @click="sendToCompare('after')">🔍 COMPARE (AFTER)</div>
        <div class="ctx-separator"></div>
        <div class="ctx-item unfav" @click="ctxRemoveFav">⭐ REMOVE FROM FAVORITES</div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const images = ref([])
const visibleCount = ref(40)

// 썸네일 크기 — localStorage 영속 (gallery와 공유)
const thumbSize = ref(parseInt(window.localStorage.getItem('gallery_thumb_size') || '200'))
watch(thumbSize, (v) => window.localStorage.setItem('gallery_thumb_size', String(v)))

// ── 썸네일 캐싱 (백그라운드 생성 + thumbnailReady 시그널) ──
const BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='
const THUMB_W = 384
const thumbCache = reactive({})
const _thumbRequested = new Set()
let _thumbOff = null
async function requestThumbs(list) {
  const need = list.filter(p => !_thumbRequested.has(p))
  if (!need.length) return
  need.forEach(p => _thumbRequested.add(p))
  const backend = await getBackend()
  if (backend.generateThumbnails) backend.generateThumbnails(JSON.stringify(need), THUMB_W)
}

// EXIF 검색
const exifSearch = ref('')
const exifFiltered = ref(false)
const exifSearching = ref(false)
const filteredImages = ref([])
const exifCache = ref({})

const displayImages = computed(() => {
  const source = exifFiltered.value ? filteredImages.value : images.value
  return source.slice(0, visibleCount.value)
})
// 보이는 카드의 썸네일만 요청
watch(displayImages, (list) => requestThumbs(list), { immediate: true })

const largeViewParams = computed(() => {
  if (!largeView.value?.raw) return ''
  const m = largeView.value.raw.match(/Steps:.*$/m); return m ? m[0] : ''
})
const sidebarParams = computed(() => {
  if (!exifData.value?.raw) return ''
  const m = exifData.value.raw.match(/Steps:.*$/m); return m ? m[0] : ''
})

const galleryContentRef = ref(null)
const sortBy = ref('date')
const sortOptions = [{ label: 'DATE', val: 'date' }, { label: 'NAME', val: 'name' }]
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const exifData = ref(null)
const largeView = ref(null)
const showMetadata = ref(window.localStorage.getItem('galleryShowMetadata') !== 'false')
const _showMetaTimer = setInterval(() => {
  const v = window.localStorage.getItem('galleryShowMetadata') !== 'false'
  if (v !== showMetadata.value) showMetadata.value = v
}, 500)

const ctxMenuStyle = computed(() => {
  const w = 220, h = 320
  let x = ctxMenu.value.x, y = ctxMenu.value.y
  if (x + w > window.innerWidth) x = window.innerWidth - w - 10
  if (y + h > window.innerHeight) y = window.innerHeight - h - 10
  return { top: y + 'px', left: x + 'px' }
})

async function loadFavorites() {
  const backend = await getBackend()
  if (backend.getFavorites) {
    backend.getFavorites((json) => {
      try {
        const list = JSON.parse(json)
        images.value = Array.isArray(list) ? list : []
        if (sortBy.value === 'name') sortImages()
      } catch {}
    })
  }
}

function sortImages() {
  if (sortBy.value === 'name') {
    images.value = [...images.value].sort((a, b) => a.split('/').pop().localeCompare(b.split('/').pop()))
  } else {
    loadFavorites()
  }
}

function onGalleryScroll(e) {
  const el = e.target
  const total = exifFiltered.value ? filteredImages.value.length : images.value.length
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 200 && visibleCount.value < total) {
    visibleCount.value = Math.min(visibleCount.value + 30, total)
  }
}

async function runExifSearch() {
  const query = exifSearch.value.trim().toLowerCase()
  if (!query) { clearExifSearch(); return }
  exifSearching.value = true
  const backend = await getBackend()
  const toCheck = images.value.filter(img => !(img in exifCache.value))
  const batchSize = 20
  for (let i = 0; i < toCheck.length; i += batchSize) {
    const batch = toCheck.slice(i, i + batchSize)
    await Promise.all(batch.map(img => new Promise(resolve => {
      if (backend.getImageExif) {
        backend.getImageExif(img, (json) => {
          try {
            const d = JSON.parse(json)
            exifCache.value[img] = `${d.prompt || ''} ${d.negative || ''} ${d.raw || ''}`.toLowerCase()
          } catch { exifCache.value[img] = '' }
          resolve()
        })
      } else resolve()
    })))
    if (!exifSearch.value.trim()) { exifSearching.value = false; return }
  }
  filteredImages.value = images.value.filter(img => (exifCache.value[img] || '').includes(query))
  exifFiltered.value = true
  exifSearching.value = false
  visibleCount.value = 40
}
function clearExifSearch() {
  exifSearch.value = ''; exifFiltered.value = false; filteredImages.value = []; visibleCount.value = 40
}

function closeLargeView() {
  largeView.value = null
  if (!showMetadata.value) exifData.value = null
}

const viewImage = async (path) => {
  const backend = await getBackend()
  if (backend.getImageExif) backend.getImageExif(path, (json) => {
    try { const d = JSON.parse(json); largeView.value = d; exifData.value = d } catch {}
  })
}

function showMenu(e, path) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function ctx(actionName) {
  const path = ctxMenu.value.path
  requestAction(actionName, { path })
  if (actionName === 'gallery_load_exif') viewImage(path)
  ctxMenu.value.show = false
}
function removeFav(path) {
  requestAction('remove_favorite', { path })
  images.value = images.value.filter(i => i !== path)
  filteredImages.value = filteredImages.value.filter(i => i !== path)
  if (largeView.value?.path === path) closeLargeView()
}
function ctxRemoveFav() { removeFav(ctxMenu.value.path); ctxMenu.value.show = false }

const quickAction = (name, path) => requestAction(name, { path })
const sendToCompare = (slot) => { requestAction('send_to_compare', { path: ctxMenu.value.path, slot }); ctxMenu.value.show = false }
const sendExifToT2I = () => { if (exifData.value) requestAction('gallery_send_exif_to_t2i', { exif: exifData.value.raw || '', path: exifData.value.path }) }
const action = (name, payload = {}) => requestAction(name, payload)
const hideMenu = () => ctxMenu.value.show = false

async function copySection(text, label) {
  if (!text) return
  try { await navigator.clipboard.writeText(text); requestAction('show_toast', { type: 'success', msg: `${label} 복사됨` }) }
  catch (e) { requestAction('show_toast', { type: 'error', msg: `복사 실패` }) }
}

onMounted(() => {
  document.addEventListener('click', hideMenu)
  _thumbOff = onBackendEvent('thumbnailReady', (json) => {
    try { const d = JSON.parse(json); thumbCache[d.path] = d.thumb || ('file:///' + d.path) } catch {}
  })
  loadFavorites()
})
onUnmounted(() => {
  document.removeEventListener('click', hideMenu)
  if (_showMetaTimer) clearInterval(_showMetaTimer)
  if (_thumbOff) _thumbOff()
})
</script>

<style scoped>
.gallery-workspace { height: 100%; display: flex; flex-direction: column; background: var(--bg-primary); position: relative; overflow: hidden; }

/* Toolbar */
.gallery-toolbar { height: 54px; display: flex; align-items: center; padding: 0 20px; background: var(--bg-secondary); border-bottom: 1px solid var(--border); }
.folder-info { display: flex; align-items: center; gap: 10px; opacity: 0.85; }
.folder-info.no-click { cursor: default; }
.folder-info .icon { font-size: 15px; }
.folder-info .path { font-size: 11px; font-weight: 800; letter-spacing: 1px; color: var(--accent); text-transform: uppercase; }
.spacer { flex: 1; }

.control-group { display: flex; align-items: center; gap: 12px; }
.icon-btn { background: transparent; border: none; font-size: 16px; cursor: pointer; }
.sep { width: 1px; height: 20px; background: var(--border); }
.sort-chips { display: flex; gap: 4px; }
.mini-chip { padding: 4px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-muted); font-size: 9px; font-weight: 800; cursor: pointer; }
.mini-chip.active { border-color: var(--accent); color: var(--accent); }
.count-badge { font-size: 10px; font-weight: 900; color: var(--text-muted); margin-left: 8px; }
.search-box { display: flex; align-items: center; gap: 4px; margin-right: 12px; }
.search-input { width: 180px; padding: 5px 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-primary); font-size: 11px; }
.search-input:focus { border-color: var(--accent); }
.search-go { padding: 5px 10px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-size: 10px; font-weight: 800; cursor: pointer; }
.search-go:disabled { opacity: 0.4; }
.search-clear { background: none; border: none; color: #f87171; cursor: pointer; font-size: 14px; }

/* Grid */
.gallery-content { flex: 1; overflow-y: auto; padding: 20px; }
.masonry-grid { columns: auto 200px; column-gap: 12px; }

.thumb-size-ctl { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; }
.thumb-icon-small { font-size: 8px; color: var(--text-muted); }
.thumb-icon-large { font-size: 14px; color: var(--text-muted); }
.thumb-slider { -webkit-appearance: none; appearance: none; width: 90px; height: 4px; background: rgba(255,255,255,0.15); border-radius: 2px; outline: none; cursor: pointer; }
.thumb-slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 12px; height: 12px; background: var(--accent); border-radius: 50%; cursor: pointer; transition: transform 0.1s; }
.thumb-slider::-webkit-slider-thumb:hover { transform: scale(1.3); }
.thumb-size-val { font-size: 9px; color: var(--text-muted); font-weight: 700; min-width: 36px; text-align: right; }

.gallery-card { break-inside: avoid; margin-bottom: 12px; border-radius: var(--radius-card); overflow: hidden; border: 1px solid var(--border); position: relative; cursor: pointer; transition: var(--transition); background: var(--bg-card); }
.gallery-card img { width: 100%; display: block; transition: var(--transition); }
.gallery-card:hover { transform: translateY(-4px); border-color: var(--text-muted); }
.gallery-card:hover img { filter: brightness(0.7); }
.card-hover-actions { position: absolute; top: 10px; right: 10px; display: flex; gap: 6px; opacity: 0; transition: var(--transition); }
.gallery-card:hover .card-hover-actions { opacity: 1; }
.tiny-btn { width: 30px; height: 30px; border-radius: 50%; background: rgba(0,0,0,0.6); border: 1px solid rgba(255,255,255,0.1); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.tiny-btn:hover { background: var(--accent); color: black; }

.empty-placeholder { text-align: center; padding: 80px 20px; color: var(--text-muted); }
.empty-placeholder .icon { font-size: 48px; }
.empty-placeholder h2 { font-size: 16px; letter-spacing: 3px; margin: 12px 0 6px; color: var(--text-secondary); }
.empty-placeholder p { font-size: 12px; }
.load-more-info { text-align: center; padding: 8px; font-size: 10px; color: var(--text-muted); }

/* EXIF Sidebar */
.exif-sidebar { position: absolute; top: 0; right: 0; bottom: 0; width: 380px; background: var(--bg-secondary); border-left: 1px solid var(--border); box-shadow: -20px 0 50px rgba(0,0,0,0.5); z-index: 100; display: flex; flex-direction: column; }
.exif-close { position: absolute; top: 20px; left: -20px; width: 40px; height: 40px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.exif-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.exif-preview { width: 100%; aspect-ratio: 1; overflow: hidden; position: relative; cursor: pointer; }
.exif-preview img { width: 100%; height: 100%; object-fit: contain; background: #000; }
.exif-meta { padding: 24px; }
.exif-meta h3 { font-size: 12px; letter-spacing: 4px; color: var(--text-muted); margin-bottom: 20px; }
.meta-row { display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.meta-row span { font-size: 10px; font-weight: 900; color: var(--text-muted); }
.meta-row p { font-size: 12px; font-weight: 700; color: var(--text-primary); word-break: break-all; }
.meta-head { display: flex; align-items: center; justify-content: space-between; min-height: 18px; margin-bottom: 6px; }
.meta-block label { font-size: 10px; font-weight: 900; color: var(--accent); }
.meta-block label.danger { color: #f87171; }
.copy-btn { opacity: 0; background: none; border: 1px solid transparent; color: var(--text-muted); width: 22px; height: 22px; border-radius: 4px; cursor: pointer; font-size: 11px; }
.meta-block:hover .copy-btn { opacity: 0.7; }
.copy-btn:hover { opacity: 1; background: var(--bg-button); border-color: var(--border); color: var(--accent); }
.code-box { background: var(--bg-input); padding: 12px; border-radius: 8px; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.6; color: var(--text-secondary); word-break: break-all; max-height: 240px; overflow-y: auto; }
.code-box.params { color: #94a3b8; font-size: 10px; }
.exif-footer { padding: 20px; background: var(--bg-card); border-top: 1px solid var(--border); }
.main-apply-btn { width: 100%; height: 46px; background: var(--accent); border: none; border-radius: var(--radius-pill); color: #000; font-weight: 900; font-size: 12px; letter-spacing: 1px; cursor: pointer; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.mini-action { height: 36px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); font-size: 10px; font-weight: 800; cursor: pointer; }

/* Context Menu */
.modern-ctx-menu { position: fixed; background: #181818; border: 1px solid #222; border-radius: 10px; padding: 6px; z-index: 1000; min-width: 200px; box-shadow: 0 12px 32px rgba(0,0,0,0.8); }
.ctx-item { padding: 10px 14px; font-size: 11px; font-weight: 600; color: #909090; cursor: pointer; border-radius: 6px; }
.ctx-item:hover { background: #252525; color: #FFF; }
.ctx-item.unfav { color: var(--accent); }
.ctx-separator { height: 1px; background: #222; margin: 4px 0; }

/* Large View Overlay */
.large-view-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.85); z-index: 200; display: flex; align-items: center; justify-content: center; }
.large-view-panel { width: 90%; height: 90%; background: var(--bg-secondary); border-radius: 16px; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--border); }
.large-view-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid var(--border); }
.large-filename { font-size: 12px; font-weight: 700; color: var(--text-primary); }
.large-actions { display: flex; gap: 4px; }
.lv-btn { padding: 5px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }
.lv-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }
.lv-btn.accent { background: var(--accent); color: #000; border: none; }
.lv-btn.unfav { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.lv-close { background: none; border: none; color: #f87171; font-size: 18px; cursor: pointer; padding: 0 8px; }
.large-view-body { flex: 1; display: flex; overflow: hidden; }
.large-img-area { flex: 1; display: flex; align-items: center; justify-content: center; background: #000; overflow: hidden; padding: 16px; }
.large-img-area img { max-width: 100%; max-height: 100%; object-fit: contain; }
.large-exif { width: 340px; overflow-y: auto; padding: 16px; border-left: 1px solid var(--border); }
.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }
.click-hint { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); font-size: 10px; color: var(--text-muted); background: rgba(0,0,0,0.6); padding: 2px 8px; border-radius: 4px; opacity: 0; transition: 0.2s; }
.exif-preview:hover .click-hint { opacity: 1; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
.pop-enter-active { transition: all 0.12s; }
.pop-enter-from { opacity: 0; transform: scale(0.95); }
</style>
