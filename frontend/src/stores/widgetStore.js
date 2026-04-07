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
 * [중요] Vue -> Python: 자동 동기화 엔진
 * state.values의 어떤 값이든 바뀌면 즉시 Python 백엔드에 보고합니다.
 */
watch(() => state.values, (newVals) => {
  if (!_backend) return
  for (const [id, val] of Object.entries(newVals)) {
    // 값이 존재하고 백엔드에 보고할 준비가 된 경우만 전송
    _backend.onWidgetChanged(id, String(val))
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
