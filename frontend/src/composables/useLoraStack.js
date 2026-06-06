import { reactive, ref, computed, watch, nextTick } from 'vue'
import { onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

/**
 * LoRA 스택 상태 + 동작 (App.vue에서 추출 — App.vue 분할 ④).
 * 단일 소스: config/ui_prefs.json 의 loraStack (Python _vue_lora_entries/_vue_lora_text로 복원).
 *
 * @param {object} deps
 * @param {object} deps.storeWidgets  위젯 스토어 reactive (main_prompt_text 등)
 * @param {Function} deps.addToast    (type, msg) 토스트
 * @param {Function} deps.saveUiPrefs (payload) ui_prefs 영속
 */
export function useLoraStack({ storeWidgets, addToast, saveUiPrefs }) {
  /** @type {import('../types/bridge').LoraEntry[]} */
  const loraStack = reactive([])

  // localStorage 복원 (빠른 폴백 — 시작 시 uiPrefs가 override)
  try {
    const saved = JSON.parse(window.localStorage.getItem('loraStack') || '[]')
    if (Array.isArray(saved)) saved.forEach(l => loraStack.push(l))
  } catch {}

  let _loraInitialized = false
  let _loraRestoring = false

  function _saveLoraStack() {
    try { window.localStorage.setItem('loraStack', JSON.stringify(loraStack)) } catch {}
    // 초기화 완료 전 빈 배열로 덮어쓰기 방지, 이후에는 빈 배열도 정상 저장
    if (!_loraInitialized && loraStack.length === 0) return
    _loraInitialized = true
    saveUiPrefs({ loraStack: loraStack.map(l => ({ ...l })) })
  }

  function syncLoraStack() {
    requestAction('set_lora_stack', {
      entries: loraStack.map(l => ({
        name: l.name || '',
        weight: Number.isFinite(Number(l.weight)) ? Number(l.weight) / 100 : 0.8,
        enabled: l.enabled !== false,
        triggerWords: Array.isArray(l.triggerWords) ? l.triggerWords : [],
      })),
    })
  }

  // LoRA 추가 (Python loraInserted 등에서 호출)
  function addLoraToStack(name, weight, triggerWords = []) {
    const existing = loraStack.find(l => l.name === name)
    if (existing) {
      existing.weight = Math.round(weight * 100); existing.enabled = true
      if (triggerWords.length) existing.triggerWords = triggerWords
    } else {
      loraStack.push({ name, weight: Math.round(weight * 100), enabled: true, triggerWords })
    }
    _saveLoraStack()
  }

  // 변경 감시 → 자동 저장 + Python 동기 (복원 중에는 무시)
  watch(loraStack, () => {
    if (_loraRestoring) return
    _saveLoraStack()
    syncLoraStack()
  }, { deep: true })

  function insertTriggerWord(tw) {
    const cur = storeWidgets.main_prompt_text || ''
    if (!cur.toLowerCase().includes(tw.toLowerCase())) {
      storeWidgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tw + ', ' : tw + ', '
      addToast('info', `트리거 워드 삽입: ${tw}`)
    } else {
      addToast('info', `이미 포함된 태그: ${tw}`)
    }
  }

  const allLorasOn = computed(() => loraStack.length > 0 && loraStack.every(l => l.enabled))
  function toggleAllLoras(on) { loraStack.forEach(l => { l.enabled = on }) }
  function insertAllTriggers() {
    const tws = []
    for (const l of loraStack) {
      if (l.enabled && Array.isArray(l.triggerWords)) {
        for (const tw of l.triggerWords) if (tw && !tws.includes(tw)) tws.push(tw)
      }
    }
    if (!tws.length) { addToast('info', '활성 LoRA의 트리거 워드가 없습니다'); return }
    const cur = (storeWidgets.main_prompt_text || '').trim()
    const lower = cur.toLowerCase()
    const add = tws.filter(tw => !lower.includes(tw.toLowerCase()))
    if (!add.length) { addToast('info', '트리거가 이미 모두 포함됨'); return }
    storeWidgets.main_prompt_text = cur ? (cur.replace(/,?\s*$/, '') + ', ' + add.join(', ')) : add.join(', ')
    addToast('success', `트리거 ${add.length}개 삽입`)
  }

  // LoRA 매니저(Vue 모달)
  const showLoraModal = ref(false)
  function onLoraAdd(p) {
    addLoraToStack(p.name, typeof p.weight === 'number' ? p.weight : 1.0, p.triggerWords || [])
    addToast('success', `LoRA 추가: ${p.name}`)
  }

  // LoRA 세트 저장/불러오기 (localStorage 'loraSets')
  const loraSets = ref({})
  try { const s = JSON.parse(window.localStorage.getItem('loraSets') || '{}'); if (s && typeof s === 'object') loraSets.value = s } catch {}
  const loraSetName = ref('')
  const loraSetSel = ref('')
  const loraSetNames = computed(() => Object.keys(loraSets.value))
  function _persistLoraSets() { try { window.localStorage.setItem('loraSets', JSON.stringify(loraSets.value)) } catch {} }
  function saveLoraSet() {
    const name = loraSetName.value.trim()
    if (!name || !loraStack.length) return
    loraSets.value = { ...loraSets.value, [name]: loraStack.map(l => ({ ...l })) }
    _persistLoraSets()
    loraSetSel.value = name; loraSetName.value = ''
    addToast('success', `LoRA 세트 저장: ${name} (${loraStack.length}개)`)
  }
  function loadLoraSet() {
    const set = loraSets.value[loraSetSel.value]
    if (!Array.isArray(set)) return
    loraStack.splice(0, loraStack.length, ...set.map(l => ({ ...l })))
    _saveLoraStack(); syncLoraStack()
    addToast('success', `세트 적용: ${loraSetSel.value} (${set.length}개)`)
  }
  function deleteLoraSet() {
    const n = loraSetSel.value
    if (!n) return
    const cp = { ...loraSets.value }; delete cp[n]
    loraSets.value = cp; _persistLoraSets(); loraSetSel.value = ''
    addToast('info', `세트 삭제: ${n}`)
  }

  // 드래그 순서 변경 — 그립(⠿)만 draggable, 삽입 위치(loraDropIdx)를 마커로 표시
  const loraDragIdx = ref(-1)   // 드래그 출발 인덱스
  const loraDropIdx = ref(-1)   // 삽입 위치 (0..length)
  function loraDragStart(i) { loraDragIdx.value = i }
  function loraDragOver(e, i) {
    // 블록 상/하 절반으로 'i 앞' / 'i+1 앞' 삽입 결정
    try {
      const r = e.currentTarget.getBoundingClientRect()
      loraDropIdx.value = (e.clientY - r.top) > r.height / 2 ? i + 1 : i
    } catch { loraDropIdx.value = i }
  }
  function loraDragEnd() { loraDragIdx.value = -1; loraDropIdx.value = -1 }
  function loraDrop() {
    const from = loraDragIdx.value
    let to = loraDropIdx.value
    loraDragIdx.value = -1; loraDropIdx.value = -1
    if (from < 0 || to < 0) return
    if (to > from) to -= 1          // 앞쪽 제거로 인덱스 보정
    if (to === from) return          // 제자리 → 무동작
    const moved = loraStack.splice(from, 1)[0]
    loraStack.splice(to, 0, moved)
    _saveLoraStack(); syncLoraStack()
  }

  // 단일 소스(ui_prefs) 복원 — App.vue uiPrefsLoaded 핸들러에서 호출
  function restoreFromPrefs(prefs) {
    if (!prefs || !Array.isArray(prefs.loraStack)) return
    _loraRestoring = true
    loraStack.splice(0, loraStack.length, ...prefs.loraStack.map(l => ({ ...l })))
    try { window.localStorage.setItem('loraStack', JSON.stringify(prefs.loraStack)) } catch {}
    nextTick(() => { _loraRestoring = false; _loraInitialized = true })
  }

  // 생성용 <lora:name:weight> 텍스트 (doGenerate에서 호출) — Python build_lora_text와 동일 포맷
  function buildActiveLoraText() {
    return loraStack.filter(l => l.enabled)
      .map(l => `<lora:${l.name}:${(l.weight / 100).toFixed(2)}>`).join(', ')
  }

  // Python → Vue: loraStackLoaded (워크플로 프로파일 적용 등). 시작 1회 active_loras emit은
  // 단일 소스 통합으로 제거됨 → 평소엔 프로파일 적용 때만 발생.
  onBackendEvent('loraStackLoaded', (json) => {
    try {
      const entries = JSON.parse(json)
      if (!Array.isArray(entries)) return
      _loraRestoring = true
      loraStack.splice(0, loraStack.length, ...entries.map(entry => ({
        name: entry.name || '',
        weight: Number.isFinite(Number(entry.weight)) ? Math.round(Number(entry.weight) * 100) : 80,
        enabled: entry.enabled !== false,
        triggerWords: Array.isArray(entry.triggerWords) ? entry.triggerWords : [],
      })))
      try { window.localStorage.setItem('loraStack', JSON.stringify(loraStack)) } catch {}
      nextTick(() => { _loraRestoring = false; _loraInitialized = true })
    } catch {}
  })

  return {
    loraStack, syncLoraStack, addLoraToStack,
    allLorasOn, toggleAllLoras, insertTriggerWord, insertAllTriggers,
    showLoraModal, onLoraAdd,
    loraSetName, loraSetSel, loraSetNames, saveLoraSet, loadLoraSet, deleteLoraSet,
    loraDragIdx, loraDropIdx, loraDragStart, loraDragOver, loraDragEnd, loraDrop,
    restoreFromPrefs, buildActiveLoraText,
  }
}
