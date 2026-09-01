<template>
  <div class="abt-overlay" @mousedown.self="close">
    <div class="abt-modal">
      <div class="abt-header">
        <div>
          <h3>A/B 프롬프트 테스트</h3>
          <span class="abt-sub">동일한 시드로 두 프롬프트를 생성하여 비교합니다 (대기열에 추가)</span>
        </div>
        <button class="abt-close" @click="close"><Icon name="close" /></button>
      </div>

      <div class="abt-body">
        <div class="abt-seedrow">
          <label>시드</label>
          <input type="number" v-model.number="seed" class="abt-seed" min="-1" />
          <span class="abt-hint">-1 또는 0 = 랜덤</span>
        </div>

        <div class="abt-group">
          <label class="abt-label a">프롬프트 A</label>
          <textarea v-model="promptA" class="abt-text" rows="4" placeholder="프롬프트 A..."></textarea>
        </div>
        <div class="abt-group">
          <label class="abt-label b">프롬프트 B</label>
          <textarea v-model="promptB" class="abt-text" rows="4" placeholder="프롬프트 B..."></textarea>
        </div>
        <div class="abt-group">
          <label class="abt-label neg">공통 네거티브</label>
          <textarea v-model="negative" class="abt-text" rows="2" placeholder="공통 네거티브..."></textarea>
        </div>
      </div>

      <div class="abt-footer">
        <span class="abt-status">{{ status }}</span>
        <div class="abt-spacer"></div>
        <button class="abt-run" @click="run"><Icon name="play" /> 대기열에 추가</button>
        <button class="abt-cancel" @click="close">취소</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

const emit = defineEmits<{ close: [] }>()

const promptA = ref('')
const promptB = ref('')
const negative = ref('')
const seed = ref(12345)
const status = ref('')

function close() { emit('close') }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') { e.stopPropagation(); close() } }

async function run() {
  if (!promptA.value.trim() && !promptB.value.trim()) {
    requestAction('show_toast', { type: 'info', msg: '프롬프트 A/B를 입력하세요' })
    return
  }
  const bk: any = await getBackend()   // QWebChannel 백엔드 — 동적 타입
  if (!bk || !bk.submitABTest) { close(); return }
  bk.submitABTest(JSON.stringify({
    prompt_a: promptA.value.trim(),
    prompt_b: promptB.value.trim(),
    negative: negative.value.trim(),
    seed: seed.value,
  }), (json: string) => {
    let r: any = null
    try { r = JSON.parse(json) } catch {}
    if (r && r.ok) {
      requestAction('show_toast', { type: 'success', msg: `A/B 대기열 추가 (${r.added}건, 시드 ${r.seed})` })
    } else {
      requestAction('show_toast', { type: 'error', msg: 'A/B 추가 실패' })
    }
    close()
  })
}

onMounted(async () => {
  window.addEventListener('keydown', onKey, true)
  const bk: any = await getBackend()
  if (bk && bk.getWidgetValue) {
    bk.getWidgetValue('main_prompt_text', (v: string) => { promptA.value = v || ''; promptB.value = v || '' })
    bk.getWidgetValue('neg_prompt_text', (v: string) => { negative.value = v || '' })
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
</script>

<style scoped>
.abt-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 2200; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.abt-modal { width: min(720px, 92vw); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-card); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.abt-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.abt-header h3 { font-size: 16px; font-weight: 800; }
.abt-sub { font-size: 11px; color: var(--text-muted); }
.abt-close { width: 30px; height: 30px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.abt-close:hover { color: var(--text-primary); border-color: var(--accent); }
.abt-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.abt-seedrow { display: flex; align-items: center; gap: 10px; }
.abt-seedrow label { font-size: 12px; font-weight: 700; color: var(--text-secondary); }
.abt-seed { width: 160px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 10px; color: var(--text-primary); font-size: 13px; }
.abt-seed:focus { outline: none; border-color: var(--accent); }
.abt-hint { font-size: 11px; color: var(--text-muted); }
.abt-group { display: flex; flex-direction: column; gap: 5px; }
.abt-label { font-size: 12px; font-weight: 700; }
.abt-label.a { color: var(--accent); }
.abt-label.b { color: #60a5fa; }
.abt-label.neg { color: #f87171; }
.abt-text { background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text-primary); font-size: 12px; resize: vertical; font-family: inherit; }
.abt-text:focus { outline: none; border-color: var(--accent); }
.abt-footer { display: flex; align-items: center; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
.abt-status { font-size: 11px; color: var(--text-muted); }
.abt-spacer { flex: 1; }
.abt-run { background: var(--accent); color: #000; border: none; border-radius: var(--radius-base); font-weight: 700; font-size: 13px; padding: 9px 18px; cursor: pointer; }
.abt-cancel { background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-weight: 700; font-size: 13px; padding: 9px 16px; cursor: pointer; }
</style>
