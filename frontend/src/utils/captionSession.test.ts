import { describe, expect, it } from 'vitest'

import {
  captionSidecarPath,
  hasUnresolvedCaptionItems,
  matchesCaptionIdentity,
} from './captionSession'

describe('caption session identity', () => {
  it('requires both the exact client token and job id', () => {
    expect(matchesCaptionIdentity(
      { clientToken: 'client-a', jobId: 'job-a' },
      'client-a',
      'job-a',
    )).toBe(true)
    expect(matchesCaptionIdentity(
      { clientToken: 'client-b', jobId: 'job-a' },
      'client-a',
      'job-a',
    )).toBe(false)
    expect(matchesCaptionIdentity(
      { clientToken: 'client-a', jobId: 'job-b' },
      'client-a',
      'job-a',
    )).toBe(false)
    expect(matchesCaptionIdentity({}, 'client-a', 'job-a')).toBe(false)
  })

  it('detects progress missing from an active job before accepting done', () => {
    const activePaths = new Set(['C:/images/a.png', 'C:/images/b.png'])
    expect(hasUnresolvedCaptionItems([
      { path: 'C:/images/a.png', status: 'done' },
      { path: 'C:/images/b.png', status: 'pending' },
      { path: 'C:/images/old.png', status: '' },
    ], activePaths)).toBe(true)

    expect(hasUnresolvedCaptionItems([
      { path: 'C:/images/a.png', status: 'skip' },
      { path: 'C:/images/b.png', status: 'error' },
    ], activePaths)).toBe(false)
  })
})

describe('caption sidecar display path', () => {
  it('uses the image directory when no output directory is selected', () => {
    expect(captionSidecarPath('C:\\images\\sample.png')).toBe('C:/images/sample.txt')
  })

  it('uses the selected output directory and strips its trailing slash', () => {
    expect(captionSidecarPath('C:/images/sample.webp', 'D:\\captions\\')).toBe('D:/captions/sample.txt')
  })
})
