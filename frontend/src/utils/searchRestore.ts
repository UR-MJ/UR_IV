export interface SearchCacheRestore<T> {
  active: T[]
  base: T[]
  isFiltered: boolean
}

export interface SearchResultLineage {
  label: string
  fingerprint: string
  snapshot_id: string
}

export interface SearchDeckUpdate<T> {
  results: T[]
  lineage: SearchResultLineage
}

/** Parse the additive backend lineage event without trusting malformed JSON. */
export function parseSearchResultLineage(raw: string): SearchResultLineage | null {
  try {
    const value = JSON.parse(raw)
    if (!value || typeof value !== 'object') return null
    const label = value.label
    const fingerprint = value.fingerprint
    const snapshotId = value.snapshot_id
    if (typeof label !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(label)) return null
    if (typeof fingerprint !== 'string' || !/^[A-Fa-f0-9]{64}$/.test(fingerprint)) return null
    if (typeof snapshotId !== 'string' || !/^[A-Fa-f0-9]{32}$/.test(snapshotId)) return null
    return {
      label,
      fingerprint: fingerprint.toLowerCase(),
      snapshot_id: snapshotId.toLowerCase(),
    }
  } catch {
    return null
  }
}

/** Bind the exact result lineage to every filter/deck mutation request. */
export function buildSearchDeckUpdate<T>(
  results: T[],
  lineage: SearchResultLineage | null,
): SearchDeckUpdate<T> | null {
  if (!lineage) return null
  return {
    results,
    lineage: { ...lineage },
  }
}

/** Resolve a validated backend active/full pair into recoverable UI state. */
export function resolveSearchCacheRestore<T>(
  active: unknown,
  full: unknown,
): SearchCacheRestore<T> | null {
  if (!Array.isArray(active) || !Array.isArray(full)) return null
  if (active.length === 0 && full.length === 0) return null
  const base = full.length > 0 ? full : active
  return {
    active: [...active] as T[],
    base: [...base] as T[],
    isFiltered: active.length !== base.length,
  }
}
