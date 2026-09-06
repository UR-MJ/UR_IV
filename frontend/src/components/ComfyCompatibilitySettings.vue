<template>
  <section class="compatibility" aria-labelledby="comfy-compatibility-heading" :aria-busy="busy">
    <header>
      <div><h3 id="comfy-compatibility-heading">ComfyUI 호환 조합 안내</h3><p>설정된 Comfy 서버의 노드·입력 타입·모델 목록과 버전을 비교합니다. 확인 과정에서 설치하거나 서버를 재시작하지 않습니다.</p></div>
      <button type="button" :disabled="busy || !available" @click="query(false)">조합 확인</button>
    </header>
    <p v-if="!available">데스크톱 앱에서 확인할 수 있습니다. 웹 미리보기에는 로컬 설치 정보를 공개하지 않습니다.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="report">
      <div class="summary" role="status">
        <span>서버 {{ report.connected ? '응답 확인' : '연결 확인 필요' }} · 버전 {{ report.serverVersion || '확인 불가' }}</span>
        <span>앱 번들 {{ report.bundled.version || '버전 미표기' }} · 소스 {{ report.bundled.fingerprint?.slice(0, 12) || '확인 불가' }}</span>
        <span v-if="report.localRevisionKnown">번들 디스크 비교: {{ report.bundled.diskMatch === true ? '앱 소스와 같음' : report.bundled.diskMatch === false ? '다름 · 동기화/재시작 확인' : '확인 불가' }}</span>
        <span v-else>원격/별도 실행 서버의 설치 커밋은 이 PC의 설치 정보와 혼동하지 않습니다.</span>
      </div>
      <p>아래의 ‘입력 확인’은 스키마 확인 결과입니다. GPU 실행·가중치 파일·이미지 품질을 검증했다는 뜻은 아닙니다.</p>
      <p v-for="warning in report.warnings" :key="warning" class="warning">{{ warning }}</p>
      <div class="recipes">
        <article v-for="recipe in report.recipes" :key="recipe.id">
          <div class="recipe-head"><h4>{{ recipe.title }}</h4><span class="badge" :data-status="recipe.status">{{ label(recipe.status) }}</span></div>
          <small>{{ recipe.scope }}</small>
          <ul><li v-for="check in recipe.checks" :key="check.label"><span>{{ check.label }}</span><strong>{{ label(check.status) }}</strong><small>{{ check.detail }}</small></li></ul>
          <p>{{ recipe.note }}</p>
          <button type="button" @click="emit('open-runtime', recipe.repoUrl)">{{ recipe.repoUrl ? '확장 관리에서 설치 검토' : 'Comfy 엔진·확장 관리 열기' }}</button>
        </article>
      </div>
      <details>
        <summary>상류 프로젝트 버전 조합과 비교</summary>
        <p>{{ report.referenceLabel }}. ‘다름’은 즉시 불호환이라는 뜻이 아닙니다. 아래 버전으로 자동 변경하지 않습니다.</p>
        <ul class="references"><li v-for="item in report.references" :key="item.id"><strong>{{ item.name }}</strong><span>참고 {{ (item.commit || item.version).slice(0, 12) }}</span><span>현재 {{ item.current?.slice(0, 12) || '확인 불가' }} · {{ referenceLabel(item.status) }}</span></li></ul>
        <a :href="report.referenceSource" target="_blank" rel="noopener noreferrer">참고한 설치기 소스 보기</a>
      </details>
      <div class="baseline">
        <h4>내 환경 비교 기준</h4><p>현재 감지된 버전·관련 노드 스키마·모델 목록의 해시를 config에 저장합니다. 모델 파일이나 프롬프트는 저장하지 않습니다.</p>
        <button type="button" :disabled="busy || !report.connected" @click="query(true)">{{ report.baseline.exists ? '현재 조합으로 기준 갱신' : '현재 조합을 기준으로 저장' }}</button>
        <p v-if="report.baseline.exists">저장: {{ report.baseline.savedAt }} · {{ report.baseline.drift.length ? `${report.baseline.drift.length}개 변경/확인 불가` : '현재 확인 항목에서 변경 없음' }}</p>
        <ul v-if="report.baseline.drift.length"><li v-for="drift in report.baseline.drift" :key="drift.field">{{ drift.field }}: {{ drift.detail }}</li></ul>
        <p v-if="report.message" role="status">{{ report.message }}</p>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

