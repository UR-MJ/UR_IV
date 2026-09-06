<template>
  <div class="gallery-workspace">
    <!-- Top Filter & Action Bar -->
    <header class="gallery-toolbar">
      <div class="folder-info" @click="openFolder">
        <span class="icon"><Icon name="folder" /></span>
        <span class="path">{{ currentFolder || '출력 폴더를 선택하세요' }}</span>
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
        <button class="icon-btn" @click="loadImages(true)" title="Refresh"><Icon name="refresh" /></button>
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
          <video v-if="isVideo(img)" class="gallery-media" :src="mediaUrl(img)"
            muted preload="metadata" playsinline />
          <div v-else-if="isAudio(img)" class="audio-card">
            <span class="audio-icon"><Icon name="music" /></span>
            <span class="audio-name">{{ filenameOf(img) }}</span>
            <audio :src="mediaUrl(img)" controls preload="metadata" @click.stop />
          </div>
          <img v-else :src="cardImageUrl(img)" loading="lazy" />
          <span v-if="mediaKind(img) !== 'image' || isAnimated(img)" class="media-kind-badge">
            {{ mediaLabel(img) }}
          </span>
          <div class="card-hover-actions">
            <button class="tiny-btn" @click.stop="quickAction('add_favorite', img)"><Icon name="star" /></button>
            <button v-if="isImage(img)" class="tiny-btn" @click.stop="quickAction('copy_to_clipboard', img)"><Icon name="clipboard" /></button>
          </div>
        </div>
      </div>
      <div class="load-more-info" v-if="visibleCount < (exifFiltered ? filteredImages.length : images.length)">
        {{ visibleCount }} / {{ exifFiltered ? filteredImages.length : images.length }} — 스크롤하여 더 보기
      </div>
      
      <div v-if="isLoading" class="empty-placeholder">
        <div class="spinner"></div>
        <p>Loading...</p>
      </div>
      <div v-else-if="images.length === 0" class="empty-placeholder">
        <div class="icon"><Icon name="video" /></div>
        <h2>갤러리가 비어 있습니다</h2>
        <p>이 폴더에는 볼 수 있는 이미지가 없습니다</p>
      </div>
    </section>

    <!-- 이미지 확대 뷰 (풀스크린 오버레이) -->
    <transition name="fade">
      <div v-if="largeView" class="large-view-overlay" @mousedown.self="closeLargeView">
        <div class="large-view-panel">
          <div class="large-view-header">
            <span class="large-filename">{{ largeView.filename }}</span>
            <div class="large-actions">
              <button class="lv-btn" @click="editFilename"><Icon name="pencil" /> 이름 변경</button>
              <button v-if="isImage(largeView.path) && largeView.source !== 'comfyui'" class="lv-btn save" @click="saveExif"><Icon name="save" /> EXIF 저장</button>
              <button v-if="isImage(largeView.path)" class="lv-btn" @click="action('send_to_i2i', { path: largeView.path })">I2I</button>
              <button v-if="isImage(largeView.path)" class="lv-btn" @click="action('send_to_inpaint', { path: largeView.path })">인페인트</button>
              <button v-if="isImage(largeView.path)" class="lv-btn" @click="action('send_to_editor', { path: largeView.path })">에디터</button>
              <button class="lv-btn" @click="quickAction('add_favorite', largeView.path)"><Icon name="star" /> 즐겨찾기</button>
              <button v-if="isImage(largeView.path)" class="lv-btn accent" :disabled="largeView.can_apply === false" @click="sendExifToT2I">프롬프트 사용</button>
              <button class="lv-close" @click="closeLargeView"><Icon name="close" /></button>
            </div>
          </div>
          <div class="large-view-body">
            <div class="large-img-area">
              <video v-if="isVideo(largeView.path)" :src="mediaUrl(largeView.path)" controls autoplay playsinline />
              <audio v-else-if="isAudio(largeView.path)" :src="mediaUrl(largeView.path)" controls autoplay />
              <img v-else :src="mediaUrl(largeView.path, true)" />
            </div>
            <div class="large-exif">
              <div class="meta-row"><span>종류</span><p>{{ largeView.mediaType || mediaLabel(largeView.path) }}</p></div>
              <div class="meta-row"><span>크기</span><p>{{ largeView.size }}</p></div>
              <div class="meta-row path-row"><span>경로</span><p>{{ largeView.path }}</p></div>
              <div v-if="largeView.prompt" class="meta-block">
                <label>프롬프트</label>
                <div class="code-box" :class="{ editable: largeView.source !== 'comfyui' }" :contenteditable="largeView.source !== 'comfyui'" @blur="onExifEdit($event, 'prompt')">{{ largeView.prompt }}</div>
              </div>
              <div v-if="largeView.negative" class="meta-block mt-8">
                <label class="danger">네거티브</label>
                <div class="code-box">{{ largeView.negative }}</div>
              </div>
              <div v-if="largeView.raw && !largeView.prompt && !largeView.raw_prompt && !largeView.raw_workflow" class="meta-block">
                <label>원본</label>
                <div class="code-box">{{ largeView.raw }}</div>
              </div>
              <div v-if="largeViewParams" class="meta-block mt-8">
                <label>파라미터</label>
                <div class="code-box params">{{ largeViewParams }}</div>
              </div>
              <ComfyMetadataDetails :data="largeView" />
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Slide-out EXIF Panel (간단 사이드바 — 하위호환) -->
    <transition name="slide">
      <aside v-if="exifData && !largeView && showMetadata" class="exif-sidebar">
        <div class="exif-close" @click="exifData = null"><Icon name="arrow-right" /></div>
        <div class="exif-content">
          <div class="exif-preview" @click="largeView = exifData">
            <video v-if="isVideo(exifData.path)" :src="mediaUrl(exifData.path)" muted preload="metadata" playsinline />
            <div v-else-if="isAudio(exifData.path)" class="sidebar-audio-preview">
              <span><Icon name="music" /></span>
              <audio :src="mediaUrl(exifData.path)" controls preload="metadata" @click.stop />
            </div>
            <img v-else :src="mediaUrl(exifData.path)" />
            <div class="click-hint">클릭하여 확대</div>
          </div>
          <div class="exif-meta">
            <h3>메타데이터</h3>
            <div class="meta-row"><span>파일</span><p>{{ exifData.filename }}</p></div>
            <div class="meta-row"><span>종류</span><p>{{ exifData.mediaType || mediaLabel(exifData.path) }}</p></div>
            <div class="meta-row"><span>크기</span><p>{{ exifData.size }}</p></div>

            <div v-if="exifData.prompt" class="meta-block">
              <label>프롬프트</label>
              <div class="code-box">{{ exifData.prompt }}</div>
            </div>
            <div v-if="exifData.negative" class="meta-block mt-12">
              <label class="danger">네거티브</label>
              <div class="code-box">{{ exifData.negative }}</div>
            </div>
            <div v-if="exifData.params" class="meta-block mt-12">
              <label>파라미터</label>
              <div class="params-grid">
                <div class="param-line" v-if="exifData.params.generation"><span class="pl">생성</span><span>{{ exifData.params.generation }}</span></div>
                <div class="param-line" v-if="exifData.params.core"><span class="pl">기본</span><span>{{ exifData.params.core }}</span></div>
                <div class="param-line" v-if="exifData.params.model"><span class="pl">모델</span><span>{{ exifData.params.model }}</span></div>
                <div class="param-line" v-if="exifData.params.hires"><span class="pl">고해상도</span><span>{{ exifData.params.hires }}</span></div>
                <div class="param-line" v-if="exifData.params.extensions"><span class="pl">확장</span><span>{{ exifData.params.extensions }}</span></div>
                <div class="param-line" v-if="exifData.params.other"><span class="pl">기타</span><span>{{ exifData.params.other }}</span></div>
              </div>
            </div>
            <div v-else-if="sidebarParams" class="meta-block mt-12">
              <label>파라미터</label>
              <div class="code-box params">{{ sidebarParams }}</div>
            </div>
            <ComfyMetadataDetails :data="exifData" />
          </div>
          <div v-if="isImage(exifData.path)" class="exif-footer">
            <button class="main-apply-btn" :disabled="exifData.can_apply === false" @click="sendExifToT2I">T2I에서 사용</button>
            <div class="grid-2 mt-8">
              <button class="mini-action" @click="action('send_to_i2i', { path: exifData.path })">I2I</button>
              <button class="mini-action" @click="action('send_to_inpaint', { path: exifData.path })">인페인트</button>
            </div>
          </div>
        </div>
      </aside>
    </transition>

    <!-- Context Menu -->
    <transition name="pop">
      <div v-if="ctxMenu.show" class="modern-ctx-menu" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
        <div class="ctx-item" @click="ctx('add_favorite')"><Icon name="star" /> 즐겨찾기 추가</div>
        <div class="ctx-item" @click="ctx('gallery_load_exif')"><Icon name="clipboard" /> 정보 보기</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="ctx('send_to_i2i')"><Icon name="image" /> I2I로 보내기</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="ctx('send_to_inpaint')"><Icon name="palette" /> 인페인트로 보내기</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="ctx('send_to_editor')"><Icon name="pencil" /> 에디터로 보내기</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="sendToCompare('before')"><Icon name="search" /> 비교 (이전)</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="sendToCompare('after')"><Icon name="search" /> 비교 (이후)</div>
        <div v-if="isImage(ctxMenu.path)" class="ctx-item" @click="ctxAdetailer"><Icon name="target" /> ADetailer</div>
        <div class="ctx-separator"></div>
        <div class="ctx-item delete" @click="ctx('delete_image')"><Icon name="trash" /> 완전 삭제</div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onActivated, onMounted, onUnmounted, nextTick } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import { mediaUrl, thumbnailUrl } from '../utils/media.js'
