<template>
  <div class="batch-view">
    <!-- 서브탭 -->
    <div class="sub-tabs">
      <button class="sub-tab" :class="{ active: subTab === 'batch' }" @click="subTab = 'batch'">BATCH</button>
      <button class="sub-tab" :class="{ active: subTab === 'upscale' }" @click="subTab = 'upscale'">UPSCALE</button>
      <button class="sub-tab" :class="{ active: subTab === 'adetailer' }" @click="subTab = 'adetailer'">ADETAILER</button>
      <button class="sub-tab" :class="{ active: subTab === 'sam3' }" @click="subTab = 'sam3'">SAM3</button>
    </div>

    <!-- Batch 탭 -->
    <div v-if="subTab === 'batch'" class="tab-body">
      <div class="panel">
        <h3>BATCH PROCESSING</h3>
        <div class="file-drop" @dragover.prevent @drop.prevent="onDropBatch">
          <div v-if="batchFiles.length === 0" class="drop-hint">
            이미지 드래그 또는 <button class="link-btn" @click="action('open_batch_files')">파일 선택</button>
          </div>
          <div v-else class="file-list">
            <div v-for="(f, i) in batchFiles" :key="f" class="file-item">
              <span>{{ basename(f) }}</span>
              <button class="rm-btn" @click="batchFiles.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <label class="s-label">작업</label>
        <CustomSelect v-model="batchOp" :options="['resize', 'format']" placeholder="작업 선택" />
        <div v-if="batchOp === 'resize'" class="op-settings">
          <div class="row"><input class="s-input" v-model="resizeW" placeholder="W" /><span>×</span><input class="s-input" v-model="resizeH" placeholder="H" /></div>
        </div>
        <div v-if="batchOp === 'format'" class="op-settings">
          <CustomSelect v-model="formatType" :options="['PNG', 'JPEG', 'WEBP']" placeholder="포맷" />
        </div>
        <button class="btn-start" @click="startBatch" :disabled="batchFiles.length === 0">
          배치 시작 ({{ batchFiles.length }}파일)
        </button>
      </div>
    </div>

    <!-- Upscale 탭 -->
    <div v-if="subTab === 'upscale'" class="tab-body">
      <div class="panel">
        <h3>UPSCALE</h3>
        <div class="file-drop" @dragover.prevent @drop.prevent="onDropUpscale">
          <div v-if="upscaleFiles.length === 0" class="drop-hint">
            이미지 드래그 또는 <button class="link-btn" @click="action('open_upscale_files')">파일 선택</button>
          </div>
          <div v-else class="file-list">
            <div v-for="(f, i) in upscaleFiles" :key="f" class="file-item">
              <span>{{ basename(f) }}</span>
              <button class="rm-btn" @click="upscaleFiles.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <label class="s-label">업스케일러</label>
        <CustomSelect v-model="upscaler" :options="upscalers" placeholder="업스케일러 선택..." />
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

    <!-- ADetailer 탭 -->
    <div v-if="subTab === 'adetailer'" class="tab-body ad-layout">
      <!-- 좌측: 설정 -->
      <div class="ad-settings">
        <h3>ADETAILER</h3>
        <div class="file-drop" @dragover.prevent @drop.prevent="onDropAd">
          <div v-if="adFiles.length === 0" class="drop-hint">
            이미지 드래그 또는
            <button class="link-btn" @click="action('open_ad_files')">파일 선택</button>
            /
            <button class="link-btn" @click="action('open_ad_folder')">폴더 선택</button>
          </div>
          <div v-else class="file-list">
            <div v-for="(f, i) in adFiles" :key="f" class="file-item"
              :class="{ active: adCurrentIdx === i, done: adResults[i] }"
              @click="previewAdFile(i)">
              <span>{{ basename(f) }}</span>
              <span v-if="adResults[i]" class="done-badge">✓</span>
              <button class="rm-btn" @click.stop="adFiles.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <div class="file-count" v-if="adFiles.length">{{ adFiles.length }}개 파일</div>

        <label class="s-label">AD Model</label>
        <CustomSelect v-model="adModel" :options="adModelItems" placeholder="AD Model..." />
        <div class="ad-params">
          <div class="ad-param">
            <label>Confidence</label>
            <input type="number" v-model.number="adConfidence" step="0.05" min="0" max="1" />
          </div>
          <div class="ad-param">
            <label>Denoise</label>
            <input type="number" v-model.number="adDenoise" step="0.05" min="0" max="1" />
          </div>
          <div class="ad-param">
            <label>Prompt</label>
            <label class="ad-toggle"><input type="checkbox" v-model="adUseExifPrompt" /><span>EXIF 프롬프트 사용</span></label>
            <input v-if="!adUseExifPrompt" type="text" v-model="adPrompt" placeholder="(선택사항)" />
            <div v-else class="exif-prompt-hint">각 이미지의 EXIF에서 Positive/Negative를 자동으로 읽어 사용합니다</div>
          </div>
        </div>

        <!-- 프로그레스 -->
        <div class="ad-progress" v-if="adProcessing">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: adProgressPct + '%' }"></div>
          </div>
          <span>
            {{ adProgressCur }}/{{ adProgressTotal }}
            <span v-if="adEtaText" class="ad-eta">· ETA {{ adEtaText }}</span>
          </span>
        </div>

        <div class="ad-actions">
          <button class="btn-start" @click="runAdSingle" :disabled="adFiles.length === 0 || adProcessing">
            현재 이미지 적용
          </button>
          <button class="btn-start batch" @click="runAdBatch" :disabled="adFiles.length === 0 || adProcessing">
            전체 배치 ({{ adFiles.length }}장)
          </button>
          <button class="btn-stop" v-if="adProcessing" @click="action('stop_adetailer_batch')">
            중지
          </button>
        </div>
      </div>

      <!-- 우측: Before/After 비교 -->
      <div class="ad-compare">
        <div v-if="adBefore && adAfter" class="compare-split">
          <div class="compare-col">
            <div class="compare-label">BEFORE</div>
            <img :src="'file:///' + adBefore" />
          </div>
          <div class="compare-col">
            <div class="compare-label">AFTER</div>
            <img :src="'file:///' + adAfter" />
          </div>
        </div>
        <div v-else-if="adPreview" class="preview-single">
          <img :src="'file:///' + adPreview" />
        </div>
        <div v-else class="compare-empty">
          좌측에서 이미지를 선택하면 미리보기가 표시됩니다
        </div>
      </div>
    </div>

    <!-- SAM3 탭 -->
    <div v-if="subTab === 'sam3'" class="tab-body ad-layout">
      <div class="ad-settings">
        <h3>SAM3</h3>
        <div class="file-drop" @dragover.prevent @drop.prevent="onDropSam3">
          <div v-if="sam3Files.length === 0" class="drop-hint">
            이미지 드래그 또는
            <button class="link-btn" @click="action('open_ad_files')">파일 선택</button>
            /
            <button class="link-btn" @click="action('open_ad_folder')">폴더 선택</button>
          </div>
          <div v-else class="file-list">
            <div v-for="(f, i) in sam3Files" :key="f" class="file-item"
              :class="{ active: sam3CurrentIdx === i, done: sam3Results[i] }"
              @click="previewSam3File(i)">
              <span>{{ basename(f) }}</span>
              <span v-if="sam3Results[i]" class="done-badge">✓</span>
              <button class="rm-btn" @click.stop="sam3Files.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <div class="file-count" v-if="sam3Files.length">{{ sam3Files.length }}개 파일</div>

        <div class="ad-params">
          <div class="ad-param">
            <label>Detect Prompt</label>
            <input type="text" v-model="sam3Prompt" placeholder="face" />
          </div>
          <div class="ad-param">
            <label>Inpaint Prompt</label>
            <label class="ad-toggle"><input type="checkbox" v-model="sam3UseExifPrompt" /><span>EXIF 프롬프트 사용</span></label>
            <input v-if="!sam3UseExifPrompt" type="text" v-model="sam3InpaintPrompt" placeholder="비워두면 메인 프롬프트 유지" />
            <div v-else class="exif-prompt-hint">각 이미지의 EXIF에서 Positive/Negative를 자동으로 읽어 사용합니다</div>
          </div>
          <div class="ad-param">
            <label>Negative Prompt</label>
            <input type="text" v-model="sam3NegativePrompt" placeholder="(선택사항)" />
          </div>
          <div class="ad-param">
            <label>Mask Mode</label>
            <CustomSelect v-model="sam3MaskMode" :options="['Individual', 'Combined']" placeholder="Mask Mode" />
          </div>
          <div class="ad-param">
            <label>Threshold</label>
            <input type="number" v-model.number="sam3Threshold" step="0.01" min="0" max="1" />
          </div>
          <div class="ad-param">
            <label>Denoise</label>
            <input type="number" v-model.number="sam3Denoise" step="0.01" min="0" max="1" />
          </div>
          <div class="ad-param">
            <label>Mask Blur</label>
            <input type="number" v-model.number="sam3MaskBlur" min="0" />
          </div>
          <div class="ad-param">
            <label>Padding</label>
            <input type="number" v-model.number="sam3Padding" min="0" />
          </div>
          <div class="ad-param">
            <label>Checkpoint</label>
            <input type="text" v-model="sam3Checkpoint" placeholder="sam3.pt" />
          </div>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3PreviewOverlay" /><span>Overlay Preview</span></label>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3SaveArtifacts" /><span>Artifacts 저장</span></label>
        </div>

        <div class="ad-progress" v-if="sam3Processing">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: sam3ProgressPct + '%' }"></div>
          </div>
          <span>{{ sam3ProgressCur }}/{{ sam3ProgressTotal }}</span>
        </div>

        <div class="ad-actions">
          <button class="btn-start" @click="runSam3Single" :disabled="sam3Files.length === 0 || sam3Processing">
            현재 이미지 적용
          </button>
          <button class="btn-start batch" @click="runSam3Batch" :disabled="sam3Files.length === 0 || sam3Processing">
            전체 배치 ({{ sam3Files.length }}장)
          </button>
        </div>
      </div>

      <div class="ad-compare">
        <div v-if="sam3Before && sam3After" class="compare-split">
          <div class="compare-col">
            <div class="compare-label">BEFORE</div>
            <img :src="'file:///' + sam3Before" />
          </div>
          <div class="compare-col">
            <div class="compare-label">AFTER</div>
            <img :src="'file:///' + sam3After" />
          </div>
        </div>
        <div v-else-if="sam3Preview" class="preview-single">
          <img :src="'file:///' + sam3Preview" />
        </div>
        <div v-else class="compare-empty">
          좌측에서 이미지를 선택하면 미리보기가 표시됩니다
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import CustomSelect from '../components/CustomSelect.vue'

