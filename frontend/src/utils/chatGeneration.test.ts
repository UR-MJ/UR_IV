import { describe, expect, it } from 'vitest'
import { applyGenerationEvent, artifactMarkdown } from './chatGeneration'

describe('chat media events', () => {
  it('ignores unrelated and stale jobs but persists the owned result', () => {
    const message: any = { requestId: 'owned', pending: true, content: '' }
    expect(applyGenerationEvent(message, { id: 'other', done: true, ok: true })).toBe(false)
    expect(message.pending).toBe(true)
    expect(applyGenerationEvent(message, { id: 'owned', kind: 'video', phase: 'generating', progress: 50 })).toBe(true)
    expect(message.generation.progress).toBe(50)
    applyGenerationEvent(message, { id: 'owned', kind: 'video', phase: 'complete', done: true, ok: true,
      artifacts: [{ kind: 'video', path: 'C:/output/movie.mp4' }] })
    expect(message.pending).toBe(false)
    expect(message.artifacts[0].path).toBe('C:/output/movie.mp4')
    expect(applyGenerationEvent(message, { id: 'owned', phase: 'generating' })).toBe(false)
  })

  it('does not attach partial media after cancellation', () => {
    const message: any = { requestId: 'a', pending: true }
    applyGenerationEvent(message, { id: 'a', kind: 'image', done: true, stopped: true, ok: false,
      artifacts: [{ kind: 'image', path: 'C:/partial.png' }] })
    expect(message.artifacts || []).toEqual([])
    expect(message.content).toContain('중지')
  })

  it('exports a local artifact link instead of silently dropping generated media', () => {
    expect(artifactMarkdown({ kind: 'video', path: 'C:/output/my video.mp4' })).toContain('file:///C:/output/my%20video.mp4')
    expect(artifactMarkdown({ kind: 'image', path: 'C:/output/image#1(2).png' })).toContain('image%231%282%29.png')
  })
})
