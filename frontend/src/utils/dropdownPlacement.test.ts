import { describe, expect, it } from 'vitest'
import { dropdownPlacement } from './dropdownPlacement'

describe('viewport-aware dropdown', () => {
  it('opens above a model selector near the bottom', () => {
    const menu = dropdownPlacement({ left: 24, top: 710, bottom: 750, width: 242 }, { width: 800, height: 800 })
    expect(menu.above).toBe(true)
    expect(menu).toMatchObject({ bottom: 94 })
    expect(menu.maxHeight).toBe(240)
  })
  it('keeps ordinary menus below their trigger', () => {
    expect(dropdownPlacement({ left: 20, top: 40, bottom: 70, width: 200 }, { width: 800, height: 800 })).toMatchObject({ above: false, top: 74 })
  })
  it('clamps width and height on a narrow touch viewport', () => {
    const menu = dropdownPlacement({ left: 250, top: 160, bottom: 190, width: 500 }, { width: 320, height: 300 })
    expect(menu.left + menu.width).toBeLessThanOrEqual(312)
    expect(menu.maxHeight).toBe(148)
    expect(menu.maxHeight).toBeGreaterThan(0)
  })
})
