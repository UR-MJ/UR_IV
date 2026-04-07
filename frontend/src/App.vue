<template>
  <div class="app">
    <TabBar @tab-changed="onTabChanged" />
    <div class="main">
      <!-- 좌측 패널 (T2I만) -->
      <div class="left-panel" v-if="showLeftPanel">
        <PromptPanel />
        <div class="tools-section">
          <button class="tool-btn" @click="action('save_settings')">💾 저장</button>
          <button class="tool-btn" @click="action('save_preset')">📥 프리셋</button>
          <button class="tool-btn" @click="action('load_preset')">📤 로드</button>
          <button class="tool-btn" @click="action('show_prompt_history')">📋</button>
          <button class="tool-btn" @click="action('open_lora_manager')">LoRA</button>
          <button class="tool-btn" @click="action('open_tag_weight_editor')">⚖</button>
          <button class="tool-btn" @click="action('shuffle')">🔀</button>
          <button class="tool-btn" @click="action('ab_test')">A/B</button>
          <button class="tool-btn" @click="action('random_prompt')">🎲</button>
        </div>
      </div>

      <!-- 중앙 콘텐츠 -->
      <div class="content">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component"
              :image-url="currentImage"
              :resolution="resolution"
              :seed="seed"
              :status="status"
            />
          </keep-alive>
        </router-view>
      </div>

      <!-- 우측 히스토리 (T2I만) -->
      <div class="right-panel" v-if="showLeftPanel">
        <div class="hist-header">
          <span>히스토리</span>
          <span class="hist-count">{{ historyImages.length }}장</span>
        </div>
        <button class="nav-btn" @click="historyScroll(-1)" :disabled="historyPage <= 0">▲</button>
        <div class="hist-grid">
          <div v-for="img in visibleHistory" :key="img" class="hist-item"
            @click="selectHistoryImage(img)"
            @contextmenu.prevent="showHistoryMenu($event, img)"
            :class="{ selected: currentImage === img }"
          >
            <img :src="'file:///' + img" loading="lazy" />
          </div>
        </div>
        <button class="nav-btn" @click="historyScroll(1)"
          :disabled="(historyPage + 1) * 5 >= historyImages.length">▼</button>
        <!-- 우클릭 메뉴 -->
        <div v-if="ctxMenu.show" class="ctx-menu" :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }">
          <div class="ctx-item" @click="ctxAddFavorite">⭐ 즐겨찾기 추가</div>
          <div class="ctx-item" @click="ctxSendI2I">🖼️ I2I로 보내기</div>
          <div class="ctx-item" @click="ctxSendInpaint">🎨 Inpaint로 보내기</div>
          <div class="ctx-item" @click="ctxSendEditor">✏️ Editor로 보내기</div>
          <div class="ctx-item" @click="ctxCopyPath">📋 경로 복사</div>
          <div class="ctx-item delete" @click="ctxDelete">🗑️ 삭제</div>
        </div>
      </div>
    </div>

    <!-- 하단 대기열 -->
    <QueuePanel />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { initBridge, onBackendEvent, getBackend } from './bridge.js'
import { requestAction } from './stores/widgetStore.js'
import PromptPanel from './components/PromptPanel.vue'
import TabBar from './components/TabBar.vue'
import QueuePanel from './components/QueuePanel.vue'

const currentImage = ref('')
const resolution = ref('')
const seed = ref('')
const status = ref('이미지를 생성하세요')
const showLeftPanel = ref(true)
const historyImages = ref([])
const historyPage = ref(0)

// 5개씩 보기
const visibleHistory = computed(() => {
  const start = historyPage.value * 5
  return historyImages.value.slice(start, start + 5)
})

function historyScroll(dir) {
  const maxPage = Math.max(0, Math.ceil(historyImages.value.length / 5) - 1)
  historyPage.value = Math.max(0, Math.min(maxPage, historyPage.value + dir))
}

// 우클릭 메뉴
const ctxMenu = ref({ show: false, x: 0, y: 0, path: '' })

function showHistoryMenu(e, path) {
  ctxMenu.value = { show: true, x: e.layerX, y: e.layerY, path }
}
function hideCtxMenu() { ctxMenu.value.show = false }
function ctxAddFavorite() { action('add_favorite', { path: ctxMenu.value.path }); hideCtxMenu() }
function ctxSendI2I() { action('send_to_i2i', { path: ctxMenu.value.path }); hideCtxMenu() }
function ctxSendInpaint() { action('send_to_inpaint', { path: ctxMenu.value.path }); hideCtxMenu() }
function ctxSendEditor() { action('send_to_editor', { path: ctxMenu.value.path }); hideCtxMenu() }
function ctxCopyPath() {
  navigator.clipboard?.writeText(ctxMenu.value.path)
  hideCtxMenu()
}
function ctxDelete() { action('delete_image', { path: ctxMenu.value.path }); hideCtxMenu() }

