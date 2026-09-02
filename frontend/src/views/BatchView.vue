<template>
  <div class="batch-view">
    <!-- 서브탭 -->
    <div class="sub-tabs">
      <button class="sub-tab" :class="{ active: subTab === 'batch' }" @click="subTab = 'batch'">일괄</button>
      <button class="sub-tab" :class="{ active: subTab === 'upscale' }" @click="subTab = 'upscale'">업스케일</button>
      <button class="sub-tab" :class="{ active: subTab === 'adetailer' }" @click="subTab = 'adetailer'">ADetailer</button>
      <button class="sub-tab" :class="{ active: subTab === 'sam3' }" @click="subTab = 'sam3'">SAM3</button>
      <button class="sub-tab" :class="{ active: subTab === 'caption' }" @click="subTab = 'caption'">캡션</button>
    </div>

    <!-- Batch 탭 — 듀얼 패널 (좌측 설정 / 우측 썸네일 그리드) -->
    <div v-if="subTab === 'batch'" class="tab-body ad-layout">
      <div class="ad-settings">
        <h3>일괄 처리</h3>
        <div class="file-drop compact" @dragover.prevent @drop.prevent="onDropBatch">
          <div class="drop-hint">
            이미지 드래그 또는
            <button class="link-btn" @click="action('open_batch_files')">파일 선택</button>
          </div>
        </div>
        <div class="file-count" v-if="batchFiles.length">{{ batchFiles.length }}개 파일</div>
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
      <!-- 우측: 썸네일 그리드 -->
      <div class="ad-compare">
        <div v-if="batchFiles.length === 0" class="grid-empty">
          <div class="grid-empty-ico"><Icon name="package" /></div>
          <div class="grid-empty-title">이미지를 드래그하여 추가</div>
          <div class="grid-empty-sub">여러 장을 한꺼번에 처리할 수 있습니다</div>
        </div>
        <div v-else class="thumb-grid">
          <div v-for="(f, i) in batchFiles" :key="f" class="thumb-card">
            <img :src="mediaUrl(f)" :alt="basename(f)" loading="lazy" />
            <div class="thumb-name" :title="f">{{ basename(f) }}</div>
            <button class="thumb-rm" @click="batchFiles.splice(i, 1)" title="제거">×</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Upscale 탭 — 듀얼 패널 -->
    <div v-if="subTab === 'upscale'" class="tab-body ad-layout">
      <div class="ad-settings">
        <h3>업스케일</h3>
        <div class="file-drop compact" @dragover.prevent @drop.prevent="onDropUpscale">
          <div class="drop-hint">
            이미지 드래그 또는
            <button class="link-btn" @click="action('open_upscale_files')">파일 선택</button>
          </div>
        </div>
        <div class="file-count" v-if="upscaleFiles.length">{{ upscaleFiles.length }}개 파일</div>
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
      <!-- 우측: 썸네일 그리드 -->
      <div class="ad-compare">
        <div v-if="upscaleFiles.length === 0" class="grid-empty">
          <div class="grid-empty-ico"><Icon name="search" /></div>
          <div class="grid-empty-title">업스케일할 이미지를 드래그</div>
          <div class="grid-empty-sub">2~4배 해상도 향상</div>
        </div>
        <div v-else class="thumb-grid">
          <div v-for="(f, i) in upscaleFiles" :key="f" class="thumb-card">
            <img :src="mediaUrl(f)" :alt="basename(f)" loading="lazy" />
            <div class="thumb-name" :title="f">{{ basename(f) }}</div>
            <button class="thumb-rm" @click="upscaleFiles.splice(i, 1)" title="제거">×</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ADetailer 탭 -->
    <div v-if="subTab === 'adetailer'" class="tab-body ad-layout">
      <!-- 좌측: 설정 -->
      <div class="ad-settings">
        <h3>ADetailer</h3>
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
              <span v-if="adResults[i]" class="done-badge"><Icon name="check" /></span>
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
            <div class="compare-label">이전</div>
            <img :src="mediaUrl(adBefore)" />
          </div>
          <div class="compare-col">
            <div class="compare-label">이후</div>
            <img :src="mediaUrl(adAfter)" />
          </div>
        </div>
        <div v-else-if="adPreview" class="preview-single">
          <img :src="mediaUrl(adPreview)" />
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
              <span v-if="sam3Results[i]" class="done-badge"><Icon name="check" /></span>
              <button class="rm-btn" @click.stop="sam3Files.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <div class="file-count" v-if="sam3Files.length">{{ sam3Files.length }}개 파일</div>

        <div class="ad-params">
          <div class="ad-param">
            <label>검출 프롬프트</label>
            <input type="text" v-model="sam3Prompt" placeholder="face" />
          </div>
          <div class="ad-param">
            <label>인페인트 프롬프트</label>
            <label class="ad-toggle"><input type="checkbox" v-model="sam3UseExifPrompt" /><span>EXIF 프롬프트 사용</span></label>
            <input v-if="!sam3UseExifPrompt" type="text" v-model="sam3InpaintPrompt" placeholder="비워두면 메인 프롬프트 유지" />
            <div v-else class="exif-prompt-hint">각 이미지의 EXIF에서 Positive/Negative를 자동으로 읽어 사용합니다</div>
          </div>
          <div class="ad-param">
            <label>Exclude Prompt (보호할 영역)</label>
            <input type="text" v-model="sam3ExcludePrompt" placeholder="face, eyes, hand" />
          </div>
          <div class="ad-param">
            <label>Negative Prompt</label>
            <input type="text" v-model="sam3NegativePrompt" placeholder="(선택사항)" />
          </div>
          <div class="ad-param">
            <label>Mode</label>
            <CustomSelect v-model="sam3Mode" :options="['Inpaint', 'Mask only']" placeholder="Inpaint" />
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
            <label>Mask Dilation (px)</label>
            <input type="number" v-model.number="sam3MaskDilation" min="0" />
          </div>
          <div class="ad-param">
            <label>Outline expand (px)</label>
            <input type="number" v-model.number="sam3MaskOutline" min="0" />
          </div>
          <div class="ad-param">
            <label>Inpainting fill</label>
            <CustomSelect v-model="sam3Fill"
              :options="['fill', 'original', 'latent noise', 'latent nothing']" placeholder="original" />
          </div>
          <div class="ad-param">
            <label>스텝</label>
            <input type="number" v-model.number="sam3Steps" min="1" />
          </div>
          <div class="ad-param">
            <label>CFG</label>
            <input type="number" v-model.number="sam3Cfg" step="0.5" min="0" />
          </div>
          <div class="ad-param">
            <label>Seed (-1 = 랜덤)</label>
            <input type="number" v-model.number="sam3Seed" />
          </div>
          <div class="ad-param">
            <label>Checkpoint</label>
            <input type="text" v-model="sam3Checkpoint" placeholder="sam3.pt" />
          </div>
          <div class="ad-param">
            <label>Device</label>
            <CustomSelect v-model="sam3Device" :options="['cuda', 'auto', 'cpu']" placeholder="cuda" />
          </div>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3MaskHull" /><span>Convex Hull (머리카락 감싸기)</span></label>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3OnlyMasked" /><span>마스크된 영역만</span></label>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3RestoreFace" /><span>Restore face</span></label>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3PreviewOverlay" /><span>오버레이 미리보기</span></label>
          <label class="ad-toggle"><input type="checkbox" v-model="sam3SaveArtifacts" /><span>Artifacts 저장</span></label>
          <label class="ad-toggle" title="검출 직후 SAM3(~3.5GB) VRAM 회수 — 16GB GPU 권장">
            <input type="checkbox" v-model="sam3UnloadAfter" /><span>검출 후 SAM3 VRAM 해제</span></label>
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
            <div class="compare-label">이전</div>
            <img :src="mediaUrl(sam3Before)" />
          </div>
          <div class="compare-col">
            <div class="compare-label">이후</div>
            <img :src="mediaUrl(sam3After)" />
          </div>
        </div>
        <div v-else-if="sam3Preview" class="preview-single">
          <img :src="mediaUrl(sam3Preview)" />
        </div>
        <div v-else class="compare-empty">
          좌측에서 이미지를 선택하면 미리보기가 표시됩니다
        </div>
      </div>
    </div>

    <!-- CAPTION 탭 — Ollama 비전 모델 캡션 (taggui 방식 .txt 사이드카) -->
    <div v-if="subTab === 'caption'" class="tab-body ad-layout">
      <div class="ad-settings">
        <h3>이미지 캡션</h3>
        <label class="s-label">캡션 모델 (Ollama 비전)</label>
        <div class="cap-model-row">
          <CustomSelect v-if="ollamaModels.length" v-model="captionModel" :options="ollamaModels"
            placeholder="모델 선택..." @update:modelValue="saveCaptionModel" />
          <input v-else class="s-input" v-model="captionModel" @change="saveCaptionModel" placeholder="모델 로딩 중..." />
          <button class="cap-refresh" @click="loadCaptionModels" title="모델 목록 새로고침"><Icon name="refresh" /></button>
        </div>
        <label class="s-label">프롬프트</label>
        <textarea class="s-textarea" v-model="captionPrompt" @change="saveCaptionPrompt" rows="4"></textarea>
        <div class="cap-opts">
          <label><input type="checkbox" v-model="captionSave" /> .txt 저장</label>
          <label><input type="checkbox" v-model="captionOverwrite" /> 기존 덮어쓰기</label>
        </div>
        <label class="s-label">저장 위치</label>
        <div class="cap-outdir">
          <span class="cap-outdir-path" :title="captionOutDir || '이미지와 같은 폴더'">{{ captionOutDir || '이미지와 같은 폴더 (.txt 사이드카)' }}</span>
          <button class="cap-refresh" @click="action('caption_pick_outdir')" title="저장 폴더 선택"><Icon name="folder" /></button>
          <button v-if="captionOutDir" class="cap-refresh" @click="clearCaptionOutDir" title="기본값(이미지 옆)으로"><Icon name="rotate-ccw" /></button>
        </div>
        <div class="cap-pick">
          <button class="link-btn" @click="action('caption_pick_files')"><Icon name="file" /> 파일 선택</button>
          <button class="link-btn" @click="action('caption_pick_folder')"><Icon name="folder" /> 폴더 선택</button>
        </div>
        <div class="file-count" v-if="captionItems.length">{{ captionItems.length }}개 이미지</div>
        <button class="btn-start" @click="captionAll" :disabled="!captionItems.length || captionRunning">
          {{ captionRunning ? `캡션 중... ${captionCur}/${captionTotal}` : `전체 캡션 (${captionItems.length})` }}
        </button>
        <button v-if="captionItems.length" class="link-btn cap-clear" @click="clearCaption">목록 비우기</button>
      </div>
      <div class="ad-compare">
        <div v-if="!captionItems.length" class="grid-empty">
          <div class="grid-empty-ico"><Icon name="tag" /></div>
          <div class="grid-empty-title">파일 또는 폴더를 선택하세요</div>
          <div class="grid-empty-sub">Ollama 비전 모델로 캡션을 만들고 이미지 옆에 .txt로 저장합니다</div>
        </div>
        <div v-else class="cap-list">
          <div v-for="it in captionItems" :key="it.path" class="cap-item">
            <img :src="mediaUrl(it.path)" loading="lazy" class="cap-thumb" />
            <div class="cap-body">
              <div class="cap-name" :title="it.path">
                {{ basename(it.path) }}
                <span class="cap-status" :class="it.status">{{ statusLabel(it.status) }}</span>
              </div>
              <textarea class="cap-text" v-model="it.caption" placeholder="캡션 (편집 가능)..." rows="3"></textarea>
              <div class="cap-actions">
                <button class="cap-btn" @click="captionSingle(it)" :disabled="captionRunning"><Icon name="tag" /> 캡션</button>
                <button class="cap-btn" @click="saveCaptionItem(it)"><Icon name="save" /> 저장</button>
                <button class="cap-btn t2i" @click="sendCaptionToT2I(it)" :disabled="!it.caption" title="이 캡션을 T2I 메인 프롬프트에 추가하고 이동">→ T2I</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getBackend, onBackendEvent } from '../bridge.js'
