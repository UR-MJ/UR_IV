<template>
  <div class="batch-view">
    <!-- 배치 처리 -->
    <div class="section">
      <h3>배치 처리</h3>
      <div class="file-drop" @dragover.prevent @drop.prevent="onDropBatch">
        <div v-if="batchFiles.length === 0" class="drop-hint">
          이미지 파일을 드래그하거나
          <button class="link-btn" @click="addBatchFiles">파일 선택</button>
        </div>
        <div v-else class="file-list">
          <div v-for="(f, i) in batchFiles" :key="i" class="file-item">
            {{ f.name || f }}
            <button class="rm-btn" @click="batchFiles.splice(i, 1)">×</button>
          </div>
        </div>
      </div>
      <label class="s-label">작업</label>
      <select v-model="batchOp" class="s-select">
        <option value="resize">리사이즈</option>
        <option value="format">포맷 변환</option>
        <option value="filter">필터 적용</option>
        <option value="watermark">워터마크</option>
      </select>
      <div v-if="batchOp === 'resize'" class="op-settings">
        <label class="s-label">크기</label>
        <div class="row"><input class="s-input" v-model="resizeW" placeholder="W" /><span>×</span><input class="s-input" v-model="resizeH" placeholder="H" /></div>
      </div>
      <div v-if="batchOp === 'format'" class="op-settings">
        <select v-model="formatType" class="s-select"><option>PNG</option><option>JPEG</option><option>WEBP</option></select>
      </div>
      <button class="btn-start" @click="startBatch" :disabled="batchFiles.length === 0">
        배치 시작 ({{ batchFiles.length }}파일)
      </button>
    </div>

    <div class="divider" />

    <!-- 업스케일 -->
    <div class="section">
      <h3>업스케일</h3>
      <div class="file-drop" @dragover.prevent @drop.prevent="onDropUpscale">
        <div v-if="upscaleFiles.length === 0" class="drop-hint">
          이미지 파일을 드래그하거나
          <button class="link-btn" @click="addUpscaleFiles">파일 선택</button>
        </div>
        <div v-else class="file-list">
          <div v-for="(f, i) in upscaleFiles" :key="i" class="file-item">
            {{ f.name || f }}
            <button class="rm-btn" @click="upscaleFiles.splice(i, 1)">×</button>
          </div>
        </div>
      </div>
      <label class="s-label">업스케일러</label>
      <select v-model="upscaler" class="s-select">
        <option v-for="u in upscalers" :key="u" :value="u">{{ u }}</option>
      </select>
      <label class="s-label">배율</label>
      <div class="slider-row">
        <input type="range" min="1" max="4" step="0.5" v-model.number="scaleFactor" />
        <span>{{ scaleFactor }}x</span>
      </div>
      <button class="btn-start" @click="startUpscale" :disabled="upscaleFiles.length === 0">
        업스케일 시작 ({{ upscaleFiles.length }}파일)
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const batchFiles = ref([])
const batchOp = ref('resize')
const resizeW = ref('1024')
const resizeH = ref('1024')
const formatType = ref('PNG')

const upscaleFiles = ref([])
const upscaler = ref('')
const upscalers = ref(['R-ESRGAN 4x+', 'R-ESRGAN 4x+ Anime6B'])
const scaleFactor = ref(2)

onMounted(async () => {
  const backend = await getBackend()
  if (backend.getUpscalers) {
    backend.getUpscalers((json) => {
      try {
        const list = JSON.parse(json)
        if (list.length) { upscalers.value = list; upscaler.value = list[0] }
      } catch {}
    })
  }
})

function onDropBatch(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  batchFiles.value.push(...files.filter(f => f.type.startsWith('image/')))
}
function onDropUpscale(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  upscaleFiles.value.push(...files.filter(f => f.type.startsWith('image/')))
}
function addBatchFiles() { requestAction('open_batch_files') }
function addUpscaleFiles() { requestAction('open_upscale_files') }

function startBatch() {
  requestAction('start_batch', {
    files: batchFiles.value.map(f => f.path || f.name),
    operation: batchOp.value,
    settings: { width: resizeW.value, height: resizeH.value, format: formatType.value },
  })
}
function startUpscale() {
  requestAction('start_upscale', {
    files: upscaleFiles.value.map(f => f.path || f.name),
    upscaler: upscaler.value,
    scale: scaleFactor.value,
  })
}
</script>

<style scoped>
.batch-view { width: 100%; height: 100%; display: flex; overflow-y: auto; }
.section { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; }
.section h3 { color: #E8E8E8; font-size: 14px; margin: 0; }
.divider { width: 1px; background: #1A1A1A; }
.file-drop {
  border: 2px dashed #1A1A1A; border-radius: 6px; min-height: 120px;
  display: flex; align-items: center; justify-content: center; padding: 12px;
}
.drop-hint { color: #484848; font-size: 13px; text-align: center; }
.link-btn { background: none; border: none; color: #E2B340; cursor: pointer; text-decoration: underline; font-size: 13px; }
.file-list { width: 100%; max-height: 150px; overflow-y: auto; }
.file-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px; font-size: 12px; color: #B0B0B0;
}
.rm-btn { background: none; border: none; color: #E05252; cursor: pointer; font-size: 14px; }
.s-label { color: #585858; font-size: 11px; font-weight: 600; }
.s-select, .s-input {
  background: #131313; border: none; border-radius: 4px; padding: 6px 8px;
  color: #E8E8E8; font-size: 12px; outline: none;
}
.row { display: flex; align-items: center; gap: 6px; }
.row span { color: #484848; }
.slider-row { display: flex; align-items: center; gap: 6px; }
.slider-row input { flex: 1; accent-color: #E2B340; }
.slider-row span { color: #787878; font-size: 12px; min-width: 30px; }
.op-settings { display: flex; flex-direction: column; gap: 4px; }
.btn-start {
  padding: 10px; background: #E2B340; border: none; border-radius: 6px;
  color: #000; font-weight: 700; cursor: pointer; margin-top: auto;
}
.btn-start:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
