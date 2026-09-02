import { describe, expect, it } from 'vitest'
import {
  createComicRecoveryMirror,
  prepareComicDocumentForBackend,
  parseComicRecovery,
  recoveryDocument,
  saveConflictDecision,
  shouldAcceptAuthoritativeRevision,
  verifyComicRecoveryMirror,
} from './comicRecovery'

const document = {
  version: 1,
  id: 'comic-1',
  title: '복구 문서',
  scene: '',
  style: 'Anime',
  layout: 'auto',
  width: 1400,
  height: 2100,
  panels: [{ id: 'panel-1', prompt: 'keep', negative: '', motion: '', imagePath: '', videoPath: '', bubbles: [] }],
  revision: 4,
  contentHash: 'a'.repeat(64),
  updatedAt: 100,
}

describe('Comic recovery mirror', () => {
  it('keeps a legacy localStorage-only document readable for one-time migration', () => {
    expect(recoveryDocument(document)).toEqual(document)
  })

  it('stores an exact document JSON with revision and a verified hash', async () => {
    const mirror = await createComicRecoveryMirror(document, {
      baseRevision: 4,
      baseContentHash: 'a'.repeat(64),
      dirty: true,
      updatedAt: 123,
    })

    expect(mirror.schema).toBe(2)
    expect(mirror.baseRevision).toBe(4)
    expect(mirror.recoveryHash).toBe('f97223f4ca172accaf6a3f1b9a7cc3b61a51bc401010b5416c5a618fd1e04dab')
    expect(JSON.parse(mirror.documentJson)).toEqual(document)
    expect(parseComicRecovery(JSON.stringify(mirror))).toEqual(mirror)
    expect(await verifyComicRecoveryMirror(mirror)).toBe(true)
    expect(await verifyComicRecoveryMirror({ ...mirror, documentJson: `${mirror.documentJson} ` })).toBe(false)
  })

  it('rejects malformed envelopes instead of replacing a recoverable document', () => {
    expect(parseComicRecovery('{bad json')).toBeNull()
    expect(recoveryDocument({ schema: 2, documentJson: '{bad json' })).toBeNull()
  })

  it('synchronizes backend aliases and flattened bubbles with visible UI edits', () => {
    const payload = prepareComicDocumentForBackend({
      ...document,
      style: 'Webtoon',
      art_style: 'manga',
      bubbles: [{ id: 'bubble-1', text: 'OLD', panelIndex: 0 }],
      panels: [{
        id: 'panel-1', prompt: 'NEW', image_prompt: 'OLD', imagePrompt: 'OLD',
        negative: 'NEW NEG', negative_prompt: 'OLD NEG',
        motion: 'NEW MOTION', motion_prompt: 'OLD MOTION',
        imagePath: 'new.png', image_path: 'old.png', videoPath: '',
        bubbles: [{ id: 'bubble-1', text: 'NEW BUBBLE', kind: 'speech', x: 8, y: 8, width: 38, height: 18 }],
      }],
    })

    expect(payload.art_style).toBe('webtoon')
    expect(payload.panels[0].image_prompt).toBe('NEW')
    expect(payload.panels[0].negative_prompt).toBe('NEW NEG')
    expect(payload.panels[0].motion_prompt).toBe('NEW MOTION')
    expect(payload.panels[0].image_path).toBe('new.png')
    expect(payload.bubbles).toEqual([
      expect.objectContaining({ id: 'bubble-1', text: 'NEW BUBBLE', panelIndex: 0, panel_index: 0 }),
    ])
  })

  it('preserves edits made after a conflicted save request', () => {
    expect(saveConflictDecision(7, 7)).toBe('restore-authoritative')
    expect(saveConflictDecision(7, 8)).toBe('preserve-newer-local')
  })

  it('never rolls the authoritative document back on reordered events', () => {
    expect(shouldAcceptAuthoritativeRevision(3, 2)).toBe(false)
    expect(shouldAcceptAuthoritativeRevision(3, 3)).toBe(true)
    expect(shouldAcceptAuthoritativeRevision(3, 4)).toBe(true)
  })
})
