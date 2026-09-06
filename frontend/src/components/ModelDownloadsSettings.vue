<template>
  <section class="model-downloads" aria-labelledby="model-downloads-title">
    <div class="section-heading">
      <div>
        <h2 id="model-downloads-title">기능별 모델 다운로드</h2>
        <p>공유 중인 모델은 다시 받지 않습니다. 파일 크기와 SHA-256 검증 후에만 설치를 완료합니다.</p>
      </div>
      <button type="button" :disabled="!connected || pending || state.busy" @click="refresh">상태 새로고침</button>
    </div>
    <p v-if="!connected" class="note" role="status">로컬 모델 설치는 데스크톱 앱에서만 사용할 수 있습니다. 앱 연결을 기다리는 중입니다.</p>
    <template v-else>
      <div class="pack-list">
        <label v-for="pack in state.packs" :key="pack.id" class="pack" :class="{ selected: selected.includes(pack.id) }">
          <input v-model="selected" type="checkbox" :value="pack.id" :disabled="state.busy || pending" />
          <span class="pack-content">
            <span class="pack-heading"><strong>{{ pack.label }}</strong><span class="badge">{{ pack.verified ? 'SHA 검증됨' : pack.ready ? '모델 발견' : `${pack.installedCount}/${pack.fileIds.length} 파일` }}</span></span>
            <span>{{ pack.description }}</span>
            <small>{{ pack.requirements }}</small>
            <small v-if="pack.downloadable === false" class="error">{{ pack.blockedReason }}</small>
          </span>
        </label>
      </div>
      <div v-if="selectedFiles.length" class="selection-summary">
        <p>선택한 {{ selected.length }}개 기능 · 중복 제외 {{ selectedFiles.length }}개 파일 · 새 다운로드 최대 {{ formatBytes(downloadBytes) }}</p>
        <p class="note">아래 실제 경로에 저장합니다. 기존 파일은 덮어쓰지 않으며, 크기가 다른 기존 파일은 직접 확인해야 합니다. 모델 준비와 백엔드·확장 설치는 별개입니다.</p>
        <details open>
          <summary>파일별 저장 위치와 출처 확인</summary>
          <ul class="file-list">
            <li v-for="file in selectedFiles" :key="file.id">
              <div><strong>{{ file.label }}</strong> · {{ formatBytes(file.size) }} · {{ statusLabel(file.status) }}</div>
              <code>{{ file.path || file.blockedReason }}</code>
              <a :href="file.sourceUrl" target="_blank" rel="noopener noreferrer">원본 모델 정보</a>
            </li>
          </ul>
        </details>
      </div>
      <div class="download-actions">
        <button type="button" class="primary" :disabled="!selected.length || pending || state.busy || blockedSelection" @click="start">선택한 모델 다운로드 / 이어받기</button>
        <button type="button" :disabled="!selected.length || pending || state.busy" @click="verify">기존 파일 SHA-256 검증</button>
        <button v-if="state.busy" type="button" :disabled="state.state === 'canceling'" @click="cancel">{{ state.state === 'canceling' ? '취소 중…' : '다운로드 / 검증 취소' }}</button>
      </div>
      <div v-if="state.busy || state.state === 'complete'" class="progress-area">
        <progress :value="progress" max="100" aria-label="모델 준비 진행률" />
        <span>{{ progress.toFixed(1) }}% · {{ formatBytes(state.downloadedBytes) }} / {{ formatBytes(state.totalBytes) }}</span>
      </div>
      <p class="note" role="status" aria-live="polite">{{ pending ? '요청 확인 중…' : state.message }}</p>
      <p v-if="state.state === 'verifying'" class="note">큰 파일의 검증에는 시간이 걸립니다. 취소하면 기존 파일과 이어받기 파일을 보존합니다.</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

