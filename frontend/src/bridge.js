/**
 * QWebChannel 브릿지 — Python(PyQt6) ↔ Vue 통신
 */
import { connectStore } from './stores/widgetStore.js'

let _backend = null
let _resolveReady = null
const _ready = new Promise(resolve => { _resolveReady = resolve })

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
 * Python → JS 이벤트 수신
 */
export function onBackendEvent(eventName, callback) {
  _ready.then(backend => {
    if (backend && backend[eventName]) {
      backend[eventName].connect(callback)
    }
  })
}
