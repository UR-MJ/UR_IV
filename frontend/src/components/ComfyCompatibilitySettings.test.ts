import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { createRenderer, nextTick, type App } from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import source from './ComfyCompatibilitySettings.vue?raw'
import * as hostBridge from '../bridge.js'
import * as widgets from '../stores/widgetStore.js'

const bridge = vi.hoisted(() => ({ get: vi.fn(), listen: vi.fn(), action: vi.fn(), off: vi.fn() }))
vi.mock('../bridge.js', () => ({ getBackend: () => bridge.get(), onBackendEvent: (...args: unknown[]) => bridge.listen(...args) }))
vi.mock('../stores/widgetStore.js', () => ({ requestAction: (...args: unknown[]) => bridge.action(...args) }))
const compiled = compileScript(parse(source).descriptor, { id: 'compatibility-test', inlineTemplate: true })
const code = ts.transpileModule(compiled.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const exports: { default?: any } = {}
new Function('require', 'exports', code)((id: string) => {
  if (id === 'vue') return Vue
  if (id === '../bridge.js') return hostBridge
  if (id === '../stores/widgetStore.js') return widgets
  throw new Error(`Unexpected dependency ${id}`)
}, exports)
class Node {
  children: Node[] = []; parent: Node | null = null; props: Record<string, any> = {}
  constructor(public tag: string, public text = '') {}
  get textContent(): string { return this.text + this.children.map(x => x.textContent).join('') }
}
function insert(node: Node, parent: Node, anchor: Node | null = null) {
  if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  node.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
}
const renderer = createRenderer<Node, Node>({
  createElement: tag => new Node(tag), createText: text => new Node('#text', text), createComment: () => new Node('#comment'),
  insert, remove: node => { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1) },
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  parentNode: node => node.parent, nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
  patchProp: (node, key, _old, value) => { node.props[key] = value }, setScopeId: () => {},
  insertStaticContent: (text, parent, anchor) => { const node = new Node('#static', text); insert(node, parent, anchor); return [node, node] },
})
function all(root: Node): Node[] { return [root, ...root.children.flatMap(all)] }
function button(root: Node, text: string) { return all(root).find(n => n.tag === 'button' && n.textContent.includes(text))! }
let app: App | undefined
async function mount(props = {}) { const root = new Node('root'); app = renderer.createApp(exports.default, props); app.mount(root); await nextTick(); await nextTick(); return root }
function reply(requestId: string, extra = {}) {
  bridge.listen.mock.calls[0]![1](JSON.stringify({ ok: true, requestId, connected: true, serverVersion: '1', localRevisionKnown: false,
    bundled: { version: '1.1.3', fingerprint: '1234567890abcdef' }, warnings: [], references: [], referenceLabel: '미검증', referenceSource: 'https://github.com/Jeong-Luke/LAKIS',
    recipes: [{ id: 'spectrum', title: 'Spectrum', scope: '실험', status: 'missing', note: '테스트', repoUrl: 'https://github.com/sorryhyun/ComfyUI-Spectrum-KSampler', checks: [] }],
    baseline: { exists: false, savedAt: '', drift: [] }, ...extra }))
}
beforeEach(() => {
  vi.useFakeTimers(); bridge.get.mockReset(); bridge.listen.mockReset(); bridge.action.mockReset(); bridge.off.mockReset()
  bridge.get.mockResolvedValue({ comfyCompatibilityResult: {} }); bridge.listen.mockReturnValue(bridge.off)
})
afterEach(() => { app?.unmount(); app = undefined; vi.clearAllTimers(); vi.useRealTimers() })

it('refreshes only on supported native bridge and saves only on explicit click', async () => {
  const root = await mount()
  expect(bridge.action).toHaveBeenCalledTimes(1)
  const [action, payload] = bridge.action.mock.calls[0]!
  expect(action).toBe('comfy_compatibility_refresh')
  reply(payload.requestId); await nextTick()
  expect(root.textContent).toContain('GPU 실행·가중치 파일·이미지 품질을 검증했다는 뜻은 아닙니다')
  button(root, '기준으로 저장').props.onClick(); await nextTick()
  expect(bridge.action.mock.calls[1]![0]).toBe('comfy_compatibility_save_baseline')
})

it('routes extension review to existing runtime UI without installing anything', async () => {
  const open = vi.fn(), root = await mount({ 'onOpen-runtime': open })
  reply(bridge.action.mock.calls[0]![1].requestId); await nextTick()
  button(root, '설치 검토').props.onClick()
  expect(open).toHaveBeenCalledWith('https://github.com/sorryhyun/ComfyUI-Spectrum-KSampler')
  expect(bridge.action).toHaveBeenCalledTimes(1)
})

it('discards stale replies after finite timeout and retry, and disconnects on unmount', async () => {
  const root = await mount(), old = bridge.action.mock.calls[0]![1].requestId
  await vi.advanceTimersByTimeAsync(35000)
  expect(root.textContent).toContain('응답 시간이 초과')
  button(root, '조합 확인').props.onClick(); await nextTick()
  reply(old, { serverVersion: 'stale-version' }); await nextTick()
  expect(root.textContent).not.toContain('stale-version')
  reply(bridge.action.mock.calls[1]![1].requestId, { serverVersion: 'current-version' }); await nextTick()
  expect(root.textContent).toContain('current-version')
  app!.unmount(); app = undefined
  expect(bridge.off).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it('never requests native paths when the web facade does not expose the native signal', async () => {
  bridge.get.mockResolvedValue({})
  const root = await mount()
  expect(bridge.action).not.toHaveBeenCalled()
  expect(root.textContent).toContain('데스크톱 앱에서 확인')
  expect(button(root, '조합 확인').props.disabled).toBe(true)
})
