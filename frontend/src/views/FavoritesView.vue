<template>
  <div class="gallery-workspace">
    <!-- Top Filter & Action Bar -->
    <header class="gallery-toolbar">
      <div class="folder-info no-click">
        <span class="icon"><Icon name="star" /></span>
        <span class="path">즐겨찾기</span>
      </div>

      <div class="spacer"></div>

      <!-- EXIF 검색 -->
      <div class="search-box">
        <input v-model="exifSearch" placeholder="EXIF 검색..." class="search-input"
          @keydown.enter="runExifSearch" />
        <button class="search-go" @click="runExifSearch" :disabled="exifSearching">{{ exifSearching ? '...' : 'GO' }}</button>
        <button class="search-clear" v-if="exifFiltered" @click="clearExifSearch"><Icon name="close" /></button>
      </div>

      <div class="control-group">
        <button class="icon-btn" @click="loadFavorites" title="Refresh"><Icon name="refresh" /></button>
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
          <img :src="thumbnailUrl(img, thumbSize * thumbPixelRatio)" loading="lazy" />
          <div class="card-hover-actions">
            <button class="tiny-btn" @click.stop="removeFav(img)" title="즐겨찾기 제거"><Icon name="star" /></button>
            <button class="tiny-btn" @click.stop="quickAction('copy_to_clipboard', img)" title="복사"><Icon name="clipboard" /></button>
          </div>
        </div>
      </div>
      <div class="load-more-info" v-if="visibleCount < (exifFiltered ? filteredImages.length : images.length)">
        {{ visibleCount }} / {{ exifFiltered ? filteredImages.length : images.length }} — 스크롤하여 더 보기
      </div>

      <div v-if="images.length === 0" class="empty-placeholder">
        <div class="icon"><Icon name="star" /></div>
        <h2>즐겨찾기가 없습니다</h2>
        <p>아직 즐겨찾기한 이미지가 없습니다</p>
      </div>
    </section>

    <!-- 별도 뷰어 창 (이미지 확대 + EXIF + 전송 버튼) — 이전 Favorites 방식 복원 -->
    <transition name="fade">
      <div v-if="viewerData" class="viewer-overlay" @mousedown.self="viewerData = null">
        <div class="viewer-panel">
          <div class="viewer-header">
            <span>{{ viewerData.filename }}</span>
            <button class="viewer-close" @click="viewerData = null"><Icon name="close" /></button>
          </div>
          <div class="viewer-body">
            <div class="viewer-img">
              <img :src="mediaUrl(viewerData.path)" />
            </div>
            <div class="viewer-info">
              <div class="vi-size">{{ viewerData.size }}</div>
              <div v-if="viewerData.prompt" class="vi-section">
                <div class="vi-head"><label>프롬프트</label></div>
                <div class="vi-pre-wrap">
                  <button class="vi-copy-float" @click="copySection(viewerData.prompt, 'Prompt')" title="Prompt 복사"><Icon name="clipboard" /></button>
                  <pre>{{ viewerData.prompt }}</pre>
                </div>
              </div>
              <div v-if="viewerData.negative" class="vi-section">
                <div class="vi-head"><label class="neg">네거티브</label></div>
                <div class="vi-pre-wrap">
                  <button class="vi-copy-float" @click="copySection(viewerData.negative, 'Negative')" title="Negative 복사"><Icon name="clipboard" /></button>
                  <pre>{{ viewerData.negative }}</pre>
                </div>
              </div>
              <div v-if="viewerData.raw && !viewerData.prompt" class="vi-section">
                <div class="vi-head"><label>원본</label></div>
                <div class="vi-pre-wrap">
                  <button class="vi-copy-float" @click="copySection(viewerData.raw, 'Raw')" title="Raw 복사"><Icon name="clipboard" /></button>
                  <pre>{{ viewerData.raw }}</pre>
                </div>
              </div>
              <div v-if="viewerParams" class="vi-section">
                <div class="vi-head"><label>파라미터</label></div>
                <div class="vi-pre-wrap">
                  <button class="vi-copy-float" @click="copySection(viewerParams, 'Parameters')" title="Parameters 복사"><Icon name="clipboard" /></button>
                  <pre>{{ viewerParams }}</pre>
                </div>
              </div>
              <div class="vi-actions-section">
                <label class="vi-actions-label">보내기</label>
                <div class="vi-send-grid">
                  <button class="send-card primary" @click="action('gallery_send_exif_to_t2i', { exif: viewerData.raw, path: viewerData.path })" title="EXIF + 이미지를 T2I 탭에 전송">
                    <span class="send-ico"><Icon name="upload" /></span>
                    <span class="send-name">T2I</span>
                  </button>
                  <button class="send-card" @click="action('send_to_i2i', { path: viewerData.path })" title="I2I 탭으로">
                    <span class="send-ico"><Icon name="image" /></span>
                    <span class="send-name">I2I</span>
                  </button>
                  <button class="send-card" @click="action('send_to_inpaint', { path: viewerData.path })" title="Inpaint 탭으로">
                    <span class="send-ico"><Icon name="scissors" /></span>
                    <span class="send-name">Inpaint</span>
                  </button>
                  <button class="send-card" @click="action('send_to_editor', { path: viewerData.path })" title="Editor 탭으로">
                    <span class="send-ico"><Icon name="palette" /></span>
                    <span class="send-name">Editor</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Context Menu -->
    <transition name="pop">
      <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="ctxMenuStyle">
        <div class="ctx-item" @click="ctx('gallery_load_exif')"><Icon name="clipboard" /> EXIF 보기</div>
        <div class="ctx-item" @click="ctx('send_to_i2i')"><Icon name="image" /> I2I로 보내기</div>
        <div class="ctx-item" @click="ctx('send_to_inpaint')"><Icon name="palette" /> 인페인트로 보내기</div>
        <div class="ctx-item" @click="ctx('send_to_editor')"><Icon name="pencil" /> 에디터로 보내기</div>
        <div class="ctx-item" @click="ctx('copy_to_clipboard')"><Icon name="clipboard" /> 복사</div>
        <div class="ctx-item" @click="sendToCompare('before')"><Icon name="search" /> 비교 (이전)</div>
        <div class="ctx-item" @click="sendToCompare('after')"><Icon name="search" /> 비교 (이후)</div>
        <div class="ctx-separator"></div>
        <div class="ctx-item unfav" @click="ctxRemoveFav"><Icon name="star" /> 즐겨찾기 해제</div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import { mediaUrl, thumbnailUrl } from '../utils/media.js'