const subTab = ref('batch')
const action = (name, payload = {}) => requestAction(name, payload)
const basename = (p) => typeof p === 'string' ? p.split('/').pop().split('\\').pop() : p.name || p

// ── Batch ──
const batchFiles = ref([])
const batchOp = ref('resize')
const resizeW = ref('1024')
const resizeH = ref('1024')
const formatType = ref('PNG')

function onDropBatch(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  batchFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => f.path))
}
function startBatch() {
  action('start_batch', {
    files: batchFiles.value,
    operation: batchOp.value,
    settings: { width: resizeW.value, height: resizeH.value, format: formatType.value },
  })
}

// ── Upscale ──
const upscaleFiles = ref([])
const upscaler = ref('')
const upscalers = ref(['R-ESRGAN 4x+', 'R-ESRGAN 4x+ Anime6B'])
const scaleFactor = ref(2)

function onDropUpscale(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  upscaleFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => f.path))
}
function startUpscale() {
  action('start_upscale', {
    files: upscaleFiles.value,
    upscaler: upscaler.value,
    scale: scaleFactor.value,
  })
}

// ── ADetailer ──
const adFiles = ref([])
const adModel = ref('face_yolov8n.pt')
const adModelItems = ref([])
const adConfidence = ref(0.3)
const adDenoise = ref(0.4)
const adPrompt = ref('')
const adUseExifPrompt = ref(false)
const adCurrentIdx = ref(-1)
const adPreview = ref('')
const adBefore = ref('')
const adAfter = ref('')
const adResults = ref({})  // index → true
const adProcessing = ref(false)
const adProgressCur = ref(0)
const adProgressTotal = ref(0)
const adProgressPct = computed(() => adProgressTotal.value ? Math.round(adProgressCur.value / adProgressTotal.value * 100) : 0)
// ETA — 시작 시각과 진행 수를 기반으로 평균 처리 시간을 추정
const _adStartTime = ref(0)
const adEtaText = computed(() => {
  if (!adProcessing.value || _adStartTime.value === 0) return ''
  const done = adProgressCur.value
  const total = adProgressTotal.value
  const remaining = total - done
  if (done < 1 || remaining <= 0) return ''
  const elapsedSec = (Date.now() - _adStartTime.value) / 1000
  const avgPerItem = elapsedSec / done
  const sec = Math.round(avgPerItem * remaining)
  if (sec < 60) return `${sec}초`
  if (sec < 3600) return `${Math.floor(sec / 60)}분 ${sec % 60}초`
  return `${Math.floor(sec / 3600)}시 ${Math.floor((sec % 3600) / 60)}분`
})