type Check = { label: string; status: string; detail: string }
type Recipe = { id: string; title: string; scope: string; note: string; repoUrl: string; status: string; checks: Check[] }
type Report = { connected: boolean; serverVersion: string; localRevisionKnown: boolean; warnings: string[];
  bundled: { version: string; fingerprint: string; diskMatch?: boolean | null }; recipes: Recipe[];
  references: { id: string; name: string; version: string; commit: string; current: string; status: string }[];
  referenceSource: string; referenceLabel: string; baseline: { exists: boolean; savedAt: string; drift: { field: string; detail: string }[] }; message?: string }

const emit = defineEmits<{ 'open-runtime': [repoUrl: string] }>()
const busy = ref(false), available = ref(false), error = ref(''), report = ref<Report | null>(null)
let requestId = '', serial = 0, disposed = false, timeout: ReturnType<typeof setTimeout> | undefined
let disconnect: (() => void) | undefined
function label(status: string) { return ({ available: '입력 확인', missing: '추가 확인 필요', mismatch: '입력 불일치', unknown: '미확인' } as Record<string, string>)[status] || status }
function referenceLabel(status: string) { return ({ same: '참고값과 같음', different: '참고값과 다름', unknown: '미확인' } as Record<string, string>)[status] || status }
function query(save: boolean) {
  if (busy.value || !available.value) return
  busy.value = true; error.value = ''; requestId = `compat-${Date.now()}-${++serial}`
  clearTimeout(timeout)
  timeout = setTimeout(() => { busy.value = false; error.value = '서버 응답 시간이 초과되었습니다. 연결을 확인하고 다시 시도하세요.'; requestId = '' }, 35000)
  requestAction(save ? 'comfy_compatibility_save_baseline' : 'comfy_compatibility_refresh', { requestId })
}
onMounted(async () => {
  disconnect = onBackendEvent('comfyCompatibilityResult', (raw: string) => {
    if (disposed) return
    try {
      const value = JSON.parse(raw)
      if (!requestId || value.requestId !== requestId) return
      clearTimeout(timeout); busy.value = false; requestId = ''
      if (!value.ok) { error.value = value.error || '조합을 확인하지 못했습니다.'; return }
      report.value = value
    } catch { busy.value = false; error.value = '호환 조합 응답을 읽지 못했습니다.' }
  })
  const backend = await getBackend()
  if (disposed) return
  available.value = Boolean(backend.comfyCompatibilityResult)
  if (available.value) query(false)
})
onUnmounted(() => { disposed = true; clearTimeout(timeout); disconnect?.() })
</script>

<style scoped>
.compatibility { padding: 20px; border: 1px solid var(--border); border-radius: 14px; background: var(--bg-card); color: var(--text-primary); min-width: 0; }
header, .recipe-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
header > div, article { min-width: 0; }
h3, h4 { margin: 0; font-size: 14px; }
p { font-size: 12px; color: var(--text-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.summary { display: grid; gap: 6px; font-size: 12px; margin: 12px 0; }
.recipes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr)); gap: 12px; }
article { border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
small { color: var(--text-muted); font-size: 11px; overflow-wrap: anywhere; }
ul { list-style: none; padding: 0; margin: 12px 0; }
li { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 6px 0; font-size: 11px; overflow-wrap: anywhere; }
li > span:first-child { flex: 1; min-width: 0; }
li small { flex-basis: 100%; }
.badge { white-space: nowrap; font-size: 11px; color: var(--text-secondary); }
.badge[data-status="available"] { color: var(--state-ok-fg); }
.badge[data-status="missing"], .warning { color: var(--state-warn-fg); }
.error { color: var(--state-alert-fg); }
button { flex-shrink: 0; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-button); color: var(--text-primary); font-size: 12px; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
details, .baseline { margin-top: 18px; border-top: 1px solid var(--border); padding-top: 14px; }
summary { cursor: pointer; font-size: 13px; }
a { color: var(--accent); font-size: 12px; }
@media (max-width: 600px) { .compatibility { padding: 14px; } header { align-items: flex-start; flex-direction: column; } }
</style>