import { mediaUrl } from '../utils/media.js'
import { requestAction, useWidgetStore } from '../stores/widgetStore.js'
import CustomSelect from '../components/CustomSelect.vue'
import type { ActionName } from '../types/bridge'

interface CaptionItem {
  path: string
  caption: string
  status: string
  [k: string]: any
}

const router = useRouter()
const widgets = useWidgetStore()
const subTab = ref('batch')
const action = (name: ActionName, payload: any = {}) => requestAction(name, payload)
const basename = (p: any) => typeof p === 'string' ? p.split('/').pop()!.split('\\').pop() : p.name || p

// ── Batch ──
const batchFiles = ref<string[]>([])
const batchOp = ref('resize')
const resizeW = ref('1024')
const resizeH = ref('1024')
const formatType = ref('PNG')

function onDropBatch(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  batchFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => (f as any).path))
}
function startBatch() {
  action('start_batch', {
    files: batchFiles.value,
    operation: batchOp.value,
    settings: { width: resizeW.value, height: resizeH.value, format: formatType.value },
  })
}

// ── Upscale ──
const upscaleFiles = ref<string[]>([])
const upscaler = ref('')
const upscalers = ref<string[]>(['R-ESRGAN 4x+', 'R-ESRGAN 4x+ Anime6B'])
const scaleFactor = ref(2)