function onDropAd(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  adFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => f.path))
}

function previewAdFile(i) {
  adCurrentIdx.value = i
  adPreview.value = adFiles.value[i]
  adBefore.value = ''
  adAfter.value = ''
}

function _adSettings() {
  return {
    ad_model: adModel.value,
    ad_confidence: adConfidence.value,
    ad_denoise: adDenoise.value,
    ad_prompt: adUseExifPrompt.value ? '' : adPrompt.value,
    use_exif_prompt: adUseExifPrompt.value,
  }
}

function runAdSingle() {
  const idx = adCurrentIdx.value >= 0 ? adCurrentIdx.value : 0
  const path = adFiles.value[idx]
  if (!path) return
  adProcessing.value = true
  adBefore.value = path
  adAfter.value = ''
  action('run_adetailer_single', { path, settings: _adSettings() })
}

function runAdBatch() {
  if (!adFiles.value.length) return
  adProcessing.value = true
  adResults.value = {}
  adProgressCur.value = 0
  adProgressTotal.value = adFiles.value.length
  _adStartTime.value = Date.now()  // ETA 계산용 시작 시각
  action('run_adetailer_batch', { paths: adFiles.value, settings: _adSettings() })
}

// ── SAM3 ──
const sam3Files = ref([])
const sam3Prompt = ref('face')
const sam3InpaintPrompt = ref('')
const sam3NegativePrompt = ref('')
const sam3UseExifPrompt = ref(false)
const sam3MaskMode = ref('Individual')
const sam3Threshold = ref(0.4)
const sam3Denoise = ref(0.3)
const sam3MaskBlur = ref(8)
const sam3Padding = ref(32)
const sam3Checkpoint = ref('sam3.pt')
const sam3PreviewOverlay = ref(false)
const sam3SaveArtifacts = ref(true)
const sam3CurrentIdx = ref(-1)
const sam3Preview = ref('')
const sam3Before = ref('')
const sam3After = ref('')
const sam3Results = ref({})
const sam3Processing = ref(false)
const sam3ProgressCur = ref(0)
const sam3ProgressTotal = ref(0)
const sam3ProgressPct = computed(() => sam3ProgressTotal.value ? Math.round(sam3ProgressCur.value / sam3ProgressTotal.value * 100) : 0)

