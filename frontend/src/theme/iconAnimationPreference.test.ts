import { describe, expect, it } from 'vitest'
import {
  applyIconAnimationStyle,
  DEFAULT_ICON_ANIMATION_STYLE,
  ICON_ANIMATION_ATTRIBUTE,
  ICON_ANIMATION_OPTIONS,
  normalizeIconAnimationStyle,
} from './iconAnimationPreference'

describe('icon animation preference contract', () => {
  it('offers exactly none, Claude, and GPT with none as the default', () => {
    expect(DEFAULT_ICON_ANIMATION_STYLE).toBe('none')
    expect(ICON_ANIMATION_OPTIONS.map(option => [option.id, option.label])).toEqual([
      ['none', '없음'],
      ['claude', 'Claude'],
      ['gpt', 'GPT'],
    ])
  })

  it('accepts only the three stored values and fails closed to none', () => {
    expect(normalizeIconAnimationStyle('none')).toBe('none')
    expect(normalizeIconAnimationStyle('claude')).toBe('claude')
    expect(normalizeIconAnimationStyle('gpt')).toBe('gpt')
    expect(normalizeIconAnimationStyle('')).toBe('none')
    expect(normalizeIconAnimationStyle('surprise')).toBe('none')
    expect(normalizeIconAnimationStyle(null)).toBe('none')
  })

  it('applies the closed preference contract to the document root seam', () => {
    const attributes = new Map<string, string>()
    const root = {
      setAttribute(name: string, value: string) { attributes.set(name, value) },
    }

    expect(applyIconAnimationStyle('gpt', root)).toBe('gpt')
    expect(attributes.get(ICON_ANIMATION_ATTRIBUTE)).toBe('gpt')

    expect(applyIconAnimationStyle('surprise', root)).toBe('none')
    expect(attributes.get(ICON_ANIMATION_ATTRIBUTE)).toBe('none')
  })
})