function onDropUpscale(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  upscaleFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => (f as any).path))
}
function startUpscale() {
  action('start_upscale', {
    files: upscaleFiles.value,
    upscaler: upscaler.value,
    scale: scaleFactor.value,
  })
}

// ── Caption (Ollama 비전 모델, taggui 방식 .txt 사이드카) ──
const captionItems = ref<CaptionItem[]>([])   // [{path, caption, status}]
const captionModel = ref(window.localStorage.getItem('ollamaCaptionModel')
  || window.localStorage.getItem('ollamaModel') || '')
const captionPrompt = ref(window.localStorage.getItem('captionPrompt')
  || 'Describe this image in detail, naming the main subject and listing appearance, clothing, pose, and background.')
const captionSave = ref(true)
const captionOverwrite = ref(false)
const captionOutDir = ref(window.localStorage.getItem('captionOutDir') || '')
function clearCaptionOutDir() { captionOutDir.value = ''; window.localStorage.removeItem('captionOutDir') }
const captionRunning = ref(false)
const captionCur = ref(0)
const captionTotal = ref(0)
const ollamaModels = ref<string[]>([])

const captionUrl = () => window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434'
function saveCaptionModel() { window.localStorage.setItem('ollamaCaptionModel', captionModel.value) }
async function loadCaptionModels() {
  const backend: any = await getBackend()
  if (backend.requestOllamaModels) {
    backend.requestOllamaModels(captionUrl())
  } else if (backend.ollamaListModels) {
    backend.ollamaListModels(captionUrl(), applyCaptionModels)
  }
}
function applyCaptionModels(json: string) {
  try {
    const payload = JSON.parse(json)
    const models = Array.isArray(payload) ? payload : payload.models
    if (!Array.isArray(models)) return
    if (!Array.isArray(payload) && payload.url && payload.url !== captionUrl()) return
    ollamaModels.value = models
    if (!captionModel.value && models.length) { captionModel.value = models[0]; saveCaptionModel() }
  } catch {}
}
function applyUpscalers(json: string) {
  try {
    const list = JSON.parse(json)
    if (list.length) { upscalers.value = list; upscaler.value = list[0] }
  } catch {}
}
function applyADetailerModels(json: string) {
  try {
    const models = JSON.parse(json)
    if (models.length) { adModelItems.value = models; adModel.value = models[0] }
  } catch {}
}
function saveCaptionPrompt() { window.localStorage.setItem('captionPrompt', captionPrompt.value) }
function clearCaption() { captionItems.value = [] }
function statusLabel(s: string) {
  return ({ pending: '생성 중', done: '✓ 완료', error: '⚠ 실패', skip: '건너뜀' } as Record<string, string>)[s] || ''
}