function onDropSam3(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  sam3Files.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => f.path))
}

function previewSam3File(i) {
  sam3CurrentIdx.value = i
  sam3Preview.value = sam3Files.value[i]
  sam3Before.value = ''
  sam3After.value = ''
}

function _sam3Settings() {
  return {
    sam3_mode: 'Inpaint',
    sam3_mask_mode: sam3MaskMode.value,
    sam3_prompt: sam3Prompt.value || 'face',
    sam3_inpaint_prompt: sam3UseExifPrompt.value ? '' : sam3InpaintPrompt.value,
    sam3_negative_prompt: sam3NegativePrompt.value,
    sam3_threshold: sam3Threshold.value,
    sam3_checkpoint: sam3Checkpoint.value || 'sam3.pt',
    sam3_mask_blur: sam3MaskBlur.value,
    sam3_denoising_strength: sam3Denoise.value,
    sam3_inpaint_only_masked: true,
    sam3_inpaint_only_masked_padding: sam3Padding.value,
    sam3_use_inpaint_width_height: false,
    sam3_inpaint_width: 1024,
    sam3_inpaint_height: 1024,
    sam3_preview_overlay: sam3PreviewOverlay.value,
    sam3_save_artifacts: sam3SaveArtifacts.value,
    use_exif_prompt: sam3UseExifPrompt.value,
  }
}

