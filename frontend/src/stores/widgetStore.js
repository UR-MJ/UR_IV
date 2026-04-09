/**
 * 위젯 상태 저장소 — Python 프록시와 실시간 2방향 동기화
 */
import { reactive, watch } from 'vue'

const state = reactive({
  values: {},      // { widget_id: value_string }
  properties: {},  // { widget_id: { items, enabled, ... } }
})

let _backend = null

/**
 * 브릿지 연결
 */
export function connectStore(backend) {
  _backend = backend

  // 1. Python -> Vue: 개별 값 수신
  backend.widgetValueChanged.connect((id, val) => {
    if (state.values[id] !== val) {
      state.values[id] = val
    }
  })

  // 2. Python -> Vue: 속성 수신
  backend.widgetPropertyChanged.connect((id, prop, valJson) => {
    if (!state.properties[id]) state.properties[id] = {}
    try {
      state.properties[id][prop] = JSON.parse(valJson)
    } catch {
      state.properties[id][prop] = valJson
    }
  })

  // 3. Python -> Vue: 배치 업데이트
  backend.batchUpdate.connect((json) => {
    try {
      const data = JSON.parse(json)
      Object.assign(state.values, data)
    } catch (e) { console.error('[Store] Batch Error:', e) }
  })

  // 4. 초기값 로드
  backend.getAllWidgetValues((json) => {
    try {
      const data = JSON.parse(json)
      Object.assign(state.values, data)
    } catch (e) { console.error('[Store] Init Error:', e) }
  })
}

/**
 * [중요] Vue -> Python: 최적화된 동기화 엔진
 * 변경된 값만 Python 백엔드에 전송 (이전 값과 비교)
 */
let _prevSnapshot = {}
watch(() => state.values, (newVals) => {
  if (!_backend) return
  for (const [id, val] of Object.entries(newVals)) {
    const strVal = String(val)
    if (_prevSnapshot[id] !== strVal) {
      _prevSnapshot[id] = strVal
      _backend.onWidgetChanged(id, strVal)
    }
  }
}, { deep: true })

export function getValue(id) { return state.values[id] ?? '' }
export function getProperty(id, prop, def = '') { return state.properties[id]?.[prop] ?? def }

// 명시적 값 설정 (watch가 감지함)
export function setValue(id, val) { state.values[id] = val }

// 액션 요청
export function requestAction(action, payload = {}) {
  if (_backend) {
    console.log(`[Vue -> Python] Action: ${action}`, payload)
    _backend.onAction(action, JSON.stringify(payload))
  }
}

/**
 * Composable 래퍼 — PromptPanel 등에서 useWidgetStore()로 사용
 */
export function useWidgetStore() {
  return {
    widgets: state.values,
    getProperty: (id, prop, def = '') => state.properties[id]?.[prop] ?? def,
    getValue,
    setValue,
    requestAction,
  }
}

export { state }
