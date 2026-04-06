/**
 * 위젯 상태 저장소 — Python 프록시와 동기화
 *
 * Python(WidgetProxy) ↔ VueBridge ↔ widgetStore ↔ Vue 컴포넌트
 */
import { reactive } from 'vue'

// 모든 위젯의 값과 속성을 저장
const state = reactive({
  values: {},      // { widget_id: value_string }
  properties: {},  // { widget_id: { placeholder, enabled, items, ... } }
})

let _backend = null

/**
 * 브릿지 연결 (App.vue에서 초기화 시 호출)
 */
export function connectStore(backend) {
  _backend = backend

  // Python → Vue: 개별 위젯 값 변경
  if (backend.widgetValueChanged) {
    backend.widgetValueChanged.connect((widgetId, value) => {
      state.values[widgetId] = value
    })
  }

  // Python → Vue: 위젯 속성 변경 (placeholder, items, enabled 등)
  if (backend.widgetPropertyChanged) {
    backend.widgetPropertyChanged.connect((widgetId, prop, valueJson) => {
      if (!state.properties[widgetId]) {
        state.properties[widgetId] = {}
      }
      try {
        state.properties[widgetId][prop] = JSON.parse(valueJson)
      } catch {
        state.properties[widgetId][prop] = valueJson
      }
    })
  }

  // Python → Vue: 배치 업데이트 (settings load 시)
  if (backend.batchUpdate) {
    backend.batchUpdate.connect((jsonStr) => {
      try {
        const batch = JSON.parse(jsonStr)
        Object.entries(batch).forEach(([id, val]) => {
          state.values[id] = val
        })
      } catch (e) {
        console.error('[widgetStore] batch parse error:', e)
      }
    })
  }

  // 초기 전체 값 로드
  if (backend.getAllWidgetValues) {
    backend.getAllWidgetValues((jsonStr) => {
      try {
        const all = JSON.parse(jsonStr)
        Object.entries(all).forEach(([id, val]) => {
          state.values[id] = val
        })
      } catch (e) {
        console.error('[widgetStore] init load error:', e)
      }
    })
  }
}

/**
 * 위젯 값 가져오기 (반응형)
 */
export function getValue(widgetId) {
  return state.values[widgetId] ?? ''
}

/**
 * 위젯 속성 가져오기 (반응형)
 */
export function getProperty(widgetId, prop, defaultVal = '') {
  return state.properties[widgetId]?.[prop] ?? defaultVal
}

/**
 * Vue에서 값 변경 → Python에 전달
 */
export function setValue(widgetId, value) {
  state.values[widgetId] = value
  if (_backend && _backend.onWidgetChanged) {
    _backend.onWidgetChanged(widgetId, String(value))
  }
}

/**
 * 액션 요청 (버튼 클릭 등)
 */
export function requestAction(action, payload = {}) {
  if (_backend && _backend.onAction) {
    _backend.onAction(action, JSON.stringify(payload))
  }
}

/**
 * 탭 전환 요청
 */
export function switchTab(tabId) {
  if (_backend && _backend.onTabSwitch) {
    _backend.onTabSwitch(tabId)
  }
}

// 반응형 state export (Vue 컴포넌트에서 직접 참조 가능)
export { state }
