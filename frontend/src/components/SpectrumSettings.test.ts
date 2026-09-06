import { afterEach, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import source from './SpectrumSettings.vue?raw'

const action = vi.fn(), read = vi.fn(), off = vi.fn()
const lastCall = () => action.mock.calls[action.mock.calls.length - 1]
let prefsEvent: ((raw: string) => void) | undefined
const compiled = compileScript(parse(source).descriptor, { id: 'spectrum-test', inlineTemplate: true })
const code = ts.transpileModule(compiled.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const output: { default?: any } = {}
new Function('require', 'exports', code)((id: string) => {
  // Keep real v-model directives: listener ordering is part of this regression.
  if (id === 'vue') return Vue
  if (id === '../bridge.js') return { getBackend: async () => ({ getUiPrefs: read }), onBackendEvent: (_event: string, receive: (raw: string) => void) => { prefsEvent = receive; return off } }
  if (id === '../stores/widgetStore.js') return { requestAction: action }
  throw Error(id)
}, output)
class Node {
  children: Node[] = []; parent?: Node; props: Record<string, any> = {}
  listeners = new Map<string, Set<(event: any) => void>>()
  type = ''; checked = false; private _value = ''
  constructor(public tag: string, public text = '') {}
  get tagName() { return this.tag.toUpperCase() }
  getRootNode() { return document }
  get value() { return this._value }
  set value(value: unknown) { this._value = String(value ?? '') }
  addEventListener(name: string, fn: (event: any) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name)!.add(fn)
  }
  dispatchEvent(event: { type: string; target?: Node }) {
    for (const fn of this.listeners.get(event.type) || []) fn({ ...event, target: this })
    return true
  }
}
const node = (tag: string, text = ''): Node => new Node(tag, text)
const renderer = Vue.createRenderer<Node, Node>({
  createElement: tag => node(tag), createText: text => node('#text', text), createComment: text => node('#comment', text),
  insert(child, parent, anchor) { child.parent = parent; const i = anchor ? parent.children.indexOf(anchor) : -1; parent.children.splice(i < 0 ? parent.children.length : i, 0, child) },
  remove(child) { const parent = child.parent; if (parent) parent.children.splice(parent.children.indexOf(child), 1) },
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  parentNode: node => node.parent ?? null, nextSibling: () => null,
  patchProp: (node, key, old, value) => {
    node.props[key] = value
    if (key === 'type') node.type = String(value)
    if (/^on[A-Z]/.test(key) && !key.startsWith('onUpdate:') && !old) {
      node.addEventListener(key.slice(2).toLowerCase(), event => node.props[key]?.(event))
    }
  }, setScopeId: () => {},
  insertStaticContent(text, parent) { const child = node('#static', text); child.parent = parent; parent.children.push(child); return [child, child] },
})
let app: Vue.App | undefined
const inputs = (root: Node): Node[] => [...(root.tag === 'input' ? [root] : []), ...root.children.flatMap(inputs)]
async function mount(prefs = '{}') {
  vi.stubGlobal('Document', class {})
  vi.stubGlobal('ShadowRoot', class {})
  vi.stubGlobal('document', { activeElement: null })
  prefsEvent = undefined
  action.mockReset(); read.mockReset(); off.mockReset()
  read.mockImplementation((callback: (raw: string) => void) => callback(prefs))
  const root = node('root'); app = renderer.createApp(output.default); app.mount(root)
  await Vue.nextTick(); await Vue.nextTick(); return root
}
async function change(input: Node, value: unknown) { input.props['onUpdate:modelValue'](value); input.props.onChange(); await Vue.nextTick() }
afterEach(() => { app?.unmount(); app = undefined; vi.unstubAllGlobals() })

it('defaults off and does not save during mount', async () => {
  const root = await mount(); expect(inputs(root)).toHaveLength(1); expect(action).not.toHaveBeenCalled()
})
it('preserves valid tuning when disabled after an invalid draft', async () => {
  const root = await mount(JSON.stringify({ comfySpectrum: { enabled: true, warmup_steps: 12 } }))
  await change(inputs(root)[3]!, 0) // invalid warmup; must not reach config
  expect(action).not.toHaveBeenCalled()
  await change(inputs(root)[0]!, false)
  expect(action).toHaveBeenLastCalledWith('save_ui_prefs', expect.objectContaining({ comfySpectrum: expect.objectContaining({ enabled: false, warmup_steps: 12 }) }))
})
it('writes validated settings only and supports re-enabling', async () => {
  const root = await mount(); await change(inputs(root)[0]!, true)
  expect(action).toHaveBeenLastCalledWith('save_ui_prefs', expect.objectContaining({ comfySpectrum: expect.objectContaining({ enabled: true, warmup_steps: 6 }) }))
  await change(inputs(root)[1]!, 2.5)
  expect(action.mock.calls[action.mock.calls.length - 1]?.[1].comfySpectrum.window_size).toBe(2.5)
})
it('does not replace edited tuning with a late startup preference event', async () => {
  const original = JSON.stringify({ comfySpectrum: { enabled: true, window_size: 2 } })
  const root = await mount(original)
  await change(inputs(root)[1]!, 2.4)
  prefsEvent!(original)
  await Vue.nextTick()
  await change(inputs(root)[0]!, false)
  await change(inputs(root)[0]!, true)
  expect(action.mock.calls[action.mock.calls.length - 1]?.[1].comfySpectrum.window_size).toBe(2.4)
})
it('keeps typed decimal through blur and off/on with synchronous saved-prefs echo', async () => {
  const root = await mount(JSON.stringify({ comfySpectrum: { enabled: true } }))
  action.mockImplementation((_name, payload) => prefsEvent!(JSON.stringify(payload)))
  const field = inputs(root)[1]!
  field.value = '2.4'; field.dispatchEvent({ type: 'input' })
  await Vue.nextTick()
  field.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  expect(lastCall()?.[1].comfySpectrum.window_size).toBe(2.4)
  const toggle = inputs(root)[0]!
  toggle.checked = false; toggle.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  toggle.checked = true; toggle.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  expect(inputs(root)[1]!.value).toBe('2.4')
  expect(lastCall()?.[1].comfySpectrum.window_size).toBe(2.4)
})
it('ignores a late getUiPrefs callback after a local edit', async () => {
  const root = await mount(JSON.stringify({ comfySpectrum: { enabled: true } }))
  const oldCallback = read.mock.calls[0]![0]
  const field = inputs(root)[1]!
  field.value = '2.4'; field.dispatchEvent({ type: 'input' }); await Vue.nextTick()
  oldCallback(JSON.stringify({ comfySpectrum: { enabled: true, window_size: 2 } })); await Vue.nextTick()
  expect(inputs(root)[1]!.value).toBe('2.4')
  field.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  expect(lastCall()?.[1].comfySpectrum.window_size).toBe(2.4)
})
it('recovers last valid tuning on off/on after invalid input without a save echo', async () => {
  const root = await mount(JSON.stringify({ comfySpectrum: { enabled: true, warmup_steps: 12 } }))
  const field = inputs(root)[3]!
  field.value = '0'; field.dispatchEvent({ type: 'input' }); await Vue.nextTick()
  field.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  expect(action).not.toHaveBeenCalled()
  const toggle = inputs(root)[0]!
  toggle.checked = false; toggle.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  toggle.checked = true; toggle.dispatchEvent({ type: 'change' }); await Vue.nextTick()
  expect(inputs(root)[3]!.value).toBe('12')
  expect(lastCall()?.[1].comfySpectrum).toEqual(expect.objectContaining({ enabled: true, warmup_steps: 12 }))
})
