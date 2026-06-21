/**
 * QWebChannel 브릿지 — Python(PyQt6) ↔ Vue 통신
 *
 * 두 가지 transport를 지원한다 (같은 vue_bridge 객체 / 같은 계약):
 *  1) Qt 임베드 모드(run_gui.bat) — QWebEngineView 안. 동일 프로세스 직통선
 *     `window.qt.webChannelTransport`. qwebchannel.js는 Qt가 qrc로 주입.
 *  2) 웹 모드(run_WEB_gui.bat) — 일반 브라우저. WebSocket(`ws://host:port`)을
 *     transport로 사용. qwebchannel.js는 npm `qwebchannel` 패키지에서 import.
 * 두 모드 모두 `channel.objects.backend`로 동일하게 귀결되므로 이후 코드는 동일.
 */
import { connectStore } from './stores/widgetStore.js'
// 웹 모드용 QWebChannel 구현 (Qt 모드는 qrc 주입본 window.QWebChannel을 그대로 씀)
import { QWebChannel as QWebChannelWS } from 'qwebchannel'

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
 * 공통 마무리 — transport 종류와 무관하게 backend 확보 후 동일 처리
 */
function _bindBackend(backend, resolve) {
  console.log('[bridge] backend ready', backend ? Object.keys(backend).length + ' members' : '(null)')
  _backend = backend
  _installStickyCaches(_backend)
  connectStore(_backend)
  _resolveReady(_backend)
  resolve(_backend)
}

/**
 * 웹 모드 — WebSocket transport로 연결.
 * WS URL은 Python 정적 서버가 index.html에 주입한 `window.__AISTUDIO_WS_PORT__`로 조립한다.
 * host는 location.hostname을 써서 LAN(폰/타 PC) 원격 접속에서도 올바른 주소가 된다.
 */
function _initWebSocketBridge(resolve) {
  const port = window.__AISTUDIO_WS_PORT__
  const wsUrl = window.__AISTUDIO_WS_URL__ || `ws://${location.hostname}:${port}`
  console.log('[bridge] web mode — connecting WebSocket', wsUrl)

  const connect = () => {
    const socket = new WebSocket(wsUrl)
    socket.onopen = () => {
      console.log('[bridge] WebSocket open — handshaking QWebChannel')
      new QWebChannelWS(socket, (channel) => {
        const backend = channel.objects.backend
        _bindBackend(backend, resolve)
        // 웹 모드: 핸드셰이크 완료(=시그널 구독 완료) 후 시작 설정을 Python에 재요청.
        // startup의 1회 push는 브라우저 연결 전이라 유실되므로 여기서 pull한다.
        // sticky 캐시는 _bindBackend에서 이미 연결돼 있어 늦은 컴포넌트도 받는다.
        try { backend.requestInitialConfig && backend.requestInitialConfig() } catch (e) {}
      })
    }
    socket.onclose = () => {
      // 백엔드 재시작/끊김 시 자동 재연결 (페이지 새로고침 없이 복구)
      if (_backend) console.warn('[bridge] WebSocket closed — retrying in 1.5s')
      setTimeout(connect, 1500)
    }
    socket.onerror = () => { try { socket.close() } catch {} }
  }
  connect()
}

/**
 * QWebChannel 초기화 — transport 자동 감지
 */
export async function initBridge() {
  // 1) Qt 임베드 모드: 동일 프로세스 transport가 존재
  const qtAvailable = await waitForQWebChannel()
  if (qtAvailable) {
    return new Promise((resolve) => {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        _bindBackend(channel.objects.backend, resolve)
      })
    })
  }

  // 2) 웹 모드: Python 정적 서버가 WS 포트를 주입했으면 WebSocket으로 연결
  if (window.__AISTUDIO_WS_PORT__ || window.__AISTUDIO_WS_URL__) {
    return new Promise((resolve) => _initWebSocketBridge(resolve))
  }

  // 3) 개발 모드 — 목 객체 (vite dev 서버 등, 백엔드 없음)
  console.log('[bridge] no transport — using mock')
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