async function loadCaptionFor(item: CaptionItem) {
  const backend: any = await getBackend()
  if (!backend.loadCaption) return
  backend.loadCaption(item.path, (json: string) => {
    try { const d = JSON.parse(json); if (d.caption) item.caption = d.caption } catch {}
  })
}

async function captionSingle(item: CaptionItem) {
  if (!captionModel.value.trim()) { requestAction('show_toast', { type: 'error', msg: '캡션 모델을 입력하세요' }); return }
  item.status = 'pending'
  const backend: any = await getBackend()
  if (!backend.captionImage) { item.status = ''; return }
  backend.captionImage(JSON.stringify({
    path: item.path, prompt: captionPrompt.value, model: captionModel.value,
    url: captionUrl(), save: captionSave.value, outDir: captionOutDir.value,
  }), (json: string) => {
    try {
      const d = JSON.parse(json)
      if (d.error) { item.status = 'error'; requestAction('show_toast', { type: 'error', msg: '캡션 실패: ' + d.error }); return }
      item.caption = d.caption; item.status = 'done'
    } catch { item.status = 'error' }
  })
}

async function captionAll() {
  if (!captionItems.value.length) return
  if (!captionModel.value.trim()) { requestAction('show_toast', { type: 'error', msg: '캡션 모델을 입력하세요' }); return }
  captionRunning.value = true; captionCur.value = 0; captionTotal.value = captionItems.value.length
  for (const it of captionItems.value) it.status = ''
  const backend: any = await getBackend()
  if (!backend.startCaptionBatch) { captionRunning.value = false; return }
  backend.startCaptionBatch(JSON.stringify({
    files: captionItems.value.map(i => i.path), prompt: captionPrompt.value,
    model: captionModel.value, url: captionUrl(), save: captionSave.value,
    overwrite: captionOverwrite.value, outDir: captionOutDir.value,
  }), (json: string) => {
    try { const d = JSON.parse(json); if (d.error) { requestAction('show_toast', { type: 'error', msg: d.error }); captionRunning.value = false } } catch {}
  })
}

