import { describe, expect, it } from 'vitest'
import { ICON_NAMES, ICONS } from './index'
import {
  ICON_MOTION_BY_NAME,
  ICON_PART_MINIMUMS,
  motionForIcon,
} from './motion'

describe('semantic icon motion registry', () => {
  it('classifies every bundled icon exactly once', () => {
    expect(Object.keys(ICON_MOTION_BY_NAME).sort()).toEqual([...ICON_NAMES].sort())
  })

  it('keeps representative gestures tied to their meaning', () => {
    expect(motionForIcon('search')).toBe('inspect')
    expect(motionForIcon('refresh')).toBe('cycle-cw')
    expect(motionForIcon('upload')).toBe('travel-up')
    expect(motionForIcon('download')).toBe('travel-down')
    expect(motionForIcon('trash')).toBe('delete')
    expect(motionForIcon('bell')).toBe('notify')
    expect(motionForIcon('star')).toBe('favorite')
  })

  it('fails unknown names closed to a quiet non-semantic gesture', () => {
    expect(motionForIcon('future-icon')).toBe('quiet')
  })

  it('only targets internal parts that exist in the SVG registry', () => {
    for (const [name, minimum] of Object.entries(ICON_PART_MINIMUMS)) {
      expect(ICONS[name]?.length, name).toBeGreaterThanOrEqual(minimum)
    }
  })
})
