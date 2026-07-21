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
let _storeDisconnect = null
const _backendWaiters = []
const _subscriptions = new Map()
const _signalBindings = new Map()

// startup에 1회만 emit되는 설정 이벤트 — 늦게 마운트된(라우터 전환) 컴포넌트도
// 마지막 페이로드를 받도록 "sticky"로 캐싱했다가 신규 구독자에게 즉시 재생한다.
// (복원 순서 race / 단일 소스 일관성: ui_prefs·cond_rules·loraStack·weights가 항상 이김)
const STICKY_EVENTS = ['uiPrefsLoaded', 'condRulesLoaded', 'loraStackLoaded', 'globalWeightsLoaded']
const _stickyCache = Object.create(null)

// getBackend()에서 이미 받아 둔 참조도 재연결 후 새 raw backend를 바라보게 한다.
const _backendProxy = new Proxy({}, {
  get(_target, prop) {
    if (prop === '_rawBackend') return _backend
    const value = _backend?.[prop]
    if (typeof value !== 'function') return value
    return (...args) => {
      const current = _backend
      const fn = current?.[prop]
      if (typeof fn !== 'function') throw new Error(`Backend disconnected: ${String(prop)}`)
      return fn.apply(current, args)
    }
  },
  ownKeys() { return _backend ? Reflect.ownKeys(_backend) : [] },
  getOwnPropertyDescriptor() { return { enumerable: true, configurable: true } },
})

function _resolveBackendWaiters() {
  while (_backendWaiters.length) {
    try { _backendWaiters.shift()(_backendProxy) } catch {}
  }
}

function _createSignalShim() {
  const handlers = new Set()
  return {
    connect(callback) { handlers.add(callback) },
    disconnect(callback) { handlers.delete(callback) },
    _emit(...args) {
      for (const callback of [...handlers]) {
        try { callback(...args) } catch (e) { console.error('[bridge] event handler failed', e) }
      }
    },
  }
}

/** 허용 목록 WebBridgeFacade를 기존 backend 계약 모양으로 어댑트한다. */
function _adaptWebFacade(facade, capabilities) {
  const methods = new Set(capabilities.methods || [])
  const signals = new Map((capabilities.signals || []).map(name => [name, _createSignalShim()]))
  const onEvent = (name, argsJson) => {
    const signal = signals.get(name)
    if (!signal) return
    try { signal._emit(...JSON.parse(argsJson || '[]')) }
    catch (e) { console.error(`[bridge] malformed event ${name}`, e) }
  }
  facade.event.connect(onEvent)

  const target = {
    _dispose() {
      try { facade.event.disconnect(onEvent) } catch {}
    },
  }
  return new Proxy(target, {
    get(obj, prop) {
      if (Reflect.has(obj, prop)) return Reflect.get(obj, prop)
      if (signals.has(prop)) return signals.get(prop)
      if (!methods.has(prop)) return undefined
      return (...callArgs) => {
        const args = [...callArgs]
        const callback = typeof args[args.length - 1] === 'function' ? args.pop() : null
        const handleResult = (responseJson) => {
          let response
          try { response = JSON.parse(responseJson || '{}') }
          catch (e) {
            console.error(`[bridge] invalid response: ${String(prop)}`, e)
            return
          }
          if (!response.ok) {
            console.error(`[bridge] backend rejected ${String(prop)}: ${response.error || 'unknown error'}`)
            return
          }
          if (callback) callback(response.value)
        }
        if (callback) facade.invoke(String(prop), JSON.stringify(args), handleResult)
        else facade.invoke(String(prop), JSON.stringify(args))
      }
    },
    ownKeys() { return [...Reflect.ownKeys(target), ...methods, ...signals.keys()] },
    getOwnPropertyDescriptor() { return { enumerable: true, configurable: true } },
  })
}

function _dispatchEvent(name, args) {
  if (STICKY_EVENTS.includes(name)) _stickyCache[name] = args
  const callbacks = _subscriptions.get(name)
  if (!callbacks) return
  for (const callback of [...callbacks]) {
    try { callback(...args) } catch (e) { console.error(`[bridge] ${name} handler failed`, e) }
  }
}

function _ensureSignalBinding(name) {
  if (!_backend || _signalBindings.has(name)) return
  const signal = _backend[name]
  if (!signal || typeof signal.connect !== 'function') return
  const handler = (...args) => _dispatchEvent(name, args)
  signal.connect(handler)
  _signalBindings.set(name, { signal, handler })
}

function _disconnectSignalBindings() {
  for (const { signal, handler } of _signalBindings.values()) {
    try { signal.disconnect(handler) } catch {}
  }
  _signalBindings.clear()
}

function _detachBackend(backend) {
  if (!_backend || _backend !== backend) return
  _disconnectSignalBindings()
  if (_storeDisconnect) {
    try { _storeDisconnect() } catch {}
    _storeDisconnect = null
  }
  try { backend._dispose?.() } catch {}
  _backend = null
}

