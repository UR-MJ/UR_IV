// 조건부 프롬프트 — Search 탭 + 조건부 모달이 공유하는 상태/로직.
// (규칙 편집은 STUDIO TOOLS의 '조건부' 모달, 적용은 Search 탭의 결과 전송 시.)
import { reactive, ref, watch } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { onBackendEvent } from '../bridge.js'

export const condPositive = reactive([])
export const condNegative = reactive([])
export const condEnabled = ref(window.localStorage.getItem('condEnabled') !== 'false')  // 기본 ON

function _payload() {
  return {
    enabled: condEnabled.value,   // 마스터 토글 — 백엔드가 cond_rules.json에서 읽어 ON/OFF 판단
    positive: condPositive.filter(r => r.condition || r.target),
    negative: condNegative.filter(r => r.condition || r.target),
  }
}

let _saveTimer = null
function _autoSave() {
  const p = _payload()
  try { window.localStorage.setItem('searchCondRules', JSON.stringify(p)) } catch {}
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => requestAction('save_cond_rules', p), 800)
}
export function saveCondRules() {
  const p = _payload()
  try { window.localStorage.setItem('searchCondRules', JSON.stringify(p)) } catch {}
  requestAction('save_cond_rules', p)
}
watch(condPositive, _autoSave, { deep: true })
watch(condNegative, _autoSave, { deep: true })
watch(condEnabled, v => { try { window.localStorage.setItem('condEnabled', String(v)) } catch {}; saveCondRules() })

export function addCondRule(which) {
  const arr = which === 'neg' ? condNegative : condPositive
  arr.push({ enabled: true, condition: '', exists: true, target: '', action: 'add', location: 'main' })
}
export function removeCondRule(which, i) {
  (which === 'neg' ? condNegative : condPositive).splice(i, 1)
}

let _loaded = false
export function loadCondRules() {
  if (_loaded) return
  _loaded = true
  // 1) localStorage 즉시 복원
  try {
    const cr = window.localStorage.getItem('searchCondRules')
    if (cr) {
      const d = JSON.parse(cr)
      if (Array.isArray(d.positive)) { condPositive.splice(0); d.positive.forEach(r => condPositive.push(r)) }
      if (Array.isArray(d.negative)) { condNegative.splice(0); d.negative.forEach(r => condNegative.push(r)) }
    }
  } catch {}
  // 2) 백엔드(config/cond_rules.json) — localStorage가 비었을 때만 채움
  onBackendEvent('condRulesLoaded', (json) => {
    try {
      const d = JSON.parse(json)
      if (condPositive.length === 0 && Array.isArray(d.positive)) d.positive.forEach(r => condPositive.push(r))
      if (condNegative.length === 0 && Array.isArray(d.negative)) d.negative.forEach(r => condNegative.push(r))
      if (typeof d.enabled === 'boolean' && window.localStorage.getItem('condEnabled') === null) condEnabled.value = d.enabled
    } catch {}
  })
}

// 생성/큐 전송 시 적용할 규칙 (condEnabled가 꺼져있으면 빈 목록)
export function condRulesPayload() {
  if (!condEnabled.value) return { cond_positive: [], cond_negative: [] }
  return {
    cond_positive: condPositive.filter(r => r.enabled && r.condition && r.target),
    cond_negative: condNegative.filter(r => r.enabled && r.condition && r.target),
  }
}
