export interface ComicRecoveryMirror {
  schema: 2
  documentJson: string
  recoveryHash: string
  baseRevision: number
  baseContentHash: string
  updatedAt: number
  dirty: boolean
}

export interface ComicRecoveryMetadata {
  baseRevision: number
  baseContentHash: string
  updatedAt?: number
  dirty: boolean
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function parseComicRecovery(raw: string | null): Record<string, any> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return isRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function recoveryDocument(recovery: unknown): Record<string, any> | null {
  if (!isRecord(recovery)) return null
  if (recovery.schema !== 2) return recovery
  if (typeof recovery.documentJson !== 'string') return null
  try {
    const parsed = JSON.parse(recovery.documentJson)
    return isRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

async function sha256(text: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle
  if (!subtle) throw new Error('Web Crypto SHA-256을 사용할 수 없습니다')
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

export async function verifyComicRecoveryMirror(recovery: unknown): Promise<boolean> {
  if (!isRecord(recovery) || recovery.schema !== 2) return false
  if (typeof recovery.documentJson !== 'string' || !/^[0-9a-f]{64}$/i.test(String(recovery.recoveryHash || ''))) {
    return false
  }
  try {
    return await sha256(recovery.documentJson) === String(recovery.recoveryHash).toLowerCase()
  } catch {
    return false
  }
}

export function prepareComicDocumentForBackend(document: Record<string, any>): Record<string, any> {
  const source = JSON.parse(JSON.stringify(document || {}))
  const panels = Array.isArray(source.panels) ? source.panels.map((raw: any, panelIndex: number) => {
    const panel = isRecord(raw) ? raw : {}
    const prompt = String(panel.prompt ?? panel.imagePrompt ?? panel.image_prompt ?? '')
    const negative = String(panel.negative ?? panel.negativePrompt ?? panel.negative_prompt ?? '')
    const motion = String(panel.motion ?? panel.motionPrompt ?? panel.motion_prompt ?? '')
    const imagePath = String(panel.imagePath ?? panel.image_path ?? '')
    const videoPath = String(panel.videoPath ?? panel.video_path ?? '')
    const bubbles = Array.isArray(panel.bubbles) ? panel.bubbles.map((rawBubble: any) => {
      const bubble = isRecord(rawBubble) ? rawBubble : {}
      const kind = String(bubble.kind ?? bubble.style ?? 'speech')
      return {
        ...bubble,
        kind,
        style: kind,
        panelIndex,
        panel_index: panelIndex,
      }
    }) : []
    return {
      ...panel,
      prompt,
      imagePrompt: prompt,
      image_prompt: prompt,
      negative,
      negativePrompt: negative,
      negative_prompt: negative,
      motion,
      motionPrompt: motion,
      motion_prompt: motion,
      imagePath,
      image_path: imagePath,
      videoPath,
      video_path: videoPath,
      bubbles,
    }
  }) : []
  const style = String(source.style ?? source.artStyle ?? source.art_style ?? 'Anime')
  const artStyle = style.trim().toLowerCase()
  return {
    ...source,
    style,
    artStyle,
    art_style: artStyle,
    panels,
    bubbles: panels.flatMap((panel: any) => panel.bubbles),
  }
}

export function saveConflictDecision(
  sentChangeSequence: number,
  currentChangeSequence: number,
): 'restore-authoritative' | 'preserve-newer-local' {
  return sentChangeSequence === currentChangeSequence
    ? 'restore-authoritative'
    : 'preserve-newer-local'
}

export function shouldAcceptAuthoritativeRevision(
  currentRevision: number,
  incomingRevision: number,
): boolean {
  return Math.max(0, Math.trunc(Number(incomingRevision) || 0))
    >= Math.max(0, Math.trunc(Number(currentRevision) || 0))
}

export async function createComicRecoveryMirror(
  document: Record<string, any>,
  metadata: ComicRecoveryMetadata,
): Promise<ComicRecoveryMirror> {
  const documentJson = JSON.stringify(document)
  return {
    schema: 2,
    documentJson,
    recoveryHash: await sha256(documentJson),
    baseRevision: Math.max(0, Math.trunc(Number(metadata.baseRevision) || 0)),
    baseContentHash: String(metadata.baseContentHash || '').toLowerCase(),
    updatedAt: Number(metadata.updatedAt) || Date.now() / 1000,
    dirty: !!metadata.dirty,
  }
}
