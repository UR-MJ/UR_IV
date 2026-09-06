<template>
  <details class="spectrum-settings">
    <summary><span class="field-label">Spectrum 가속 · 실험 기능</span> <span>{{ enabled ? 'ON' : 'OFF' }}</span></summary>
    <p>ComfyUI의 DiTSpectrumPatch를 사용합니다. 기본값은 꺼짐이며, 속도·품질은 모델별 A/B 확인이 필요합니다. Forge와 Krea2 전용 생성에는 적용하지 않습니다.</p>
    <label class="enable"><input v-model="enabled" type="checkbox" :disabled="!connected" @change="save" /> Spectrum 사용 (다음 Comfy 생성부터)</label>
    <div v-if="enabled" class="fields">
      <label v-for="field in fields" :key="field.key">{{ field.label }}
        <input v-model.number="values[field.key]" type="number" :min="field.min" :max="field.max" :step="field.step" @input="markEdited" @change="save" />
      </label>
    </div>
    <p v-if="enabled">기본 생성 샘플러에만 적용합니다. Hires·상세 보정은 별도입니다. 매번 모델을 내리거나 서버 전체 캐시를 비우지 않습니다. 준비 + 마지막 단계보다 Steps를 크게 설정하세요.</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <small>설치된 외부 Spectrum 버전의 호환성은 아래 호환 조합 안내에서 확인하세요.</small>
    <p>앱은 샘플러별 옵션을 분리하지만, 외부 노드 내부의 GPU 복사·훅 문제까지 수정하지는 않습니다. 오래된 Spectrum 버전에서 오류가 나면 끄고 해당 확장을 확인하세요.</p>
  </details>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
const enabled = ref(false), connected = ref(false), error = ref('')
let edited = false
const fields = [
  { key: 'window_size', label: '캐시 간격', min: 1, max: 4, step: 0.1, initial: 2 },
  { key: 'flex_window', label: '간격 증가량', min: 0, max: 1, step: 0.05, initial: 0.25 },
  { key: 'warmup_steps', label: '준비 단계', min: 1, max: 150, step: 1, initial: 6 },
  { key: 'tail_actual_steps', label: '마지막 실제 계산 단계', min: 1, max: 150, step: 1, initial: 3 },
  { key: 'blend_w', label: '예측 혼합 비율', min: 0, max: 1, step: 0.05, initial: 0.3 },
  { key: 'cheby_degree', label: '예측 차수', min: 1, max: 10, step: 1, initial: 3 },
  { key: 'ridge_lambda', label: '예측 안정화 계수', min: 0.001, max: 10, step: 0.001, initial: 0.1 },
  { key: 'history_size', label: '예측 이력 크기', min: 5, max: 256, step: 1, initial: 100 },
]
const values = reactive<Record<string, number>>(Object.fromEntries(fields.map(f => [f.key, f.initial])))
let lastValid = { ...values }
let disposed = false, disconnect: (() => void) | undefined
function markEdited() { edited = true }
function apply(raw: string) {
  // Startup/sticky replies carry no revision. Once typing begins, they must
  // not overwrite this panel's draft or its last valid, locally saved tuning.
  if (disposed || edited) return
  try {
    const prefs = JSON.parse(raw).comfySpectrum || {}
    enabled.value = prefs.enabled === true
    for (const field of fields) {
      const value = prefs[field.key]
      values[field.key] = Number.isFinite(value) && value >= field.min && value <= field.max
        && (field.step !== 1 || Number.isInteger(value)) ? value : field.initial
    }
    lastValid = { ...values }
  } catch { error.value = 'Spectrum 설정을 읽지 못했습니다.' }
}
function save() {
  edited = true
  error.value = ''
  if (!enabled.value) {
    // Disabling must also recover an invalid draft for the next ON, even when
    // the native backend does not echo save_ui_prefs through uiPrefsLoaded.
    Object.assign(values, lastValid)
    requestAction('save_ui_prefs', { comfySpectrum: { enabled: false, ...lastValid } })
    return
  }
  for (const field of fields) {
    const value = values[field.key]!
    if (!Number.isFinite(value) || value < field.min || value > field.max || (field.step === 1 && !Number.isInteger(value))) {
      error.value = `${field.label}: ${field.min}~${field.max} 범위를 확인하세요.`
      return
    }
  }
  lastValid = { ...values }
  requestAction('save_ui_prefs', { comfySpectrum: { enabled: enabled.value, ...lastValid } })
}
onMounted(async () => {
  disconnect = onBackendEvent('uiPrefsLoaded', apply)
  const backend = await getBackend()
  if (disposed) return
  connected.value = Boolean(backend?.getUiPrefs)
  backend?.getUiPrefs?.((raw: string) => { if (!disposed && !edited) apply(raw) })
})
onUnmounted(() => { disposed = true; disconnect?.() })
</script>
<style scoped>
.spectrum-settings { margin: 16px 0; padding: 18px; border: 1px solid var(--border); border-radius: 14px; background: var(--bg-secondary); color: var(--text-primary); overflow-wrap: anywhere; }
summary { cursor: pointer; font-weight: var(--fw-bold); } summary span { font-size: 11px; margin-left: 8px; }
p, small { color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.enable { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 14px; }
.fields label { min-width: 0; font-size: 12px; } .fields input { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 7px; color: var(--text-primary); background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; }
[role=alert] { color: var(--state-alert-fg); }
</style>
