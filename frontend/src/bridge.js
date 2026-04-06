/**
 * QWebChannel 브릿지 — Python(PyQt6) ↔ Vue 통신
 */

let _backend = null
let _resolveReady = null
const _ready = new Promise(resolve => { _resolveReady = resolve })

/**
 * QWebChannel 초기화 (PyQt에서 qwebchannel.js 주입 후 호출됨)
 */
export function initBridge() {
  return new Promise((resolve) => {
    if (window.qt && window.qt.webChannelTransport) {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        _backend = channel.objects.backend
        _resolveReady(_backend)
        resolve(_backend)
      })
    } else {
      // 개발 모드 (브라우저에서 직접 열 때) — 목 객체
      _backend = {
        generate: async () => console.log('[mock] generate'),
        getSettings: async () => ({}),
        setPrompt: async () => {},
        _mock: true,
      }
      _resolveReady(_backend)
      resolve(_backend)
    }
  })
}

/**
 * 백엔드 객체 반환 (초기화 대기)
 */
export async function getBackend() {
  return _ready
}

/**
 * Python → JS 이벤트 수신용 (PyQt signal → JS callback)
 */
export function onBackendEvent(eventName, callback) {
  _ready.then(backend => {
    if (backend && backend[eventName]) {
      backend[eventName].connect(callback)
    }
  })
}