async function saveCaptionItem(item: CaptionItem) {
  const backend: any = await getBackend()
  if (!backend.saveCaption) return
  backend.saveCaption(JSON.stringify({ path: item.path, caption: item.caption, outDir: captionOutDir.value }), (json: string) => {
    try { const d = JSON.parse(json); if (d.ok) requestAction('show_toast', { type: 'success', msg: '캡션 저장됨' }) } catch {}
  })
}

// 캡션을 T2I 메인 프롬프트에 추가하고 T2I 탭으로 이동
function sendCaptionToT2I(item: CaptionItem) {
  const cap = (item.caption || '').trim()
  if (!cap) { requestAction('show_toast', { type: 'warning', msg: '캡션이 비어있습니다' }); return }
  const cur = ((widgets as any).main_prompt_text || '').trim().replace(/[,\s]+$/, '')
  ;(widgets as any).main_prompt_text = cur ? (cur + ', ' + cap) : cap
  router.push('/')   // T2I 탭 (path '/')
  requestAction('show_toast', { type: 'success', msg: 'T2I 프롬프트에 추가했습니다' })
}

// ── ADetailer ──
const adFiles = ref<string[]>([])
const adModel = ref('face_yolov8n.pt')
const adModelItems = ref<string[]>([])
const adConfidence = ref(0.3)
const adDenoise = ref(0.4)
const adPrompt = ref('')
const adUseExifPrompt = ref(false)
const adCurrentIdx = ref(-1)
const adPreview = ref('')
const adBefore = ref('')
const adAfter = ref('')
const adResults = ref<Record<number, boolean>>({})  // index → true
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

function onDropAd(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  adFiles.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => (f as any).path))
}