function selectHistoryImage(path) {
  // Vue 뷰어에서 직접 표시 (Python 윈도우 안 뜸)
  currentImage.value = path
  const img = new Image()
  img.onload = () => {
    resolution.value = `${img.naturalWidth} × ${img.naturalHeight}`
  }
  img.src = 'file:///' + path
}

function onTabChanged(tabName) {
  showLeftPanel.value = tabName === 't2i'
  hideCtxMenu()
}

function action(name, payload = {}) {
  requestAction(name, payload)
}

async function loadHistory() {
  const backend = await getBackend()
  if (backend.getGalleryImages) {
    backend.getGalleryImages('', (json) => {
      try { historyImages.value = JSON.parse(json).slice(0, 100) } catch {}
    })
  }
}

// 클릭 시 우클릭 메뉴 닫기
function onGlobalClick() { hideCtxMenu() }
onMounted(() => document.addEventListener('click', onGlobalClick))
onUnmounted(() => document.removeEventListener('click', onGlobalClick))

onMounted(async () => {
  await initBridge()
  loadHistory()

  onBackendEvent('imageGenerated', (data) => {
    const parsed = JSON.parse(data)
    currentImage.value = parsed.path
    resolution.value = `${parsed.width} × ${parsed.height}`
    seed.value = String(parsed.seed)
    status.value = ''
    if (parsed.path) {
      historyImages.value.unshift(parsed.path)
      if (historyImages.value.length > 100) historyImages.value.pop()
      historyPage.value = 0
    }
  })
  onBackendEvent('generationStarted', () => { status.value = '생성 중...' })
  onBackendEvent('generationError', (msg) => { status.value = `오류: ${msg}` })
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0A0A0A; }
body { color: #E8E8E8; font-family: 'Pretendard', 'Malgun Gothic', 'Segoe UI', sans-serif; }
.app { width: 100%; height: 100%; display: flex; flex-direction: column; }
.main { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.left-panel {
  width: 340px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
}
.tools-section {
  display: flex; flex-wrap: wrap; gap: 3px; padding: 4px 6px;
  background: #0A0A0A; flex-shrink: 0;
}
.tool-btn {
  padding: 4px 8px; background: #181818; border: none; border-radius: 4px;
  color: #585858; font-size: 10px; cursor: pointer; white-space: nowrap;
}
.tool-btn:hover { background: #222; color: #E8E8E8; }
.content { flex: 1; overflow: hidden; min-width: 0; }

/* 히스토리 패널 */
.right-panel {
  width: 200px; flex-shrink: 0; background: #0D0D0D;
  display: flex; flex-direction: column; overflow: hidden;
  position: relative;
}
.hist-header {
  display: flex; justify-content: space-between; padding: 6px 8px; flex-shrink: 0;
}
.hist-header span { color: #585858; font-size: 11px; font-weight: 600; }
.hist-count { color: #484848; }
.nav-btn {
  width: 100%; padding: 4px; background: #131313; border: none;
  color: #484848; font-size: 12px; cursor: pointer; flex-shrink: 0;
}
.nav-btn:hover { background: #1A1A1A; color: #E8E8E8; }
.nav-btn:disabled { opacity: 0.3; cursor: default; }
.hist-grid {
  flex: 1; display: flex; flex-direction: column; gap: 4px; padding: 4px;
  overflow: hidden;
}
.hist-item {
  border-radius: 4px; overflow: hidden; cursor: pointer;
  border: 2px solid transparent; transition: border-color 0.15s; flex-shrink: 0;
}
.hist-item:hover { border-color: #333; }
.hist-item.selected { border-color: #E2B340; }
.hist-item img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }

/* 우클릭 메뉴 */
.ctx-menu {
  position: absolute; background: #1A1A1A; border-radius: 6px;
  padding: 4px; z-index: 100; min-width: 160px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}
.ctx-item {
  padding: 6px 12px; font-size: 12px; color: #B0B0B0; cursor: pointer;
  border-radius: 4px; white-space: nowrap;
}
.ctx-item:hover { background: #222; color: #E8E8E8; }
.ctx-item.delete { color: #E05252; }
.ctx-item.delete:hover { background: #2a1515; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #E2B340; }
</style>
