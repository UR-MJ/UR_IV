/**
 * 위젯 상태 저장소 — Python 프록시와 실시간 2방향 동기화
 */
import { reactive } from 'vue'

/** @type {{ values: Record<string, any>, properties: Record<string, Record<string, any>> }} */
const state = reactive({
  values: {},      // { widget_id: value_string }
  properties: {},  // { widget_id: { items, enabled, ... } }
})

let _backend = null
let _applyingFromBackend = false
const _prevSnapshot = Object.create(null)

// Vue에서 발생한 키 단위 변경만 Python으로 전송한다.
// reactive 객체 전체를 deep-watch하면 입력 한 글자마다 모든 위젯을 순회하고,
// Python에서 받은 초기값까지 다시 echo하게 된다.
const widgetValues = new Proxy(state.values, {
  set(target, id, val) {
    if (target[id] === val) return true
    target[id] = val
    if (!_applyingFromBackend && _backend) {
      const strVal = String(val)
      if (_prevSnapshot[id] !== strVal) {
        _prevSnapshot[id] = strVal
        _backend.onWidgetChanged(String(id), strVal)
      }
    }
    return true
  },
})

function applyBackendValues(data) {
  _applyingFromBackend = true
  try {
    for (const [id, val] of Object.entries(data || {})) {
      _prevSnapshot[id] = String(val)
      state.values[id] = val
    }
  } finally {
    _applyingFromBackend = false
  }
}

/**
 * 브릿지 연결
 */
export function connectStore(backend) {
  _backend = backend

  // 1. Python -> Vue: 개별 값 수신
  backend.widgetValueChanged.connect((id, val) => {
    if (state.values[id] !== val) applyBackendValues({ [id]: val })
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
      applyBackendValues(data)
    } catch (e) { console.error('[Store] Batch Error:', e) }
  })

  // 4. 초기값 로드
  backend.getAllWidgetValues((json) => {
    try {
      const data = JSON.parse(json)
      applyBackendValues(data)
    } catch (e) { console.error('[Store] Init Error:', e) }
  })
}

export function getValue(id) { return state.values[id] ?? '' }
export function getProperty(id, prop, def = '') { return state.properties[id]?.[prop] ?? def }

// 명시적 값 설정 (Proxy가 키 단위로 감지함)
export function setValue(id, val) { widgetValues[id] = val }

// 액션 요청
/**
 * Vue → Python 액션 요청. (이름 정합성 강제는 tests/test_bridge_contract.py)
 * @param {import('../types/bridge').ActionName} action  백엔드 액션 이름(에디터 자동완성)
 * @param {object} [payload]
 */
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
    widgets: widgetValues,
    getProperty: (id, prop, def = '') => state.properties[id]?.[prop] ?? def,
    getValue,
    setValue,
    requestAction,
  }
}

export { state }