function previewAdFile(i: number) {
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
const sam3Files = ref<string[]>([])
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
// t2i 패널과 동일 수준으로 노출 (예전엔 배치에 없어 확장 기본값으로만 돌았음)
const sam3Mode = ref('Inpaint')
const sam3ExcludePrompt = ref('')
const sam3MaskDilation = ref(0)
const sam3MaskHull = ref(false)
const sam3MaskOutline = ref(0)
const sam3Device = ref('cuda')
const sam3Fill = ref('original')
const sam3OnlyMasked = ref(true)
const sam3Steps = ref(28)
const sam3Cfg = ref(7)
const sam3Seed = ref(-1)
const sam3RestoreFace = ref(false)
const sam3UnloadAfter = ref(true)
const sam3CurrentIdx = ref(-1)
const sam3Preview = ref('')
const sam3Before = ref('')
const sam3After = ref('')
const sam3Results = ref<Record<number, boolean>>({})
const sam3Processing = ref(false)
const sam3ProgressCur = ref(0)
const sam3ProgressTotal = ref(0)
const sam3ProgressPct = computed(() => sam3ProgressTotal.value ? Math.round(sam3ProgressCur.value / sam3ProgressTotal.value * 100) : 0)

function onDropSam3(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  sam3Files.value.push(...files.filter(f => f.type.startsWith('image/')).map(f => (f as any).path))
}

function previewSam3File(i: number) {
  sam3CurrentIdx.value = i
  sam3Preview.value = sam3Files.value[i]
  sam3Before.value = ''
  sam3After.value = ''
}

function _sam3Settings() {
  return {
    sam3_mode: sam3Mode.value,
    sam3_mask_mode: sam3MaskMode.value,
    sam3_prompt: sam3Prompt.value || 'face',
    // 예전엔 배치 경로에 exclude/dilation/hull/outline/device 입력이 없어
    // 확장 기본값으로만 돌았다 — t2i 패널과 같은 수준으로 노출한다
    sam3_exclude_prompt: sam3ExcludePrompt.value,
    sam3_inpaint_prompt: sam3UseExifPrompt.value ? '' : sam3InpaintPrompt.value,
    sam3_negative_prompt: sam3NegativePrompt.value,
    sam3_threshold: sam3Threshold.value,
    sam3_mask_dilation: sam3MaskDilation.value,
    sam3_mask_hull: sam3MaskHull.value,
    sam3_mask_outline_px: sam3MaskOutline.value,
    sam3_checkpoint: sam3Checkpoint.value || 'sam3.pt',
    sam3_device: sam3Device.value,
    sam3_mask_blur: sam3MaskBlur.value,
    sam3_denoising_strength: sam3Denoise.value,
    sam3_inpainting_fill: sam3Fill.value,
    sam3_inpaint_only_masked: sam3OnlyMasked.value,
    sam3_inpaint_only_masked_padding: sam3Padding.value,
    sam3_use_inpaint_width_height: false,
    sam3_inpaint_width: 1024,
    sam3_inpaint_height: 1024,
    sam3_use_steps: true,
    sam3_steps: sam3Steps.value,
    sam3_use_cfg_scale: true,
    sam3_cfg_scale: sam3Cfg.value,
    sam3_use_seed: sam3Seed.value !== -1,
    sam3_seed: sam3Seed.value,
    sam3_restore_face: sam3RestoreFace.value,
    sam3_preview_overlay: sam3PreviewOverlay.value,
    sam3_save_artifacts: sam3SaveArtifacts.value,
    // 16GB GPU에서 인페인트 OOM 방지 — 확장 API 기본값이 False라 명시 전송 필수
    sam3_unload_after: sam3UnloadAfter.value,
    use_exif_prompt: sam3UseExifPrompt.value,
    // 부모 i2i 샘플링 파라미터 (Forge 현재 UI 값에 좌우되지 않게)
    steps: sam3Steps.value,
    cfg_scale: sam3Cfg.value,
    seed: sam3Seed.value,
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
withDefaults(defineProps<{ initialAdPath?: string }>(), { initialAdPath: '' })

// 캡션 탭을 열 때마다 모델 목록 새로고침
watch(subTab, (v) => { if (v === 'caption') loadCaptionModels() })

onMounted(async () => {
  onBackendEvent('ollamaModelsReady', applyCaptionModels)
  onBackendEvent('upscalersReady', applyUpscalers)
  onBackendEvent('adetailerModelsReady', applyADetailerModels)

  const backend: any = await getBackend()

  // 캡션 모델 드롭다운 — UI 시작 시 자동 새로고침
  loadCaptionModels()

  // 업스케일러 로드
  if (backend.requestUpscalers) backend.requestUpscalers()
  else if (backend.getUpscalers) backend.getUpscalers(applyUpscalers)

  // AD 모델 로드
  if (backend.requestADetailerModels) backend.requestADetailerModels()
  else if (backend.getADetailerModels) backend.getADetailerModels(applyADetailerModels)

  // 파일 선택 이벤트
  onBackendEvent('batchFilesSelected', (json: string) => {
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
  onBackendEvent('adetailerResult', (json: string) => {
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
  onBackendEvent('adetailerProgress', (cur: number, total: number) => {
    adProgressCur.value = cur
    adProgressTotal.value = total
    if (cur >= total) adProcessing.value = false
  })

  onBackendEvent('sam3Result', (json: string) => {
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

  onBackendEvent('sam3Progress', (cur: number, total: number) => {
    sam3ProgressCur.value = cur
    sam3ProgressTotal.value = total
    if (cur >= total) sam3Processing.value = false
  })

  // 캡션 대상 선택 (파일/폴더)
  onBackendEvent('captionFilesSelected', (json: string) => {
    try {
      const paths = JSON.parse(json)
      captionItems.value = paths.map((p: string) => ({ path: p, caption: '', status: '' }))
      captionItems.value.forEach(loadCaptionFor)   // 기존 .txt 있으면 불러오기
    } catch {}
  })
  // 캡션 배치 진행
  onBackendEvent('captionProgress', (json: string) => {
    try {
      const d = JSON.parse(json)
      captionCur.value = (typeof d.index === 'number' ? d.index : 0) + 1
      captionTotal.value = d.total || captionTotal.value
      const it = captionItems.value.find(i => i.path === d.path)
      if (it) {
        if (d.error) it.status = 'error'
        else { it.caption = d.caption || it.caption; it.status = d.skipped ? 'skip' : 'done' }
      }
    } catch {}
  })
  onBackendEvent('captionOutDirSelected', (p: string) => {
    captionOutDir.value = p
    window.localStorage.setItem('captionOutDir', p)
  })
  onBackendEvent('captionDone', (json: string) => {
    captionRunning.value = false
    try { const d = JSON.parse(json); requestAction('show_toast', { type: 'success', msg: `캡션 완료: ${d.ok}/${d.total}${d.failed ? ` (실패 ${d.failed})` : ''}` }) } catch {}
  })
})
</script>

<style scoped>
.batch-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
/* 오른쪽 여백은 알림 종 자리다 (style.css --notif-gutter) */
.sub-tabs { display: flex; gap: 0; padding-right: var(--notif-gutter); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.sub-tab {
  flex: 1; padding: 8px; background: transparent; border: none; border-bottom: 2px solid transparent;
  color: var(--text-muted); font-size: 11px; font-weight: var(--fw-bold); cursor: pointer; text-align: center;
  letter-spacing: 0;
}
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* CAPTION 탭 */
.s-textarea { width: 100%; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text-primary); font-size: 12px; resize: vertical; line-height: 1.4; }
.s-textarea:focus { outline: none; border-color: var(--accent); }
.cap-model-row { display: flex; gap: 6px; align-items: center; }
.cap-model-row > :first-child { flex: 1; min-width: 0; }
.cap-refresh { flex-shrink: 0; width: 32px; height: 32px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 13px; cursor: pointer; }
.cap-refresh:hover { color: var(--accent); border-color: var(--accent); }
.cap-opts { display: flex; gap: 14px; margin: 8px 0; }
.cap-outdir { display: flex; gap: 6px; align-items: center; }
.cap-outdir-path { flex: 1; min-width: 0; font-size: 11px; color: var(--text-secondary); background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cap-opts label { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.cap-pick { display: flex; gap: 8px; margin-top: 6px; }
.cap-clear { margin-top: 8px; align-self: flex-start; }
.cap-list { display: flex; flex-direction: column; gap: 10px; padding: 4px; }
.cap-item { display: flex; gap: 10px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }
.cap-thumb { width: 110px; height: 110px; object-fit: cover; border-radius: 6px; flex-shrink: 0; background: var(--bg-input); }
.cap-body { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.cap-name { font-size: 11px; font-weight: var(--fw-bold); color: var(--text-secondary); display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cap-status { font-size: var(--fs-label); font-weight: var(--fw-bold); padding: 1px 6px; border-radius: 7px; flex-shrink: 0; }
/* 옅은 틴트 위의 '글자'라 채움용(--state-*)이 아니라 글자용(--state-*-fg) */
.cap-status.pending { background: rgba(251,191,36,0.18); color: var(--state-warn-fg); }
.cap-status.done { background: rgba(74,222,128,0.18); color: var(--state-ok-fg); }
.cap-status.error { background: rgba(248,113,113,0.18); color: var(--state-alert-fg); }
.cap-status.skip { background: var(--bg-button); color: var(--text-muted); }
.cap-text { flex: 1; min-height: 56px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; color: var(--text-primary); font-size: 12px; resize: vertical; line-height: 1.45; }
.cap-text:focus { outline: none; border-color: var(--accent); }
.cap-actions { display: flex; gap: 6px; }
.cap-btn { background: var(--bg-button); border: 1px solid var(--border); border-radius: 5px; color: var(--text-secondary); font-size: var(--fs-label); font-weight: var(--fw-bold); padding: 4px 10px; cursor: pointer; }
.cap-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.cap-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cap-btn.t2i { color: var(--accent); border-color: rgba(226,179,64,0.4); }
.cap-btn.t2i:hover:not(:disabled) { background: var(--accent-fill); color: var(--on-accent); }
.tab-body { flex: 1; overflow-y: auto; padding: 20px; }

.panel { max-width: 500px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.panel h3 { color: var(--text-primary); font-size: 13px; font-weight: var(--fw-bold); letter-spacing: 0; margin: 0; }

.file-drop {
  border: 2px dashed var(--border); border-radius: 8px; min-height: 100px;
  display: flex; align-items: center; justify-content: center; padding: 12px;
}
.drop-hint { color: var(--text-muted); font-size: 12px; text-align: center; }
.link-btn { min-height: 28px; padding: 0 4px; background: none; border: none; color: var(--accent); cursor: pointer; text-decoration: underline; font-size: var(--fs-meta); }
.file-list { width: 100%; max-height: 200px; overflow-y: auto; }
.file-item {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; font-size: 11px; color: var(--text-secondary); cursor: pointer;
  border-radius: 4px;
}
.file-item span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-item.active { background: var(--accent-dim); color: var(--accent); }
.file-item.done { opacity: 0.6; }
.done-badge { color: var(--state-ok-fg); font-weight: var(--fw-bold); flex: 0 !important; }
.rm-btn { background: none; border: none; color: var(--state-alert-fg); cursor: pointer; font-size: 14px; flex-shrink: 0; }
.file-count { font-size: var(--fs-label); color: var(--text-muted); }

.s-label { color: var(--text-muted); font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; }
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
/* 주 버튼: 면은 --accent-fill(글자가 4.5:1 로 읽히게 민 값), 글자는 --on-accent */
.btn-start {
  padding: 10px; background: var(--accent-fill); border: none; border-radius: 8px;
  color: var(--on-accent); font-weight: var(--fw-bold); font-size: 11px; cursor: pointer; letter-spacing: 0;
}
.btn-start:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-start.batch { background: var(--bg-button); color: var(--accent); border: 1px solid var(--accent-dim); }
/* 정지 버튼은 '채움'이라 --state-alert(글자용 -fg 아님). 그 위 글자는 흰색 고정 —
   상태 채움색이 흰 글자와 4.5:1 을 맞춘 값이고, --text-primary 는 라이트에서 검정이 된다. */
.btn-stop { padding: 10px; background: var(--state-alert); border: none; border-radius: 8px; color: #FFFFFF; font-weight: var(--fw-bold); font-size: 11px; cursor: pointer; }

/* ADetailer Layout */
.ad-layout { display: flex; gap: 0; padding: 0 !important; }
.ad-settings { width: 320px; flex-shrink: 0; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; border-right: 1px solid var(--border); }
.ad-settings h3 { color: var(--text-primary); font-size: 13px; font-weight: var(--fw-bold); letter-spacing: 0; margin: 0; }
.ad-params { display: flex; flex-direction: column; gap: 8px; }
.ad-param { display: flex; flex-direction: column; gap: 2px; }
.ad-param label { font-size: var(--fs-label); color: var(--text-muted); font-weight: var(--fw-bold); }
.ad-param input { padding: 6px 8px; font-size: 12px; }
.ad-toggle { display: flex; align-items: center; gap: 4px; font-size: var(--fs-label); color: var(--text-muted); cursor: pointer; margin-bottom: 4px; }
.ad-toggle input { width: 14px; height: 14px; accent-color: var(--accent); }
.exif-prompt-hint { font-size: var(--fs-label); color: var(--accent); background: var(--accent-dim); padding: 6px 8px; border-radius: 4px; }
.ad-actions { display: flex; flex-direction: column; gap: 6px; margin-top: auto; }

.ad-progress { display: flex; align-items: center; gap: 8px; }
.progress-bar { flex: 1; height: 6px; background: var(--bg-button); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.ad-progress span { font-size: var(--fs-label); color: var(--text-muted); font-family: monospace; }

/* Compare */
.ad-compare { flex: 1; display: flex; align-items: center; justify-content: center; padding: 20px; overflow: hidden; }
/* 썸네일 그리드가 있으면 stretch — top-left 채움 */
.ad-compare:has(.thumb-grid) { align-items: stretch; justify-content: stretch; }
.compare-split { display: flex; gap: 12px; width: 100%; height: 100%; }
.compare-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
.compare-label { font-size: var(--fs-label); font-weight: var(--fw-bold); color: var(--text-muted); letter-spacing: 0; }
.compare-col img { max-width: 100%; max-height: calc(100% - 24px); object-fit: contain; border-radius: 6px; }
.preview-single { display: flex; align-items: center; justify-content: center; }
.preview-single img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
.compare-empty { color: var(--text-muted); font-size: 13px; }

/* Batch/Upscale 우측 썸네일 그리드 */
.file-drop.compact { min-height: 80px; padding: 14px; }
.thumb-grid {
  width: 100%; height: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px; padding: 4px;
  align-content: start;
  overflow-y: auto;
}
.thumb-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex; flex-direction: column;
  transition: all 0.15s;
  aspect-ratio: 1;
}
.thumb-card:hover {
  border-color: var(--text-muted);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}
.thumb-card img {
  flex: 1; min-height: 0;
  width: 100%; object-fit: cover;
  background: var(--bg-primary);
}
.thumb-name {
  font-size: var(--fs-label); color: var(--text-secondary);
  padding: 5px 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  background: var(--bg-card);
  border-top: 1px solid var(--border);
}
/* 이 두 색은 토큰화하지 않는다: 바탕이 테마를 안 타는 검정 오버레이라
   --state-alert-fg 로 바꾸면 라이트에서 어두운 빨강이 검은 원 위에 얹혀 안 보인다.
   hover 도 채움(밝은 빨강)과 글자(검정)가 짝으로 맞춰진 값이다. */
.thumb-rm {
  position: absolute; top: 4px; right: 4px;
  width: 22px; height: 22px;
  background: rgba(0, 0, 0, 0.7); border: none;
  border-radius: 50%; color: #f87171;
  font-size: 16px; font-weight: var(--fw-bold);
  cursor: pointer; opacity: 0;
  transition: opacity 0.15s, background 0.15s;
  line-height: 1;
}
.thumb-card:hover .thumb-rm { opacity: 1; }
.thumb-rm:hover { background: rgba(248, 113, 113, 0.9); color: #000; }

/* 우측 빈 상태 */
.grid-empty {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: var(--text-muted);
}
.grid-empty-ico { font-size: 56px; opacity: 0.3; line-height: 1; }
.grid-empty-title { font-size: 15px; font-weight: var(--fw-bold); color: var(--text-secondary); }
.grid-empty-sub { font-size: 12px; color: var(--text-muted); }
</style>