function runSam3Single() {
  const idx = sam3CurrentIdx.value >= 0 ? sam3CurrentIdx.value : 0
  const path = sam3Files.value[idx]
  if (!path) return
  sam3Processing.value = true
  sam3Before.value = path
  sam3After.value = ''
  action('run_sam3_single', { path, settings: _sam3Settings() })
}

function runSam3Batch() {
  if (!sam3Files.value.length) return
  sam3Processing.value = true
  sam3Results.value = {}
  sam3ProgressCur.value = 0
  sam3ProgressTotal.value = sam3Files.value.length
  action('run_sam3_batch', { paths: sam3Files.value, settings: _sam3Settings() })
}

// 외부에서 이미지 수신 (History/Gallery 우클릭 → "ADetailer 적용")
defineProps({ initialAdPath: { type: String, default: '' } })

onMounted(async () => {
  const backend = await getBackend()

  // 업스케일러 로드
  if (backend.getUpscalers) {
    backend.getUpscalers((json) => {
      try {
        const list = JSON.parse(json)
        if (list.length) { upscalers.value = list; upscaler.value = list[0] }
      } catch {}
    })
  }

  // AD 모델 로드
  if (backend.getADetailerModels) {
    backend.getADetailerModels((json) => {
      try {
        const models = JSON.parse(json)
        if (models.length) { adModelItems.value = models; adModel.value = models[0] }
      } catch {}
    })
  }

  // 파일 선택 이벤트
  onBackendEvent('batchFilesSelected', (json) => {
    try {
      const paths = JSON.parse(json)
      if (subTab.value === 'adetailer') {
        adFiles.value.push(...paths)
      } else if (subTab.value === 'sam3') {
        sam3Files.value.push(...paths)
      } else if (subTab.value === 'upscale') {
        upscaleFiles.value.push(...paths)
      } else {
        batchFiles.value.push(...paths)
      }
    } catch {}
  })

  // ADetailer 결과 수신
  onBackendEvent('adetailerResult', (json) => {
    try {
      const d = JSON.parse(json)
      if (d.error) {
        requestAction('show_toast', { type: 'error', msg: `AD 오류: ${d.error}` })
        adProcessing.value = false
        return
      }
      adBefore.value = d.before
      adAfter.value = d.after
      if (typeof d.index === 'number') {
        adResults.value[d.index] = true
        adCurrentIdx.value = d.index
      }
      // 단일 처리 완료
      if (typeof d.index !== 'number') {
        adProcessing.value = false
        _adStartTime.value = 0
        requestAction('show_toast', { type: 'success', msg: 'ADetailer 완료' })
      }
      // 배치 전체 완료 — 마지막 인덱스가 total-1
      if (typeof d.index === 'number' && d.index === adProgressTotal.value - 1) {
        adProcessing.value = false
        _adStartTime.value = 0
        requestAction('show_toast', { type: 'success', msg: `ADetailer 배치 완료 (${adProgressTotal.value}장)` })
      }
    } catch {}
  })

  // 배치 진행률
  onBackendEvent('adetailerProgress', (cur, total) => {
    adProgressCur.value = cur
    adProgressTotal.value = total
    if (cur >= total) adProcessing.value = false
  })

  onBackendEvent('sam3Result', (json) => {
    try {
      const d = JSON.parse(json)
      if (d.error) {
        requestAction('show_toast', { type: 'error', msg: `SAM3 오류: ${d.error}` })
        sam3Processing.value = false
        return
      }
      sam3Before.value = d.before
      sam3After.value = d.after
      if (typeof d.index === 'number') {
        sam3Results.value[d.index] = true
        sam3CurrentIdx.value = d.index
      }
      if (typeof d.index !== 'number') {
        sam3Processing.value = false
        requestAction('show_toast', { type: 'success', msg: 'SAM3 완료' })
      }
    } catch {}
  })

  onBackendEvent('sam3Progress', (cur, total) => {
    sam3ProgressCur.value = cur
    sam3ProgressTotal.value = total
    if (cur >= total) sam3Processing.value = false
  })
})
</script>

<style scoped>
.batch-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.sub-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.sub-tab {
  flex: 1; padding: 8px; background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-muted); font-size: 11px; font-weight: 800; cursor: pointer; text-align: center;
  letter-spacing: 1px;
}
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-body { flex: 1; overflow-y: auto; padding: 20px; }