interface ModelFile { id: string; label: string; size: number; path: string; status: string; sourceUrl: string; blockedReason?: string }
interface ModelPack { id: string; label: string; description: string; requirements: string; fileIds: string[]; ready: boolean; verified: boolean; installedCount: number; downloadable?: boolean; blockedReason?: string }
interface DownloadState { available: boolean; busy: boolean; state: string; message: string; error: string; actionError?: string; jobId: string; downloadedBytes: number; totalBytes: number; percent: number; files: ModelFile[]; packs: ModelPack[]; selectedPackIds?: string[]; revision?: number }
const state = ref<DownloadState>({ available: false, busy: false, state: 'idle', message: '', error: '', jobId: '', downloadedBytes: 0, totalBytes: 0, percent: 0, files: [], packs: [] })
const connected = ref(false)
const pending = ref(false)
const selected = ref<string[]>([])
const localError = ref('')
let restoredSelection = false
let disposed = false
let unsubscribe: (() => void) | undefined
let timeout: ReturnType<typeof setTimeout> | undefined
const selectedPacks = computed(() => state.value.packs.filter(pack => selected.value.includes(pack.id)))
const selectedFiles = computed(() => {
  const ids = new Set(selectedPacks.value.flatMap(pack => pack.fileIds))
  return state.value.files.filter(file => ids.has(file.id))
})
const downloadBytes = computed(() => selectedFiles.value.filter(file => file.status === 'missing').reduce((total, file) => total + file.size, 0))
const blockedSelection = computed(() => selectedPacks.value.some(pack => pack.downloadable === false))
const error = computed(() => localError.value || state.value.actionError || state.value.error)
const progress = computed(() => Math.min(100, Math.max(0, Number(state.value.percent) || 0)))
function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(0, bytes || 0).toLocaleString()} B`
}
function statusLabel(status: string) {
  return ({ missing: '다운로드 필요', present: '기존 파일 · SHA 미검증', verified: 'SHA 검증됨', mismatch: '크기 불일치 · 기존 파일 보존', blocked: '확장 설치 필요', inaccessible: '경로 접근 불가' } as Record<string, string>)[status] || status
}
function send(action: 'model_download_status' | 'model_download_start' | 'model_download_verify' | 'model_download_cancel') {
  localError.value = ''
  pending.value = true
  clearTimeout(timeout)
  timeout = setTimeout(() => { pending.value = false; localError.value = '응답을 기다리고 있습니다. 연결을 확인한 뒤 상태를 새로고침하세요.' }, 30000)
  try { requestAction(action, { packIds: [...selected.value], jobId: state.value.jobId }) }
  catch { clearTimeout(timeout); pending.value = false; localError.value = '앱 연결이 끊어졌습니다.' }
}
function refresh() { send('model_download_status') }
function start() { send('model_download_start') }
function verify() { send('model_download_verify') }
function cancel() { send('model_download_cancel') }
onMounted(async () => {
  unsubscribe = onBackendEvent('modelDownloadEvent', (raw: string) => {
    let event: Partial<DownloadState>
    try { event = JSON.parse(raw) } catch { return }
    if (!event || (event.revision !== undefined && event.revision < (state.value.revision ?? 0))) return
    clearTimeout(timeout)
    pending.value = false
    localError.value = ''
    state.value = { ...state.value, ...event }
    if (!restoredSelection && event.packs) {
      selected.value = (event.selectedPackIds || []).filter(id => event.packs?.some(pack => pack.id === id))
      restoredSelection = true
    }
  })
  const backend = await getBackend()
  if (disposed) return
  connected.value = Boolean(backend?.modelDownloadEvent)
  if (connected.value) refresh()
})
onUnmounted(() => { disposed = true; clearTimeout(timeout); unsubscribe?.() })
</script>

<style scoped>
.model-downloads { margin-top: 20px; padding: 20px; border: 1px solid var(--border); border-radius: 16px; color: var(--text-primary); background: var(--bg-card); }
.section-heading, .pack-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h2 { font-size: 15px; margin: 0 0 8px; }
p { line-height: 1.6; font-size: 12px; margin: 8px 0; }
.section-heading p, .note, small { color: var(--text-muted); }
.pack-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 10px; margin: 18px 0; }
.pack { display: flex; align-items: flex-start; gap: 10px; padding: 12px; min-width: 0; white-space: normal; border: 1px solid var(--border); border-radius: 10px; cursor: pointer; }
.pack.selected { border-color: var(--accent); }
.pack input { margin-top: 3px; flex: 0 0 auto; accent-color: var(--accent); }
.pack-content { display: grid; grid-template-columns: minmax(0, 1fr); gap: 7px; flex: 1; min-width: 0; white-space: normal; overflow-wrap: anywhere; font-size: 12px; line-height: 1.5; }
.pack-heading { align-items: flex-start; flex-wrap: wrap; }
.badge { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
small { font-size: 11px; }
.selection-summary { padding: 12px; border-radius: 10px; background: var(--bg-input); }
summary { cursor: pointer; font-size: 12px; margin-top: 10px; }
.file-list { list-style: none; padding: 0; display: grid; gap: 14px; font-size: 12px; }
code { display: block; white-space: normal; overflow-wrap: anywhere; font-size: 11px; color: var(--text-muted); margin: 5px 0; }
a { color: var(--accent); }
.download-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
button { border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; background: var(--bg-button); color: var(--text-primary); cursor: pointer; font-size: 12px; }
button.primary { border-color: var(--accent); }
button:disabled, input:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.error { color: var(--state-alert-fg, #e57373); overflow-wrap: anywhere; }
.progress-area { display: grid; gap: 6px; margin-top: 16px; font-size: 12px; }
progress { width: 100%; height: 10px; accent-color: var(--accent); }
@media (max-width: 640px) { .section-heading { align-items: flex-start; flex-direction: column; } .model-downloads { padding: 14px; } }
</style>