interface ViewerData {
  filename?: string
  path?: string
  size?: string
  prompt?: string
  negative?: string
  raw?: string
  [k: string]: any
}

const images = ref<string[]>([])
const visibleCount = ref(40)

// 썸네일 크기 — localStorage 영속 (gallery와 공유)
const thumbSize = ref(parseInt(window.localStorage.getItem('gallery_thumb_size') || '200'))
const thumbPixelRatio = Math.min(2, Math.max(1, window.devicePixelRatio || 1))
watch(thumbSize, (v) => window.localStorage.setItem('gallery_thumb_size', String(v)))

// ── 썸네일 캐싱 (백그라운드 생성 + thumbnailReady 시그널) ──
const BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='
const THUMB_W = 384
const thumbCache = reactive<Record<string, string>>({})
const _thumbRequested = new Set<string>()
let _thumbOff: (() => void) | null = null
async function requestThumbs(list: string[]) {
  const need = list.filter(p => !_thumbRequested.has(p))
  if (!need.length) return
  need.forEach(p => _thumbRequested.add(p))
  const backend: any = await getBackend()
  if (backend.generateThumbnails) backend.generateThumbnails(JSON.stringify(need), THUMB_W)
}

// EXIF 검색
const exifSearch = ref('')
const exifFiltered = ref(false)
const exifSearching = ref(false)
const filteredImages = ref<string[]>([])
const exifCache = ref<Record<string, string>>({})

const displayImages = computed(() => {
  const source = exifFiltered.value ? filteredImages.value : images.value
  return source.slice(0, visibleCount.value)
})
// 보이는 카드의 썸네일만 요청
// 썸네일 캐싱 비활성화 — Gallery처럼 원본을 직접 표시(저화질 썸네일 회피)
// watch(displayImages, (list) => requestThumbs(list), { immediate: true })

