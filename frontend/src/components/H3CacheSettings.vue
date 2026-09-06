<template>
  <section class="h3-cache" aria-labelledby="h3-cache-title">
    <div class="cache-header">
      <div>
        <h2 id="h3-cache-title">H3 인코딩 캐시</h2>
        <p>텍스트·참조 입력의 인코딩을 재사용하고, 인코더를 내린 뒤 영상 모델을 불러옵니다.</p>
      </div>
      <ToggleSwitch v-model="enabled" aria-label="H3 인코딩 캐시 사용" :disabled="!connected" @update:model-value="save" />
    </div>
    <div class="cache-limits">
      <label>최대 용량 (GB)
        <input v-model.number="maxGB" type="number" min="1" max="64" step="1" :disabled="!connected" @change="save" />
      </label>
      <label>최대 항목 수
        <input v-model.number="maxEntries" type="number" min="1" max="256" step="1" :disabled="!connected" @change="save" />
      </label>
    </div>
    <p class="cache-note">현재 ComfyUI 서버의 전용 캐시만 관리합니다. 모델·원본 미디어는 삭제하지 않습니다. 용량 제한은 다음 캐시 저장부터 적용됩니다.</p>
    <p v-if="status?.available && status.ok" class="cache-status" role="status">
      저장된 항목 {{ status.entries }}개 · {{ formatBytes(status.bytes) }}
    </p>
    <p v-if="notice" class="cache-note" role="status">{{ notice }}</p>
    <p v-if="error" class="cache-error" role="alert">{{ error }}</p>
    <div class="cache-actions">
      <button type="button" :disabled="!connected || busy" @click="query('status')">{{ busy ? '확인 중…' : '캐시 상태 확인' }}</button>
      <button v-if="!confirmClear" type="button" :disabled="!connected || busy || !status?.available" @click="confirmClear = true">캐시 비우기</button>
      <template v-else>
        <span>인코딩 캐시를 비울까요?</span>
        <button type="button" :disabled="busy" @click="query('clear')">비우기 확인</button>
        <button type="button" :disabled="busy" @click="confirmClear = false">취소</button>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import ToggleSwitch from './ToggleSwitch.vue'

interface CacheStatus {
  requestId: string
  operation: 'status' | 'clear'
  ok: boolean
  available: boolean
  entries: number
  bytes: number
  error?: string
  removedEntries?: number
}
const enabled = ref(true)
const maxGB = ref(8)
const maxEntries = ref(32)
const connected = ref(false)
const busy = ref(false)
const confirmClear = ref(false)
const status = ref<CacheStatus | null>(null)
const error = ref('')
const notice = ref('')
let disposed = false
let pendingId = ''
let timeout: ReturnType<typeof setTimeout> | undefined
const disconnects: Array<() => void> = []

function bounded(value: unknown, fallback: number, maximum: number) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(maximum, Math.max(1, Math.round(number))) : fallback
}
function applyPrefs(raw: string) {
  try {
    const prefs = JSON.parse(raw || '{}')
    enabled.value = prefs.h3ConditioningCacheEnabled === undefined || prefs.h3ConditioningCacheEnabled === true
    maxGB.value = bounded(prefs.h3ConditioningCacheMaxGB ?? 8, 8, 64)
    maxEntries.value = bounded(prefs.h3ConditioningCacheMaxEntries ?? 32, 32, 256)
  } catch { /* Keep defaults if an older host sends invalid settings. */ }
}
function save() {
  maxGB.value = bounded(maxGB.value, 8, 64)
  maxEntries.value = bounded(maxEntries.value, 32, 256)
  requestAction('save_ui_prefs', {
    h3ConditioningCacheEnabled: enabled.value,
    h3ConditioningCacheMaxGB: maxGB.value,
    h3ConditioningCacheMaxEntries: maxEntries.value,
  })
}
function formatBytes(value: number) {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}
function query(operation: 'status' | 'clear') {
  if (!connected.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  confirmClear.value = false
  pendingId = `h3-cache-${Date.now()}-${Math.random().toString(36).slice(2)}`
  timeout = setTimeout(() => {
    busy.value = false
    pendingId = ''
    error.value = 'ComfyUI 응답을 기다리는 시간이 초과되었습니다. 연결 상태를 확인한 뒤 다시 시도하세요.'
  }, 30000)
  try {
    if (operation === 'clear') requestAction('creator_h3_cache_clear', { requestId: pendingId })
    else requestAction('creator_h3_cache_status', { requestId: pendingId })
  } catch {
    clearTimeout(timeout)
    busy.value = false
    pendingId = ''
    error.value = '백엔드 연결이 끊어졌습니다. 연결 후 다시 시도하세요.'
  }
}
onMounted(async () => {
  disconnects.push(onBackendEvent('uiPrefsLoaded', applyPrefs))
  disconnects.push(onBackendEvent('creatorCacheEvent', (raw: string) => {
    let event: CacheStatus
    try { event = JSON.parse(raw) } catch { return }
    if (!event || event.requestId !== pendingId || !pendingId) return
    clearTimeout(timeout)
    busy.value = false
    pendingId = ''
    status.value = event
    if (!event.ok) error.value = event.error || '캐시 상태를 확인하지 못했습니다.'
    else if (event.operation === 'clear') notice.value = `인코딩 캐시 ${event.removedEntries ?? 0}개를 비웠습니다.`
  }))
  const backend = await getBackend()
  if (disposed) return
  connected.value = Boolean(backend?.creatorCacheEvent && backend?.getUiPrefs)
  if (!connected.value) {
    notice.value = '앱 백엔드에 연결하면 캐시 설정과 상태를 확인할 수 있습니다.'
    return
  }
  backend.getUiPrefs((raw: string) => { if (!disposed) applyPrefs(raw) })
  query('status')
})
onUnmounted(() => {
  disposed = true
  clearTimeout(timeout)
  disconnects.forEach(disconnect => disconnect())
})
</script>

<style scoped>
.h3-cache { margin-top: 20px; padding: 20px; border: 1px solid var(--border); border-radius: 16px; background: var(--bg-card); color: var(--text-primary); }
.cache-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h2 { font-size: 15px; margin: 0 0 8px; }
p { margin: 8px 0; line-height: 1.6; }
.cache-header p, .cache-note { font-size: 12px; color: var(--text-muted); }
.cache-limits { display: flex; flex-wrap: wrap; gap: 18px; margin: 16px 0; }
.cache-limits label { display: flex; gap: 10px; align-items: center; font-size: 12px; }
input { width: 76px; min-height: 32px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); background: var(--bg-input); }
.cache-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 14px; font-size: 12px; }
button { border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; background: var(--bg-button); color: var(--text-primary); cursor: pointer; }
button:disabled, input:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.cache-status { font-size: 13px; }
.cache-error { font-size: 12px; color: var(--state-alert-fg); overflow-wrap: anywhere; }
</style>
