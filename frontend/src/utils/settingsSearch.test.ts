import { describe, it, expect } from 'vitest'
import { searchSettings } from './settingsSearch'

describe('settings field search', () => {
  const entries = [
    { id: 'duplicates', tab: 'prompt', title: '중복 자동 정리', keywords: '로직' },
    { id: 'cache', tab: 'models', title: 'H3 인코딩 캐시', keywords: '영상 encoding cache' },
  ]
  it('finds a nested option without requiring its tab name', () => {
    expect(searchSettings(entries, '중복자동 정리')).toEqual([entries[0]])
  })
  it('normalizes English case, spaces and punctuation', () => {
    expect(searchSettings(entries, 'H3 인코딩_캐시')).toEqual([entries[1]])
    expect(searchSettings(entries, 'ENCODING CACHE')).toEqual([entries[1]])
  })
  it('does not suggest unrelated fields or match an empty query', () => {
    expect(searchSettings(entries, 'unavailable option')).toEqual([])
    expect(searchSettings(entries, ' ')).toEqual([])
  })
})
