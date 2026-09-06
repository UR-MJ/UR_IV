import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { createRenderer, h, nextTick, type App } from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import chatSource from './ChatView.vue?raw'
import selectSource from '../components/CustomSelect.vue?raw'
import * as chatBridge from '../bridge.js'
import * as widgetStore from '../stores/widgetStore.js'
import * as media from '../utils/media.js'
import * as chatMarkdown from '../utils/chatMarkdown'
import * as clipboard from '../utils/clipboard'
import * as chatSettings from '../utils/chatSettings'
import * as chatGeneration from '../utils/chatGeneration'
import * as dropdownPlacement from '../utils/dropdownPlacement'

const bridge = vi.hoisted(() => ({
  handlers: new Map<string, (raw: string) => void>(),
  action: vi.fn(),
}))
vi.mock('../bridge.js', () => ({
  getBackend: async () => null,
  onBackendEvent: (name: string, callback: (raw: string) => void) => {
    bridge.handlers.set(name, callback)
    return () => bridge.handlers.delete(name)
  },
}))
vi.mock('../stores/widgetStore.js', () => ({ requestAction: bridge.action }))

// Vitest's node environment normally compiles SFCs for SSR, which cannot mount.
// Compile their current source for this renderer, using the installed compiler.
function compileClient(source: string, modules: Record<string, unknown>) {
  const script = compileScript(parse(source).descriptor, { id: 'chat-regression', inlineTemplate: true })
  const code = ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  const exports: { default?: any } = {}
  new Function('require', 'exports', code)((id: string) => {
    if (!(id in modules)) throw Error(`Unknown component dependency: ${id}`)
    return modules[id]
  }, exports)
  return exports.default
}
const CustomSelect = compileClient(selectSource, { vue: Vue, '../utils/dropdownPlacement': dropdownPlacement })
const ChatView = compileClient(chatSource, {
  vue: Vue, '../bridge.js': chatBridge, '../stores/widgetStore.js': widgetStore,
  '../utils/media.js': media, '../utils/chatMarkdown': chatMarkdown, '../utils/clipboard': clipboard,
  '../utils/chatSettings': chatSettings, '../utils/chatGeneration': chatGeneration,
  '../components/CustomSelect.vue': { default: CustomSelect },
})

// Vue's public renderer boundary supplies a tiny in-memory DOM. No browser,
// Ollama process, real clipboard or user localStorage is touched by this test.
class Node {
  children: Node[] = []
  parent: Node | null = null
  props: Record<string, any> = {}
  style: Record<string, unknown> = {}
  value = ''
  constructor(public tag: string, public text = '') {}
  get tagName() { return this.tag.toUpperCase() }
  get options() { return this.children.filter(child => child.tag === 'option') }
  get textContent(): string { return this.text + this.children.map(child => child.textContent).join('') }
  addEventListener() {}
  removeEventListener() {}
  setAttribute(name: string, value: string) { this.props[name] = value }
  removeAttribute(name: string) { delete this.props[name] }
  focus() {}
  scrollTo() {}
}
const body = new Node('body')
function insert(node: Node, parent: Node, anchor: Node | null = null) {
  if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  node.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
}
const renderer = createRenderer<Node, Node>({
  createElement: tag => new Node(tag), createText: text => new Node('#text', text),
  createComment: () => new Node('#comment'),
  insert, remove: node => { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1) },
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text; node.children = [] },
  parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
  patchProp: (node, key, _old, value) => { node.props[key] = value; if (key === 'value') node.value = value },
  querySelector: () => body, setScopeId: () => {},
  insertStaticContent: (text, parent, anchor) => { const node = new Node('#static', text); insert(node, parent, anchor); return [node, node] },
})
function find(root: Node, predicate: (node: Node) => boolean): Node | undefined {
  if (predicate(root)) return root
  for (const child of root.children) { const found = find(child, predicate); if (found) return found }
}
let app: App | undefined
beforeEach(() => {
  vi.useFakeTimers()
  bridge.handlers.clear()
  bridge.action.mockClear()
  body.children = []
  const storage = new Map([['ollamaModel', 'selected-model']])
  vi.stubGlobal('localStorage', { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value) })
  vi.stubGlobal('window', { addEventListener() {}, removeEventListener() {} })
  vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {} })
})
afterEach(() => { app?.unmount(); app = undefined; vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('replaces a timed-out model-info warning with matching late success and keeps stale replies out', async () => {
  const root = new Node('root')
  app = renderer.createApp(ChatView)
  app.component('Icon', { render: () => h('span') })
  app.mount(root)
  await nextTick()
  find(root, node => String(node.props.title || '').startsWith('대화 설정'))!.props.onClick()
  await nextTick()
  const request = bridge.action.mock.calls.find(call => call[0] === 'chat_model_info')![1]
  await vi.advanceTimersByTimeAsync(15000)
  expect(root.textContent).toContain('모델 정보를 받지 못했습니다')

  bridge.handlers.get('chatModelInfo')!(JSON.stringify({ id: 'old-request', model: 'selected-model', ok: true, info: { architecture: 'stale-model' } }))
  await nextTick()
  expect(root.textContent).not.toContain('stale-model')

  bridge.handlers.get('chatModelInfo')!(JSON.stringify({ id: request.id, model: 'selected-model', ok: true,
    info: { architecture: 'qwen3', thinkingMode: 'boolean', moe: false, vision: false } }))
  await nextTick()
  expect(root.textContent).toContain('qwen3')
  expect(root.textContent).toContain('켜기/끄기 지원')
  expect(root.textContent).not.toContain('모델 정보를 받지 못했습니다')
  expect(root.textContent).not.toContain('추론 설정은 모델 기본값으로 전달합니다')
})