import type { ActionName } from '../types/bridge'
import ComfyMetadataDetails from '../components/ComfyMetadataDetails.vue'

import { computed } from 'vue'

interface ExifParams {
  generation?: string
  core?: string
  model?: string
  hires?: string
  extensions?: string
  other?: string
  [k: string]: any
}
interface ExifData {
  source?: string
  path: string
  filename: string
  mediaType?: string
  size?: string
  prompt?: string
  negative?: string
  raw?: string
  params?: ExifParams
  [k: string]: any
}
interface CtxMenu {
  show: boolean
  x: number
  y: number
  path: string
}
interface CacheEntry {
  images: string[]
  timestamp: number
}

const images = ref<string[]>([])
const currentFolder = ref('')
const visibleCount = ref(40)

type MediaKind = 'image' | 'video' | 'audio'
const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'mkv', 'm4v', 'avi', 'ogv'])
const AUDIO_EXTENSIONS = new Set(['wav', 'mp3', 'ogg', 'flac', 'm4a', 'aac', 'opus'])
const ANIMATED_EXTENSIONS = new Set(['gif', 'apng', 'webp'])

function mediaExtension(path: string): string {
  const clean = String(path || '').split(/[?#]/, 1)[0]
  const filename = clean.replace(/\\/g, '/').split('/').pop() || ''
  const dot = filename.lastIndexOf('.')
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : ''
}

function mediaKind(path: string): MediaKind {
  const ext = mediaExtension(path)
  if (VIDEO_EXTENSIONS.has(ext)) return 'video'
  if (AUDIO_EXTENSIONS.has(ext)) return 'audio'
  return 'image'
}

const isVideo = (path: string) => mediaKind(path) === 'video'
const isAudio = (path: string) => mediaKind(path) === 'audio'
const isImage = (path: string) => mediaKind(path) === 'image'
const isAnimated = (path: string) => ANIMATED_EXTENSIONS.has(mediaExtension(path))
const filenameOf = (path: string) => String(path || '').replace(/\\/g, '/').split('/').pop() || path
const mediaLabel = (path: string) => {
  const kind = mediaKind(path)
  if (kind === 'video') return 'VIDEO'
  if (kind === 'audio') return 'AUDIO'
  return isAnimated(path) ? 'ANIMATED' : 'IMAGE'
}
const cardImageUrl = (path: string) => isAnimated(path)
  ? mediaUrl(path)
  : thumbnailUrl(path, thumbSize.value * thumbPixelRatio)

// 썸네일 크기 — localStorage 영속, 100~380px
const thumbSize = ref(parseInt(window.localStorage.getItem('gallery_thumb_size') || '200'))
const thumbPixelRatio = Math.min(2, Math.max(1, window.devicePixelRatio || 1))
watch(thumbSize, (v) => {
  window.localStorage.setItem('gallery_thumb_size', String(v))
})

const pagedImages = computed(() => images.value.slice(0, visibleCount.value))

// largeView에서 Parameters 라인 추출
const largeViewParams = computed(() => {
  if (!largeView.value?.raw) return ''
  const match = largeView.value.raw.match(/Steps:.*$/m)
  return match ? match[0] : ''
})
const sidebarParams = computed(() => {
  if (!exifData.value?.raw) return ''
  const match = exifData.value.raw.match(/Steps:.*$/m)
  return match ? match[0] : ''
})

// EXIF 검색
const exifSearch = ref('')
const exifFiltered = ref(false)
const exifSearching = ref(false)
const filteredImages = ref<string[]>([])
const exifCache = ref<Record<string, string>>({})  // path → exif text

const displayImages = computed(() => {
  const source = exifFiltered.value ? filteredImages.value : images.value
  return source.slice(0, visibleCount.value)
})

async function runExifSearch() {
  const query = exifSearch.value.trim().toLowerCase()
  if (!query) { clearExifSearch(); return }
  exifSearching.value = true

  const backend: any = await getBackend()
  // 비이미지는 Pillow EXIF 슬롯에 보내지 않는다. 파일명/미디어 유형만 검색한다.
  for (const media of images.value.filter(img => !isImage(img))) {
    exifCache.value[media] = `${filenameOf(media)} ${mediaLabel(media)}`.toLowerCase()
  }
  const toCheck = images.value.filter(img => isImage(img) && !(img in exifCache.value))

  // 캐시에 없는 이미지의 EXIF 로드
  let loaded = 0
  const batchSize = 20
  for (let i = 0; i < toCheck.length; i += batchSize) {
    const batch = toCheck.slice(i, i + batchSize)
    await Promise.all(batch.map((img: string) => new Promise<void>(resolve => {
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
    loaded += batch.length
  }

  // 필터
  filteredImages.value = images.value.filter(img => {
    const text = exifCache.value[img] || ''
    return text.includes(query)
  })
  exifFiltered.value = true
  exifSearching.value = false
  visibleCount.value = 40
}

function clearExifSearch() {
  exifSearch.value = ''
  exifFiltered.value = false
  filteredImages.value = []
  visibleCount.value = 40
}
const galleryContentRef = ref<HTMLElement | null>(null)

/**
 * 넘칠 때까지 채운다.
 *
 * '더 보기'는 스크롤 이벤트로만 발동한다. 그런데 첫 40장이 화면에 다 들어가면
 * (넓은 모니터 + 작은 썸네일) 컨테이너가 넘치지 않아 스크롤 자체가 생기지 않고,
 * "N / M — 스크롤하여 더 보기" 만 떠 있는 채 영영 안 채워졌다. 목록·크기가 바뀔
 * 때마다 컨테이너가 넘칠 때까지 30장씩 더 보인다. 스크롤이 생기는 순간 멈춘다.
 */
function fillViewport() {
  const el = galleryContentRef.value
  const total = exifFiltered.value ? filteredImages.value.length : images.value.length
  if (!el || visibleCount.value >= total) return
  // keep-alive 로 떼어졌거나 아직 레이아웃이 없으면 높이가 0 이라 '안 찼다' 로 읽힌다 — 그때 늘리면 전부 펼쳐진다
  if (!el.isConnected || el.clientHeight === 0) return
  // 1) 기하 추정 — 썸네일이 뜨기 전엔 카드 높이가 0 이라 scrollHeight 로는 알 수 없다.
  //    열 수 × (뷰포트를 덮는 행 수 + 1) 만큼은 먼저 보인다.
  const cell = Math.max(60, thumbSize.value)
  const need = Math.min(total, Math.max(1, Math.floor(el.clientWidth / cell)) * (Math.ceil(el.clientHeight / cell) + 1))
  if (need > visibleCount.value) { visibleCount.value = need; return }
  // 2) 실측 — 썸네일이 다 떴는데도 안 넘치면(가로로 긴 그림들) 한 페이지 더. 그리드가 자라면 관찰자가 다시 부른다.
  if (el.scrollHeight <= el.clientHeight + 1) visibleCount.value = Math.min(total, visibleCount.value + 30)
}
let _fillObserver: ResizeObserver | null = null
onMounted(() => {
  const el = galleryContentRef.value
  if (typeof ResizeObserver === 'undefined' || !el) return
  // 콜백 안에서 바로 늘리면 같은 프레임에 크기가 또 바뀌어 'ResizeObserver loop' 경고가 난다 — 다음 프레임에
  _fillObserver = new ResizeObserver(() => { requestAnimationFrame(fillViewport) })
  _fillObserver.observe(el)                                              // 창 크기
  if (el.firstElementChild) _fillObserver.observe(el.firstElementChild)  // 그리드 — 썸네일이 뜨며 자란다
})
onUnmounted(() => { _fillObserver?.disconnect(); _fillObserver = null })
watch([images, filteredImages, exifFiltered, thumbSize], () => { fillViewport() }, { flush: 'post' })
const sortBy = ref('date')
const sortOptions = [{label: '날짜', val: 'date'}, {label: '이름', val: 'name'}]
const ctxMenu = ref<CtxMenu>({ show: false, x: 0, y: 0, path: '' })
const exifData = ref<ExifData | null>(null)
const largeView = ref<ExifData | null>(null)
const isLoading = ref(false)
const showMetadata = ref(window.localStorage.getItem('galleryShowMetadata') !== 'false')
// Settings에서 변경 시 실시간 반영 — interval ID 보관 후 unmount 시 정리
const _showMetaTimer = setInterval(() => {
  const v = window.localStorage.getItem('galleryShowMetadata') !== 'false'
  if (v !== showMetadata.value) showMetadata.value = v
}, 500)

// ── 캐시 시스템 ──
const _cache = new Map<string, CacheEntry>()  // folder → { images, timestamp }
const CACHE_TTL = 5 * 60 * 1000  // 5분

async function editFilename() {
  if (!largeView.value) return
  const newName = window.prompt('파일 이름 변경:', largeView.value.filename)
  if (newName && newName !== largeView.value.filename) {
    const backend: any = await getBackend()
    if (backend.renameFile) {
      backend.renameFile(largeView.value.path, newName, (json: string) => {
        try {
          const r = JSON.parse(json)
          if (r.ok) { largeView.value!.filename = newName; loadImages() }
          else alert(r.error || '이름 변경 실패')
        } catch {}
      })
    }
  }
}
function onExifEdit(e: FocusEvent, field: string) {
  if (largeView.value && largeView.value.source !== 'comfyui') largeView.value[field] = (e.target as HTMLElement).textContent
}
async function saveExif() {
  if (!largeView.value || largeView.value.source === 'comfyui') return
  const backend: any = await getBackend()
  if (!backend.saveImageExif) return
  // prompt + negative + raw 에서 A1111 형식으로 재구성
  const parts = []
  if (largeView.value.prompt) parts.push(largeView.value.prompt)
  if (largeView.value.negative) parts.push('Negative prompt: ' + largeView.value.negative)
  // raw에서 Steps: 이후 파라미터 라인 추출
  const rawMatch = (largeView.value.raw || '').match(/Steps:.*$/m)
  if (rawMatch) parts.push(rawMatch[0])
  const newParams = parts.join('\n')
  backend.saveImageExif(largeView.value.path, newParams, (json: string) => {
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
    const cached = _cache.get(cacheKey)!
    if (Date.now() - cached.timestamp < CACHE_TTL) {
      images.value = cached.images
      return
    }
  }

  isLoading.value = true
  const backend: any = await getBackend()
  if (backend.requestGalleryImages) {
    backend.requestGalleryImages(currentFolder.value)
  } else if (backend.getGalleryImages) {
    backend.getGalleryImages(currentFolder.value, (json: string) => {
      try {
        applyGalleryImages(currentFolder.value, JSON.parse(json))
      } catch {}
      isLoading.value = false
    })
  } else {
    isLoading.value = false
  }
}

function applyGalleryImages(folder: string, list: unknown) {
  if (folder !== currentFolder.value || !Array.isArray(list)) return
  images.value = list as string[]
  visibleCount.value = Math.min(Math.max(40, visibleCount.value), Math.max(40, images.value.length))
  const cacheKey = folder || '__default__'
  _cache.set(cacheKey, { images: images.value, timestamp: Date.now() })
  isLoading.value = false
}

function sortImages() {
  if (sortBy.value === 'name') {
    images.value.sort((a, b) => a.split('/').pop()!.localeCompare(b.split('/').pop()!))
  } else {
    loadImages(true)  // DATE 정렬은 서버에서 새로 가져옴
  }
}

function onGalleryScroll(e: Event) {
  const el = e.target as HTMLElement
  const total = exifFiltered.value ? filteredImages.value.length : images.value.length
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
    if (visibleCount.value < total) {
      visibleCount.value = Math.min(visibleCount.value + 30, total)
    }
  }
}

function closeLargeView() {
  largeView.value = null
  // metadata OFF면 사이드바도 닫기
  if (!showMetadata.value) exifData.value = null
}

const openFolder = () => requestAction('gallery_open_folder')
const viewImage = async (path: string) => {
  const basic: ExifData = {
    path,
    filename: filenameOf(path),
    mediaType: mediaLabel(path),
    size: '—',
  }
  if (!isImage(path)) {
    largeView.value = basic
    exifData.value = basic
    return
  }
  const backend: any = await getBackend()
  if (!backend.getImageExif) {
    largeView.value = basic
    exifData.value = basic
    return
  }
  backend.getImageExif(path, (json: string) => {
    try {
      const d = JSON.parse(json)
      const data = d?.error ? basic : { ...basic, ...d, mediaType: basic.mediaType }
      largeView.value = data  // 확대 뷰
      exifData.value = data   // 사이드바 데이터 (showMetadata로 표시 여부 제어)
    } catch {
      largeView.value = basic
      exifData.value = basic
    }
  })
}

function showMenu(e: MouseEvent, path: string) { ctxMenu.value = { show: true, x: e.clientX, y: e.clientY, path } }
function ctx(actionName: ActionName | 'gallery_load_exif') {
  const path = ctxMenu.value.path
  if (actionName === 'gallery_load_exif') viewImage(path)
  else requestAction(actionName, { path })
  // 삭제 시 즉시 목록에서 제거 (스크롤 유지)
  if (actionName === 'delete_image') {
    images.value = images.value.filter(img => img !== path)
    // 캐시도 업데이트
    const cacheKey = currentFolder.value || '__default__'
    if (_cache.has(cacheKey)) _cache.get(cacheKey)!.images = images.value
  }
  ctxMenu.value.show = false
}
const quickAction = (name: ActionName, path: string) => requestAction(name, { path })
const sendToCompare = (slot: string) => { requestAction('send_to_compare', { path: ctxMenu.value.path, slot }); ctxMenu.value.show = false }
const ctxAdetailer = () => { requestAction('run_adetailer_single', { path: ctxMenu.value.path, settings: { ad_model: 'face_yolov8n.pt', ad_confidence: 0.3, ad_denoise: 0.4 } }); ctxMenu.value.show = false }
const sendExifToT2I = () => {
  const data = largeView.value || exifData.value
  if (data && data.can_apply !== false) requestAction('gallery_send_exif_to_t2i', { exif: data.raw || '', path: data.path, metadata: data })
}
const action = (name: ActionName, payload: Record<string, any> = {}) => requestAction(name, payload)
const hideMenu = () => ctxMenu.value.show = false

onMounted(async () => {
  document.addEventListener('click', hideMenu)
  _galleryImagesUnsub = onBackendEvent('galleryImagesReady', (json: string) => {
    try {
      const payload = JSON.parse(json)
      applyGalleryImages(payload.folder || '', payload.files)
    } catch {}
  })
  // 마지막 폴더 경로 로드 후 이미지 로드
  const bk: any = await getBackend()
  if (bk.getLastGalleryFolder) {
    bk.getLastGalleryFolder((f: string) => {
      if (f) currentFolder.value = f
      loadImages()  // 경로 설정 후 로드
    })
  } else {
    loadImages()
  }
  _galleryFolderUnsub = onBackendEvent('galleryFolderLoaded', (f: string) => { currentFolder.value = f; visibleCount.value = 40; loadImages(true) })
})
onActivated(() => { loadImages(true); fillViewport() })
// onBackendEvent disconnect 핸들 — unmount 시 정리
let _galleryFolderUnsub: (() => void) | null = null
let _galleryImagesUnsub: (() => void) | null = null
onUnmounted(() => {
  document.removeEventListener('click', hideMenu)
  if (_showMetaTimer) clearInterval(_showMetaTimer)
  if (_galleryFolderUnsub) _galleryFolderUnsub()
  if (_galleryImagesUnsub) _galleryImagesUnsub()
})
</script>

<style scoped>

.folder-info { display: flex; align-items: center; gap: 10px; cursor: pointer; opacity: 0.7; transition: var(--transition); }
.folder-info:hover { opacity: 1; }
/* 경로는 있는 그대로 — 대문자로 밀면 실제와 다른 문자열이 된다 */
.folder-info .path { font-size: var(--fs-meta); color: var(--text-muted); max-width: 400px; overflow: hidden; text-overflow: ellipsis; }

.gallery-card img, .gallery-card > video { width: 100%; display: block; transition: var(--transition); }
/* contain 여백(레터박스)은 카드 안의 '파인 면'이라 --bg-primary — 라이트에서도 카드보다 한 단 어둡다 */
.gallery-card > video { min-height: 120px; max-height: 320px; object-fit: contain; background: var(--bg-primary); }

.gallery-card:hover img, .gallery-card:hover > video { filter: brightness(0.7); }
/* 원래 푸른기 도는 고정 어두운 그라디언트였다 — 테마를 안 타서 라이트에서 이 카드만 검게 남는다.
   기울기(밝은 면 → 파인 면)만 살려 토큰으로 옮겼다. */
.audio-card { min-height: 128px; padding: 20px 12px 14px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; background: linear-gradient(145deg, var(--bg-card), var(--bg-primary)); }
.audio-icon { font-size: 34px; color: var(--accent); }
.audio-name { width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; font-size: var(--fs-label); color: var(--text-muted); }
.audio-card audio { width: 100%; height: 32px; }
/* 흰 글자를 그대로 둔다: 배지 바탕이 테마를 안 타는 검정 오버레이라 --text-primary 로 바꾸면 라이트에서 검정 위 검정이 된다 */
.media-kind-badge { position: absolute; left: 8px; top: 8px; padding: 3px 7px; border-radius: 999px; background: rgba(0,0,0,0.72); color: #fff; font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; pointer-events: none; }

.exif-close { position: absolute; top: 20px; left: -20px; width: 40px; height: 40px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transform: rotate(0deg); }

.exif-preview { width: 100%; aspect-ratio: 1; overflow: hidden; }
.exif-preview img, .exif-preview video { width: 100%; height: 100%; object-fit: contain; background: var(--bg-primary); }
.sidebar-audio-preview { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px; background: var(--bg-primary); color: var(--accent); font-size: 42px; }
.sidebar-audio-preview audio { width: 85%; }

.meta-row p { font-size: 12px; font-weight: var(--fw-bold); color: var(--text-primary); }
.meta-row.path-row { align-items: flex-start; }
.meta-row.path-row p { max-width: 250px; word-break: break-all; text-align: right; font-size: var(--fs-label); }

.meta-block label { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--accent); margin-bottom: 8px; }
.code-box { background: var(--bg-input); padding: 12px; border-radius: 8px; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.6; color: var(--text-secondary); word-break: break-all; }

.params-grid { background: var(--bg-input); border-radius: 8px; padding: 8px 12px; }
.param-line { display: flex; align-items: baseline; gap: 8px; padding: 3px 0; font-size: 11px; color: var(--text-secondary); border-bottom: 1px solid rgba(255,255,255,0.03); font-family: 'Consolas', monospace; }
.param-line:last-child { border-bottom: none; }
.pl { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--accent); letter-spacing: 0; min-width: 45px; flex-shrink: 0; }

.mini-action { flex: 1; height: 36px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); font-size: var(--fs-label); font-weight: var(--fw-bold); cursor: pointer; }

.ctx-item.delete { color: var(--state-alert-fg); }

/* 채움이라 --state-ok(글자용 -fg 아님). 그 위 글자는 흰색 고정 —
   상태 채움색 자체가 '흰 글자와 4.5:1' 기준으로 잡힌 값이고, --text-primary 는 라이트에서 검정이 된다. */
.lv-btn.save { background: var(--state-ok); color: #FFFFFF; border: none; }

.large-img-area img, .large-img-area video { max-width: 100%; max-height: 100%; object-fit: contain; }
.large-img-area audio { width: min(620px, 90%); }

.code-box.editable { cursor: text; border: 1px solid transparent; }
.code-box.editable:focus { border-color: var(--accent-dim); outline: none; }

.exif-preview { position: relative; cursor: pointer; }

.spinner { width: 32px; height: 32px; border: 3px solid var(--rule); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 12px; }
@keyframes spin { to { transform: rotate(360deg); } }

</style>