const largeViewParams = computed(() => {
  if (!largeView.value?.raw) return ''
  const m = largeView.value.raw.match(/Steps:.*$/m); return m ? m[0] : ''
})
const sidebarParams = computed(() => {
  if (!exifData.value?.raw) return ''
  const m = exifData.value.raw.match(/Steps:.*$/m); return m ? m[0] : ''
})
// 이전 Favorites 방식: 중앙 모달 뷰어
const viewerData = ref<ViewerData | null>(null)
const viewerParams = computed(() => {
  if (!viewerData.value?.raw) return ''
  const m = viewerData.value.raw.match(/Steps:.*$/m); return m ? m[0] : ''
})

const galleryContentRef = ref<HTMLElement | null>(null)
const sortBy = ref('date')
const sortOptions = [{ label: '날짜', val: 'date' }, { label: '이름', val: 'name' }]
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })
const exifData = ref<any>(null)
const largeView = ref<any>(null)
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
  const backend: any = await getBackend()
  if (backend.getFavorites) {
    backend.getFavorites((json: string) => {
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
    images.value = [...images.value].sort((a, b) => (a.split('/').pop() || '').localeCompare(b.split('/').pop() || ''))
  } else {
    loadFavorites()
  }
}

function onGalleryScroll(e: Event) {
  const el = e.target as HTMLElement
  const total = exifFiltered.value ? filteredImages.value.length : images.value.length
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 200 && visibleCount.value < total) {
    visibleCount.value = Math.min(visibleCount.value + 30, total)
  }
}

