import { afterEach, describe, expect, it, vi } from 'vitest'
vi.mock('../bridge.js', () => ({ getBackend: vi.fn() }))
import { getBackend } from '../bridge.js'
import { copyTextToClipboard } from './clipboard'

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

function browserFallback(success: boolean) {
  const originalFocus = { focus: vi.fn() }
  const textarea = { value: '', style: {}, select: vi.fn(), focus: vi.fn(), remove: vi.fn(), setAttribute: vi.fn() }
  vi.stubGlobal('window', {})
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(Error('denied')) } })
  vi.stubGlobal('document', { activeElement: originalFocus, getSelection: () => null,
    createElement: () => textarea, body: { appendChild: vi.fn() }, execCommand: vi.fn(() => success) })
  return { originalFocus, textarea }
}

describe('clipboard confirmation', () => {
  it('reports failure when both browser clipboard mechanisms reject copying', async () => {
    const { originalFocus, textarea } = browserFallback(false)
    expect(await copyTextToClipboard('message')).toBe(false)
    expect(textarea.remove).toHaveBeenCalledOnce()
    expect(originalFocus.focus).toHaveBeenCalledOnce()
  })
  it('uses the native desktop slot without relying on insecure browser clipboard', async () => {
    browserFallback(false)
    vi.stubGlobal('window', { qt: { webChannelTransport: {} } })
    vi.mocked(getBackend).mockResolvedValue({ copyTextToClipboard: (_text: string, done: (ok: boolean) => void) => done(true) } as any)
    expect(await copyTextToClipboard('한국어\nsecond line')).toBe(true)
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled()
  })
  it('never sends a remote web user clipboard to the host desktop', async () => {
    browserFallback(true)
    expect(await copyTextToClipboard('web message')).toBe(true)
    expect(getBackend).not.toHaveBeenCalled()
  })
})