function _requestInitialConfig(backend) {
  if (!backend?.getInitialConfig) return
  backend.getInitialConfig((json) => {
    try {
      const payload = JSON.parse(json || '{}')
      _dispatchEvent('uiPrefsLoaded', [JSON.stringify(payload.uiPrefs || {})])
      _dispatchEvent('condRulesLoaded', [JSON.stringify(payload.condRules || { positive: [], negative: [] })])
      _dispatchEvent('globalWeightsLoaded', [JSON.stringify(payload.globalWeights || [])])
    } catch (e) {
      console.error('[bridge] initial config parse failed', e)
    }
  })
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
function _bindBackend(backend) {
  if (_backend && _backend !== backend) _detachBackend(_backend)
  console.log('[bridge] backend ready', backend ? Object.keys(backend).length + ' members' : '(null)')
  _backend = backend
  _storeDisconnect = connectStore(_backend)
  const eventNames = new Set([...STICKY_EVENTS, ..._subscriptions.keys()])
  for (const name of eventNames) _ensureSignalBinding(name)
  _resolveBackendWaiters()
}

/**
 * 웹 모드 — WebSocket transport로 연결.
 * WS URL은 Python 정적 서버가 index.html에 주입한 `window.__AISTUDIO_WS_PORT__`로 조립한다.
 * host는 location.hostname을 써서 LAN(폰/타 PC) 원격 접속에서도 올바른 주소가 된다.
 */
function _initWebSocketBridge() {
  const port = window.__AISTUDIO_WS_PORT__
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = window.__AISTUDIO_WS_URL__ || `${scheme}://${location.hostname}:${port}`
  console.log('[bridge] web mode — connecting WebSocket', wsUrl)

  let retryDelay = 1000
  let reconnectTimer = null
  let activeBackend = null

  const connect = () => {
    const socket = new WebSocket(wsUrl)
    socket.onopen = () => {
      console.log('[bridge] WebSocket open — handshaking QWebChannel')
      new QWebChannelWS(socket, (channel) => {
        const facade = channel.objects.backend
        if (!facade?.getCapabilities) {
          console.error('[bridge] web facade unavailable')
          socket.close()
          return
        }
        facade.getCapabilities((json) => {
          if (socket.readyState !== WebSocket.OPEN) return
          try {
            const backend = _adaptWebFacade(facade, JSON.parse(json || '{}'))
            activeBackend = backend
            _bindBackend(backend)
            _requestInitialConfig(backend)
            retryDelay = 1000
          } catch (e) {
            console.error('[bridge] web facade setup failed', e)
            socket.close()
          }
        })
      })
    }
    socket.onclose = (event) => {
      if (activeBackend) _detachBackend(activeBackend)
      activeBackend = null
      if (event.code === 1008) {
        console.error('[bridge] WebSocket authorization rejected — reopen the authenticated URL')
        return
      }
      console.warn(`[bridge] WebSocket closed — retrying in ${retryDelay}ms`)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connect, retryDelay)
      retryDelay = Math.min(10000, Math.round(retryDelay * 1.7))
    }
    socket.onerror = () => { try { socket.close() } catch {} }
  }
  connect()
}

/**
 * QWebChannel 초기화 — transport 자동 감지
 */
export async function initBridge() {
  // 1) 웹 모드: 서버가 주입한 값은 문서 파싱 시 이미 존재하므로 Qt transport를
  //    기다리지 않고 즉시 WebSocket으로 연결한다. (일반 브라우저의 5초 지연 방지)
  if (window.__AISTUDIO_WS_PORT__ || window.__AISTUDIO_WS_URL__) {
    _initWebSocketBridge()
    return getBackend()
  }

  // 2) Qt 임베드 모드: 동일 프로세스 transport가 존재
  const qtAvailable = await waitForQWebChannel()
  if (qtAvailable) {
    return new Promise((resolve) => {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        _bindBackend(channel.objects.backend)
        resolve(_backendProxy)
      })
    })
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
  _bindBackend(_backend)
  return _backendProxy
}

/**
 * 백엔드 객체 반환 (초기화 대기)
 */
export async function getBackend() {
  if (_backend) return _backendProxy
  return new Promise(resolve => _backendWaiters.push(resolve))
}

/**
 * Python → JS 이벤트 수신. (이름 정합성 강제는 tests/test_bridge_contract.py)
 * @param {import('./types/bridge').BackendEvent} eventName  백엔드 시그널 이름(에디터 자동완성)
 * @param {Function} callback
 * @returns {() => void} disconnect 함수 — onUnmounted에서 호출하여 리스너 해제
 */
export function onBackendEvent(eventName, callback) {
  if (!_subscriptions.has(eventName)) _subscriptions.set(eventName, new Set())
  const callbacks = _subscriptions.get(eventName)
  callbacks.add(callback)
  _ensureSignalBinding(eventName)

  // sticky: 이미 발생한 설정 이벤트면 신규 구독자에게만 최신값을 즉시 재생한다.
  if (STICKY_EVENTS.includes(eventName) && _stickyCache[eventName] !== undefined) {
    queueMicrotask(() => {
      if (!callbacks.has(callback)) return
      try { callback(..._stickyCache[eventName]) } catch {}
    })
  }

  return () => {
    callbacks.delete(callback)
    if (callbacks.size === 0) {
      _subscriptions.delete(eventName)
      if (!STICKY_EVENTS.includes(eventName)) {
        const binding = _signalBindings.get(eventName)
        if (binding) {
          try { binding.signal.disconnect(binding.handler) } catch {}
          _signalBindings.delete(eventName)
        }
      }
    }
  }
}
