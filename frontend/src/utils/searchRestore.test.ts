import { describe, expect, it } from 'vitest'

import {
  buildSearchDeckUpdate,
  parseSearchResultLineage,
  resolveSearchCacheRestore,
} from './searchRestore'


describe('resolveSearchCacheRestore', () => {
  it('keeps the full base recoverable after a zero-result active filter', () => {
    const full = [{ general: 'recoverable' }]
    const restored = resolveSearchCacheRestore([], full)

    expect(restored).not.toBeNull()
    expect(restored?.active).toEqual([])
    expect(restored?.base).toEqual(full)
    expect(restored?.isFiltered).toBe(true)

    const afterClearFilters = [...(restored?.base ?? [])]
    expect(afterClearFilters).toEqual(full)
  })

  it('rejects an absent or empty cache pair', () => {
    expect(resolveSearchCacheRestore(null, [])).toBeNull()
    expect(resolveSearchCacheRestore([], [])).toBeNull()
  })

  it('binds a filter payload to the result lineage that produced its rows', () => {
    const lineage = parseSearchResultLineage(JSON.stringify({
      label: '2026_07',
      fingerprint: 'a'.repeat(64),
      snapshot_id: 'b'.repeat(32),
    }))

    expect(buildSearchDeckUpdate([{ general: 'from_a' }], lineage)).toEqual({
      results: [{ general: 'from_a' }],
      lineage: {
        label: '2026_07',
        fingerprint: 'a'.repeat(64),
        snapshot_id: 'b'.repeat(32),
      },
    })
  })

  it('does not build an unbound filter payload', () => {
    expect(parseSearchResultLineage('{"label":"../unsafe"}')).toBeNull()
    expect(buildSearchDeckUpdate([], null)).toBeNull()
  })
})
