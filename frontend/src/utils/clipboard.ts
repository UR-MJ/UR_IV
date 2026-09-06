import { getBackend } from '../bridge.js'

/** Confirm a copy; remote web clients must never write the host PC clipboard. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if ((window as any).qt?.webChannelTransport) {
    try {
      const backend = await Promise.race([
        getBackend(), new Promise<null>(resolve => setTimeout(() => resolve(null), 1500)),
      ])
      if (backend?.copyTextToClipboard) {
        return await new Promise<boolean>(resolve => {
          const timer = setTimeout(() => resolve(false), 1500)
          backend.copyTextToClipboard(text, (ok: boolean) => { clearTimeout(timer); resolve(ok === true) })
        })
      }
    } catch { /* older desktop bridge: try the browser's local clipboard */ }
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch { /* insecure HTTP/QWebEngine or a denied browser permission */ }
  const focused = document.activeElement as HTMLElement | null
  const selection = document.getSelection()
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : []
  const field = document.createElement('textarea')
  field.value = text
  field.setAttribute('readonly', '')
  field.style.position = 'fixed'
  field.style.opacity = '0'
  field.style.pointerEvents = 'none'
  document.body.appendChild(field)
  try {
    field.focus()
    field.select()
    return document.execCommand('copy') === true
  } catch { return false }
  finally {
    field.remove()
    focused?.focus({ preventScroll: true })
    if (selection && ranges.length) {
      selection.removeAllRanges()
      ranges.forEach(range => selection.addRange(range))
    }
  }
}
