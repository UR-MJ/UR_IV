export interface CaptionIdentity {
  clientToken?: string
  jobId?: string
}

export interface CaptionItemState {
  path: string
  status?: string
}

const TERMINAL_CAPTION_STATUSES = new Set(['done', 'error', 'skip'])

/** Broadcast QWebChannel events are accepted only when both scoped IDs match. */
export function matchesCaptionIdentity(
  payload: CaptionIdentity,
  clientToken: string,
  jobId: string,
): boolean {
  return Boolean(
    clientToken
    && jobId
    && payload.clientToken === clientToken
    && payload.jobId === jobId,
  )
}

/** True when the active job still has an item whose final progress was not observed. */
export function hasUnresolvedCaptionItems(
  items: readonly CaptionItemState[],
  activePaths: ReadonlySet<string>,
): boolean {
  return items.some(item => (
    activePaths.has(item.path) && !TERMINAL_CAPTION_STATUSES.has(item.status || '')
  ))
}

/** Mirror the backend's `{stem}.txt` sidecar convention for display only. */
export function captionSidecarPath(imagePath: string, outputDirectory = ''): string {
  const normalized = String(imagePath || '').replace(/\\/g, '/')
  const slash = normalized.lastIndexOf('/')
  const filename = slash >= 0 ? normalized.slice(slash + 1) : normalized
  const dot = filename.lastIndexOf('.')
  const stem = dot > 0 ? filename.slice(0, dot) : filename
  const selectedDirectory = outputDirectory.trim().replace(/\\/g, '/').replace(/\/+$/, '')
  const sourceDirectory = slash >= 0 ? normalized.slice(0, slash) : ''
  const directory = selectedDirectory || sourceDirectory
  return directory ? `${directory}/${stem}.txt` : `${stem}.txt`
}
