<template>
  <div class="pnginfo-view">
    <!-- 상단 서브탭 -->
    <div class="sub-tabs">
      <button class="sub-tab" :class="{ active: subTab === 'info' }" @click="subTab = 'info'">📄 PNG Info</button>
      <button class="sub-tab" :class="{ active: subTab === 'compare' }" @click="subTab = 'compare'">🔍 Compare</button>
    </div>

    <!-- PNG Info 탭 -->
    <div v-if="subTab === 'info'" class="tab-content info-layout">
      <div class="image-area" @dragover.prevent @drop.prevent="onDrop" @dblclick="openFile">
        <img v-if="imagePath" :src="'file:///' + imagePath" class="preview-img" />
        <div v-else class="drop-hint">
          <div class="icon">📄</div>
          <div>이미지를 드래그하거나 더블클릭</div>
        </div>
      </div>
      <div class="info-panel">
        <div class="info-header">
          <h3>PNG Info</h3>
          <button class="btn" @click="openFile">📂 열기</button>
          <button class="btn" @click="copyAll" v-if="exif.raw">📋 복사</button>
          <button class="btn" @click="sendToCompare" v-if="imagePath">🔍 비교로</button>
        </div>
        <div class="info-body" v-if="exif.raw">
          <div v-if="exif.prompt" class="section"><label>Prompt</label><pre>{{ exif.prompt }}</pre></div>
          <div v-if="exif.negative" class="section"><label>Negative</label><pre>{{ exif.negative }}</pre></div>
          <div v-if="exif.params_line" class="section"><label>Parameters</label><pre>{{ exif.params_line }}</pre></div>
          <div v-if="!exif.prompt" class="section"><label>Raw</label><pre>{{ exif.raw }}</pre></div>
          <div class="action-bar">
            <button class="btn accent" @click="sendPrompt">📤 T2I 전송</button>
            <button class="btn" @click="sendGenerate">⚡ 즉시 생성</button>
            <button class="btn" @click="action('send_to_i2i', { path: imagePath })">I2I</button>
            <button class="btn" @click="action('send_to_inpaint', { path: imagePath })">Inpaint</button>
            <button class="btn" @click="action('send_to_editor', { path: imagePath })">Editor</button>
            <button class="btn" @click="action('add_favorite', { path: imagePath })">⭐</button>
          </div>
        </div>
        <div v-else class="info-empty">이미지를 선택하면 메타데이터가 표시됩니다</div>
      </div>
    </div>

    <!-- Compare 탭 -->
    <div v-if="subTab === 'compare'" class="tab-content compare-layout">
      <div class="compare-controls">
        <div class="cmp-slot">
          <span class="cmp-label">BEFORE</span>
          <button class="btn" @click="loadCompareImage('before')">📂 열기</button>
          <span class="cmp-name">{{ beforeName || '없음' }}</span>
        </div>
        <div class="cmp-slot">
          <span class="cmp-label">AFTER</span>
          <button class="btn" @click="loadCompareImage('after')">📂 열기</button>
          <span class="cmp-name">{{ afterName || '없음' }}</span>
        </div>
      </div>
      <div class="compare-area">
        <CompareSlider v-if="compareBefore && compareAfter"
          :before-src="'file:///' + compareBefore"
          :after-src="'file:///' + compareAfter"
        />
        <div v-else class="compare-hint">
          <div class="icon">🔍</div>
          <p>두 이미지를 선택하면 비교 슬라이더가 표시됩니다</p>
          <p class="sub">우클릭 메뉴의 "비교로 보내기"로도 이미지를 추가할 수 있습니다</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import CompareSlider from '../components/CompareSlider.vue'

const subTab = ref('info')
const imagePath = ref('')
const exif = ref({})

// Compare
const compareBefore = ref('')
const compareAfter = ref('')
const beforeName = ref('')
const afterName = ref('')

async function loadImage(path) {
  imagePath.value = path
  const backend = await getBackend()
  if (backend.getImageExif) {
    backend.getImageExif(path, (json) => { try { exif.value = JSON.parse(json) } catch {} })
  }
}

function onDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file?.path) loadImage(file.path.replace(/\\/g, '/'))
  else {
    const path = e.dataTransfer?.getData('text/plain')
    if (path && path.includes('/')) loadImage(path)
  }
}

function openFile() { requestAction('open_png_info_file') }
function copyAll() { navigator.clipboard?.writeText(exif.value.raw || '') }
function sendPrompt() { requestAction('pnginfo_send_prompt', { prompt: exif.value.prompt || '', negative: exif.value.negative || '' }) }
function sendGenerate() { requestAction('pnginfo_generate', exif.value) }
function action(name, payload = {}) { requestAction(name, payload) }

function sendToCompare() {
  if (!compareBefore.value) {
    compareBefore.value = imagePath.value
    beforeName.value = imagePath.value.split('/').pop()
  } else {
    compareAfter.value = imagePath.value
    afterName.value = imagePath.value.split('/').pop()
  }
  subTab.value = 'compare'
}

async function loadCompareImage(slot) {
  // Python에서 파일 다이얼로그
  requestAction('open_compare_image', { slot })
}

onMounted(() => {
  onBackendEvent('inpaintImageLoaded', (path) => loadImage(path))
  // 비교 이미지 수신 (우클릭 메뉴 "비교로 보내기" 또는 파일 다이얼로그)
  onBackendEvent('compareImageLoaded', (json) => {
    try {
      const d = JSON.parse(json)
      if (d.slot === 'before') { compareBefore.value = d.path; beforeName.value = d.path.split('/').pop() }
      else { compareAfter.value = d.path; afterName.value = d.path.split('/').pop() }
      subTab.value = 'compare'
    } catch {}
  })
})
</script>

<style scoped>
.pnginfo-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.sub-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.sub-tab {
  flex: 1; padding: 8px; background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-muted); font-size: 11px; font-weight: 700; cursor: pointer; text-align: center;
}
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-content { flex: 1; overflow: hidden; }

/* Info Layout */
.info-layout { display: flex; }
.image-area { flex: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; min-width: 300px; padding: 16px; }
.preview-img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 4px; }
.drop-hint { text-align: center; color: #484848; user-select: none; }
.drop-hint .icon { font-size: 48px; opacity: 0.3; margin-bottom: 12px; }
.info-panel { width: 400px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; }
.info-header { display: flex; align-items: center; gap: 6px; padding: 8px 12px; flex-shrink: 0; }
.info-header h3 { color: #E8E8E8; font-size: 14px; margin: 0; flex: 1; }
.btn { padding: 5px 10px; background: #181818; border: none; border-radius: 4px; color: #787878; font-size: 10px; cursor: pointer; }
.btn:hover { background: #222; color: #E8E8E8; }
.btn.accent { background: #E2B340; color: #000; }
.info-body { flex: 1; overflow-y: auto; padding: 8px 12px; }
.section { margin-bottom: 10px; }
.section label { color: #E2B340; font-size: 11px; font-weight: 600; display: block; margin-bottom: 2px; }
.section pre { color: #B0B0B0; font-size: 11px; white-space: pre-wrap; word-break: break-all; background: #111; padding: 6px 8px; border-radius: 4px; margin: 0; max-height: 150px; overflow-y: auto; }
.action-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 12px; }
.info-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #484848; font-size: 14px; }

/* Compare Layout */
.compare-layout { display: flex; flex-direction: column; }
.compare-controls { display: flex; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.cmp-slot { display: flex; align-items: center; gap: 6px; flex: 1; }
.cmp-label { font-size: 10px; font-weight: 900; color: var(--accent); letter-spacing: 1px; }
.cmp-name { font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.compare-area { flex: 1; position: relative; }
.compare-hint { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-align: center; }
.compare-hint .icon { font-size: 48px; opacity: 0.3; margin-bottom: 12px; }
.compare-hint p { color: #484848; font-size: 13px; }
.compare-hint .sub { font-size: 11px; color: #383838; margin-top: 4px; }
</style>
