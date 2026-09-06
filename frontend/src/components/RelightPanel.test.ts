import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { createRenderer, h, nextTick, ref, type App } from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import ts from 'typescript'
import source from './RelightPanel.vue?raw'
import i2iSource from '../views/I2IView.vue?raw'
import * as hostBridge from '../bridge.js'
import * as widgetStore from '../stores/widgetStore.js'
import * as media from '../utils/media.js'

const host = vi.hoisted(() => ({ action: vi.fn(), off: vi.fn(), event: vi.fn(), web: false }))
vi.mock('../bridge.js', () => ({ onBackendEvent: (_name: string, callback: unknown) => { host.event(callback); return host.off } }))
vi.mock('../stores/widgetStore.js', () => ({ requestAction: host.action }))
vi.mock('../utils/media.js', () => ({ isWebMode: () => host.web }))
const script = compileScript(parse(source).descriptor, { id: 'relight-test', inlineTemplate: true })
const code = ts.transpileModule(script.content, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const compiled: { default?: any } = {}
new Function('require', 'exports', code)((name: string) => {
  if (name === 'vue') return Vue
  if (name === '../bridge.js') return hostBridge
  if (name === '../stores/widgetStore.js') return widgetStore
  if (name === '../utils/media.js') return media
  throw Error(`Unexpected component dependency: ${name}`)
}, compiled)

class Node {
  children: Node[] = []
  parent: Node | null = null
  props: Record<string, any> = {}
  constructor(public tag: string, public text = '') {}
  get textContent(): string { return this.text + this.children.map(child => child.textContent).join('') }
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
function all(root: Node, predicate: (node: Node) => boolean): Node[] {
  return [...(predicate(root) ? [root] : []), ...root.children.flatMap(child => all(child, predicate))]
}
function button(root: Node, label: string) { return all(root, node => node.tag === 'button' && node.textContent.includes(label))[0]! }
function checkbox(root: Node) { return all(root, node => node.props.type === 'checkbox')[0]! }
function range(root: Node, key: string) { return all(root, node => node.props.type === 'range' && node.props.id.endsWith(`-${key}`))[0]! }
const DATA = 'data:image/png;base64,iVBORw0KGgo='
let app: App | undefined
async function mount(initial = DATA) {
  const root = new Node('root')
  const image = ref(initial)
  const apply = vi.fn()
  app = renderer.createApp({ setup: () => () => h(compiled.default, { imageSrc: image.value, onApply: apply }) })
  app.mount(root)
  await nextTick()
  return { root, image, apply }
}
async function enable(root: Node) { checkbox(root).props.onChange({ target: { checked: true } }); await nextTick() }
function receive(event: Record<string, unknown>) { host.event.mock.calls[0]![0](JSON.stringify(event)) }
async function complete(root: Node) {
  await button(root, '미리보기 계산').props.onClick()
  await nextTick()
  const payload = host.action.mock.calls.find(([action]) => action === 'relight_preview')![1]
  receive({ action: 'relight_preview', requestId: payload.requestId, ok: true, image: DATA, width: 24, height: 16, geometry: 'luminance-approximation' })
  await nextTick()
  return payload
}
beforeEach(() => { host.action.mockReset(); host.event.mockReset(); host.off.mockReset(); host.web = false; vi.useFakeTimers() })
afterEach(() => { app?.unmount(); app = undefined; vi.clearAllTimers(); vi.useRealTimers() })

it('is collapsed and disabled by default and changing settings never executes a relight', async () => {
  const { root, apply } = await mount()
  expect(all(root, node => node.tag === 'details')[0]!.props.open).toBeUndefined()
  expect(checkbox(root).props.checked).toBe(false)
  expect(host.action).not.toHaveBeenCalled()
  await enable(root)
  expect(root.textContent).toContain('명암 기반 근사 (실제 깊이 아님)')
  expect(all(root, node => node.props.type === 'range')).toHaveLength(9)
  expect(range(root, 'shadow_length').props.disabled).toBe(true)
  range(root, 'strength').props.onInput({ target: { value: '0.7' } })
  expect(host.action).not.toHaveBeenCalled()
  expect(apply).not.toHaveBeenCalled()
})

it('keeps preview separate from input and exports only its acknowledged preview identity', async () => {
  const { root, image, apply } = await mount()
  await enable(root)
  const payload = await complete(root)
  expect(payload.image).toBe(DATA)
  expect(payload).not.toHaveProperty('image_path')
  expect(image.value).toBe(DATA); expect(apply).not.toHaveBeenCalled()
  expect(root.textContent).toContain('원본은 아직 변경하지 않았습니다')
  button(root, '별도 PNG 저장').props.onClick()
  await nextTick()
  const exported = host.action.mock.calls.find(([action]) => action === 'relight_export')![1]
  expect(exported.previewRequestId).toBe(payload.requestId)
  expect(exported.requestId).not.toBe(payload.requestId)
  receive({ action: 'relight_export', requestId: exported.requestId, ok: true, path: 'generated_images/relight/new.png' })
  await nextTick()
  expect(root.textContent).toContain('별도 PNG로 저장했습니다')
  button(root, '결과를 I2I 원본으로 사용').props.onClick()
  expect(apply).toHaveBeenCalledWith({ image: DATA, width: 24, height: 16 })
})

it('invalidates cached output on setting changes and never accepts late mismatched results', async () => {
  const { root } = await mount()
  await enable(root)
  const payload = await complete(root)
  range(root, 'azimuth').props.onInput({ target: { value: '60' } })
  await nextTick()
  expect(host.action).toHaveBeenCalledWith('relight_cancel', { requestId: payload.requestId })
  receive({ action: 'relight_preview', requestId: payload.requestId, ok: true, image: DATA })
  await nextTick()
  expect(all(root, node => node.tag === 'button' && node.textContent.includes('별도 PNG'))).toHaveLength(0)
})

it('cancels an in-flight preview after source replacement and shows validation failures', async () => {
  const { root, image, apply } = await mount()
  await enable(root)
  await button(root, '미리보기 계산').props.onClick()
  const payload = host.action.mock.calls.find(([action]) => action === 'relight_preview')![1]
  image.value = 'data:image/png;base64,AAAA'
  await nextTick()
  expect(host.action).toHaveBeenCalledWith('relight_cancel', { requestId: payload.requestId })
  receive({ action: 'relight_preview', requestId: payload.requestId, ok: true, image: DATA })
  expect(apply).not.toHaveBeenCalled()
  await button(root, '미리보기 계산').props.onClick()
  const previews = host.action.mock.calls.filter(([action]) => action === 'relight_preview')
  const retry = previews[previews.length - 1]![1]
  receive({ action: 'relight_preview', requestId: retry.requestId, ok: false, error: '원본과 같은 해상도 맵을 사용하세요.' })
  await nextTick()
  expect(root.textContent).toContain('같은 해상도')
})

it('disables the web runtime and refuses remote source URLs without fetching', async () => {
  host.web = true
  const { root } = await mount()
  expect(checkbox(root).props.disabled).toBe(true)
  await enable(root)
  expect(all(root, node => node.tag === 'button')).toHaveLength(0)
  expect(host.action).not.toHaveBeenCalled()
  app!.unmount(); app = undefined
  host.web = false
  const remote = await mount('https://external.invalid/image.png')
  await enable(remote.root)
  await button(remote.root, '미리보기 계산').props.onClick()
  await nextTick()
  expect(remote.root.textContent).toContain('외부 이미지 URL은 읽지 않습니다')
  expect(host.action.mock.calls.some(([action]) => action === 'relight_preview')).toBe(false)
})

it('releases listeners and invalidates pending work after a timeout or unmount', async () => {
  const { root } = await mount()
  await enable(root)
  await button(root, '미리보기 계산').props.onClick()
  await vi.advanceTimersByTimeAsync(120000)
  expect(root.textContent).toContain('응답이 지연')
  expect(host.action.mock.calls.some(([action]) => action === 'relight_cancel')).toBe(true)
  app!.unmount(); app = undefined
  expect(host.off).toHaveBeenCalledOnce()
})

it('wires I2I through data rather than the old image path and offers an original restore', () => {
  expect(i2iSource).toContain('<RelightPanel :image-src="imageSrc" @apply="applyRelight"')
  expect(i2iSource).toMatch(/function applyRelight[\s\S]*?imagePath\.value = ''[\s\S]*?imageSrc\.value = result\.image/)
  expect(i2iSource).toContain('조명 적용 전 원본 복원')
})
