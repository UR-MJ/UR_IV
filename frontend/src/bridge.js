/**
 * QWebChannel 브릿지 — Python(PyQt6) ↔ Vue 통신
 */
import { connectStore } from './stores/widgetStore.js'

let _backend = null
let _resolveReady = null
const _ready = new Promise(resolve => { _resolveReady = resolve })

// startup에 1회만 emit되는 설정 이벤트 — 늦게 마운트된(라우터 전환) 컴포넌트도
// 마지막 페이로드를 받도록 "sticky"로 캐싱했다가 신규 구독자에게 즉시 재생한다.
// (복원 순서 race / 단일 소스 일관성: ui_prefs·cond_rules·loraStack·weights가 항상 이김)
const STICKY_EVENTS = ['uiPrefsLoaded', 'condRulesLoaded', 'loraStackLoaded', 'globalWeightsLoaded']
const _stickyCache = Object.create(null)
function _installStickyCaches(backend) {
  if (!backend) return
  for (const name of STICKY_EVENTS) {
    const sig = backend[name]
    if (sig && typeof sig.connect === 'function') {
      // bridge가 가장 먼저(구독 컴포넌트보다 앞서) 연결 → 모든 emit을 캐싱
      sig.connect((...args) => { _stickyCache[name] = args })
    }
  }
}

/**
 * QWebChannel 사용 가능할 때까지 대기
 */
function waitForQWebChannel(maxWait = 5000) {
  return new Promise((resolve) => {
    if (window.QWebChannel && window.qt?.webChannelTransport) {
      resolve(true)
      return
    }
    const start = Date.now()
    const check = () => {
      if (window.QWebChannel && window.qt?.webChannelTransport) {
        resolve(true)
      } else if (Date.now() - start > maxWait) {
        resolve(false) // 타임아웃 → 개발 모드
      } else {
        setTimeout(check, 50)
      }
    }
    setTimeout(check, 50)
  })
}

/**
 * QWebChannel 초기화
 */
export async function initBridge() {
  const available = await waitForQWebChannel()

  if (available) {
    return new Promise((resolve) => {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        _backend = channel.objects.backend
        _installStickyCaches(_backend)
        connectStore(_backend)
        _resolveReady(_backend)
        resolve(_backend)
      })
    })
  } else {
    // 개발 모드 — 목 객체
    console.log('[bridge] QWebChannel not available, using mock')
    _backend = {
      onWidgetChanged: (id, v) => console.log(`[mock] widget ${id} = ${v}`),
      onAction: (a, p) => console.log(`[mock] action ${a}`, p),
      onTabSwitch: (t) => console.log(`[mock] tab ${t}`),
      getAllWidgetValues: (cb) => cb('{}'),
      getSettings: (cb) => cb('{}'),
      _mock: true,
    }
    connectStore(_backend)
    _resolveReady(_backend)
    return _backend
  }
}

/**
 * 백엔드 객체 반환 (초기화 대기)
 */
export async function getBackend() {
  return _ready
}

/**
 * Python → JS 이벤트 수신. (이름 정합성 강제는 tests/test_bridge_contract.py)
 * @param {import('./types/bridge').BackendEvent} eventName  백엔드 시그널 이름(에디터 자동완성)
 * @param {Function} callback
 * @returns {() => void} disconnect 함수 — onUnmounted에서 호출하여 리스너 해제
 */
export function onBackendEvent(eventName, callback) {
  let _signal = null
  let _connected = false
  _ready.then(backend => {
    if (backend && backend[eventName]) {
      _signal = backend[eventName]
      _signal.connect(callback)
      _connected = true
      // sticky: 이미 발생한 1회성 설정 이벤트면 최신 페이로드를 즉시 재생 (늦은 마운트 대응)
      if (STICKY_EVENTS.includes(eventName) && _stickyCache[eventName] !== undefined) {
        try { callback(..._stickyCache[eventName]) } catch {}
      }
    }
  })
  return () => {
    if (_connected && _signal) {
      try { _signal.disconnect(callback) } catch {}
      _connected = false
    }
  }
}