async function runExifSearch() {
  const query = exifSearch.value.trim().toLowerCase()
  if (!query) { clearExifSearch(); return }
  exifSearching.value = true
  const backend: any = await getBackend()
  const toCheck = images.value.filter(img => !(img in exifCache.value))
  const batchSize = 20
  for (let i = 0; i < toCheck.length; i += batchSize) {
    const batch = toCheck.slice(i, i + batchSize)
    await Promise.all(batch.map(img => new Promise<void>(resolve => {
      if (backend.getImageExif) {
        backend.getImageExif(img, (json: string) => {
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

const viewImage = async (path: string) => {
  const backend: any = await getBackend()
  if (backend.getImageExif) backend.getImageExif(path, (json: string) => {
    try { const d = JSON.parse(json); viewerData.value = d } catch {}
  })
}

function showMenu(e: MouseEvent, path: string) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function ctx(actionName: string) {
  const path = ctxMenu.value.path
  requestAction(actionName, { path })
  if (actionName === 'gallery_load_exif') viewImage(path)
  ctxMenu.value.show = false
}
function removeFav(path: string) {
  requestAction('remove_favorite', { path })
  images.value = images.value.filter(i => i !== path)
  filteredImages.value = filteredImages.value.filter(i => i !== path)
  if (viewerData.value?.path === path) viewerData.value = null
}
function ctxRemoveFav() { removeFav(ctxMenu.value.path); ctxMenu.value.show = false }

const quickAction = (name: string, path: string) => requestAction(name, { path })
const sendToCompare = (slot: string) => { requestAction('send_to_compare', { path: ctxMenu.value.path, slot }); ctxMenu.value.show = false }
const sendExifToT2I = () => { if (exifData.value) requestAction('gallery_send_exif_to_t2i', { exif: exifData.value.raw || '', path: exifData.value.path }) }
const action = (name: string, payload: Record<string, any> = {}) => requestAction(name, payload)
const hideMenu = () => ctxMenu.value.show = false

async function copySection(text: string, label: string) {
  if (!text) return
  try { await navigator.clipboard.writeText(text); requestAction('show_toast', { type: 'success', msg: `${label} 복사됨` }) }
  catch (e) { requestAction('show_toast', { type: 'error', msg: `복사 실패` }) }
}

onMounted(() => {
  document.addEventListener('click', hideMenu)
  _thumbOff = onBackendEvent('thumbnailReady', (json: string) => {
    try { const d = JSON.parse(json); thumbCache[d.path] = d.thumb || mediaUrl(d.path) } catch {}
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

.folder-info { display: flex; align-items: center; gap: 10px; opacity: 0.85; }
.folder-info.no-click { cursor: default; }
.folder-info .icon { font-size: 15px; }
/* 경로는 있는 그대로 — 대문자로 밀면 실제와 다른 문자열이 된다 */
.folder-info .path { font-size: var(--fs-meta); color: var(--text-muted); }


.gallery-card img { width: 100%; display: block; transition: var(--transition); }

.gallery-card:hover img { filter: brightness(0.7); }


.exif-close { position: absolute; top: 20px; left: -20px; width: 40px; height: 40px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; }

.exif-preview { width: 100%; aspect-ratio: 1; overflow: hidden; position: relative; cursor: pointer; }
.exif-preview img { width: 100%; height: 100%; object-fit: contain; background: #000; }

.meta-row p { font-size: 12px; font-weight: var(--fw-bold); color: var(--text-primary); word-break: break-all; }
.meta-head { display: flex; align-items: center; justify-content: space-between; min-height: 18px; margin-bottom: 6px; }
.meta-block label { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--accent); }
.meta-block label.danger { color: #f87171; }
.copy-btn { opacity: 0; background: none; border: 1px solid transparent; color: var(--text-muted); width: 22px; height: 22px; border-radius: 4px; cursor: pointer; font-size: 11px; }
.meta-block:hover .copy-btn { opacity: 0.7; }
.copy-btn:hover { opacity: 1; background: var(--bg-button); border-color: var(--border); color: var(--accent); }
.code-box { background: var(--bg-input); padding: 12px; border-radius: 8px; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.6; color: var(--text-secondary); word-break: break-all; max-height: 240px; overflow-y: auto; }

/* 이전 Favorites 중앙 모달 뷰어 복원 */
.viewer-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.85); z-index: 100; display: flex; align-items: center; justify-content: center; }
.viewer-panel { width: 85%; height: 85%; background: #0D0D0D; border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; border: 1px solid #222; }
.viewer-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; border-bottom: 1px solid #1A1A1A; }
.viewer-header span { font-size: 12px; color: #787878; }
.viewer-close { background: none; border: none; color: #f87171; font-size: 18px; cursor: pointer; }
.viewer-body { flex: 1; display: flex; overflow: hidden; }
.viewer-img { flex: 1; display: flex; align-items: center; justify-content: center; background: #000; padding: 16px; }
.viewer-img img { max-width: 100%; max-height: 100%; object-fit: contain; }
.viewer-info { width: 460px; max-width: 46vw; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; border-left: 1px solid #1A1A1A; }
.vi-size { color: #585858; font-size: 12px; }
.vi-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px; min-height: 18px; }
.vi-head label { color: var(--accent); font-size: 11px; font-weight: var(--fw-bold); letter-spacing: 0; margin: 0; }
.vi-head label.neg { color: #f87171; }
.vi-pre-wrap { position: relative; }
.vi-copy-float { position: absolute; top: 7px; right: 7px; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; background: rgba(20,20,20,0.5); border: 1px solid rgba(255,255,255,0.12); border-radius: 7px; color: #ddd; font-size: 14px; cursor: pointer; opacity: 0.5; backdrop-filter: blur(3px); transition: opacity .15s, background .15s, border-color .15s; z-index: 2; }
.vi-pre-wrap:hover .vi-copy-float { opacity: 0.85; }
.vi-copy-float:hover { opacity: 1 !important; background: rgba(45,45,45,0.9); border-color: var(--accent); color: var(--accent); }
.vi-section pre { color: #C4C4C4; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; background: #111; padding: 12px 14px; border-radius: 6px; margin: 0; max-height: 360px; overflow-y: auto; }
.vi-actions-section { margin-top: auto; padding-top: 12px; }
.vi-actions-label { display: block; font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-muted); letter-spacing: 0; margin-bottom: 8px; }
.vi-send-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.send-card { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 10px 6px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; transition: all 0.15s; }
.send-card:hover { background: var(--bg-input); border-color: var(--text-muted); transform: translateY(-1px); }
.send-card.primary { background: var(--accent-dim); border-color: rgba(250,204,21,0.4); }
.send-card.primary:hover { background: rgba(250,204,21,0.15); border-color: var(--accent); box-shadow: 0 2px 8px rgba(250,204,21,0.2); }
.send-ico { font-size: 18px; line-height: 1; }
.send-name { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-secondary); letter-spacing: 0; }
.send-card.primary .send-name { color: var(--accent); }

.mini-action { height: 36px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); font-size: var(--fs-label); font-weight: var(--fw-bold); cursor: pointer; }

.ctx-item.unfav { color: var(--accent); }

.lv-btn.unfav { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

.large-img-area img { max-width: 100%; max-height: 100%; object-fit: contain; }


.pop-enter-active { transition: all 0.12s; }
.pop-enter-from { opacity: 0; transform: scale(0.95); }
</style>