.panel { max-width: 500px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.panel h3 { color: var(--text-primary); font-size: 13px; font-weight: 900; letter-spacing: 2px; margin: 0; }

.file-drop {
  border: 2px dashed var(--border); border-radius: 8px; min-height: 100px;
  display: flex; align-items: center; justify-content: center; padding: 12px;
}
.drop-hint { color: var(--text-muted); font-size: 12px; text-align: center; }
.link-btn { background: none; border: none; color: var(--accent); cursor: pointer; text-decoration: underline; font-size: 12px; }
.file-list { width: 100%; max-height: 200px; overflow-y: auto; }
.file-item {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; font-size: 11px; color: var(--text-secondary); cursor: pointer;
  border-radius: 4px;
}
.file-item span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-item.active { background: var(--accent-dim); color: var(--accent); }
.file-item.done { opacity: 0.6; }
.done-badge { color: #4ade80; font-weight: 900; flex: 0 !important; }
.rm-btn { background: none; border: none; color: #f87171; cursor: pointer; font-size: 14px; flex-shrink: 0; }
.file-count { font-size: 10px; color: var(--text-muted); }

.s-label { color: var(--text-muted); font-size: 10px; font-weight: 700; letter-spacing: 1px; }
.s-select, .s-input {
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; color: var(--text-primary); font-size: 12px; outline: none;
}
.s-select:focus, .s-input:focus { border-color: var(--accent); }
.row { display: flex; align-items: center; gap: 6px; }
.row span { color: var(--text-muted); }
.slider-row { display: flex; align-items: center; gap: 8px; }
.slider-row input { flex: 1; accent-color: var(--accent); }
.slider-row span { color: var(--text-secondary); font-size: 12px; min-width: 30px; font-family: monospace; }
.op-settings { display: flex; flex-direction: column; gap: 4px; }
.btn-start {
  padding: 10px; background: var(--accent); border: none; border-radius: 8px;
  color: #000; font-weight: 800; font-size: 11px; cursor: pointer; letter-spacing: 1px;
}
.btn-start:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-start.batch { background: var(--bg-button); color: var(--accent); border: 1px solid var(--accent-dim); }
.btn-stop { padding: 10px; background: #f87171; border: none; border-radius: 8px; color: #000; font-weight: 800; font-size: 11px; cursor: pointer; }

/* ADetailer Layout */
.ad-layout { display: flex; gap: 0; padding: 0 !important; }
.ad-settings { width: 320px; flex-shrink: 0; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; border-right: 1px solid var(--border); }
.ad-settings h3 { color: var(--text-primary); font-size: 13px; font-weight: 900; letter-spacing: 2px; margin: 0; }
.ad-params { display: flex; flex-direction: column; gap: 8px; }
.ad-param { display: flex; flex-direction: column; gap: 2px; }
.ad-param label { font-size: 10px; color: var(--text-muted); font-weight: 700; }
.ad-param input { padding: 6px 8px; font-size: 12px; }
.ad-toggle { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-muted); cursor: pointer; margin-bottom: 4px; }
.ad-toggle input { width: 14px; height: 14px; accent-color: var(--accent); }
.exif-prompt-hint { font-size: 10px; color: var(--accent); background: var(--accent-dim); padding: 6px 8px; border-radius: 4px; }
.ad-actions { display: flex; flex-direction: column; gap: 6px; margin-top: auto; }

.ad-progress { display: flex; align-items: center; gap: 8px; }
.progress-bar { flex: 1; height: 6px; background: var(--bg-button); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.ad-progress span { font-size: 10px; color: var(--text-muted); font-family: monospace; }

/* Compare */
.ad-compare { flex: 1; display: flex; align-items: center; justify-content: center; padding: 20px; overflow: hidden; }
.compare-split { display: flex; gap: 12px; width: 100%; height: 100%; }
.compare-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
.compare-label { font-size: 10px; font-weight: 900; color: var(--text-muted); letter-spacing: 2px; }
.compare-col img { max-width: 100%; max-height: calc(100% - 24px); object-fit: contain; border-radius: 6px; }
.preview-single { display: flex; align-items: center; justify-content: center; }
.preview-single img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
.compare-empty { color: var(--text-muted); font-size: 13px; }
</style>
