import { describe, expect, it } from 'vitest'
import { parseAxisValues, acceptCapabilityEvent } from './xyzPlot'

describe('XYZ axis input', () => {
  it('supports decimal ranges and quoted resource names without unbounded loops', () => {
    expect(parseAxisValues('1-2:0.5', 'number')).toEqual(['1', '1.5', '2'])
    expect(parseAxisValues('"folder/model, v2.safetensors", other', 'choice')).toEqual(['folder/model, v2.safetensors', 'other'])
    expect(() => parseAxisValues('20-40:0', 'integer')).toThrow()
    expect(() => parseAxisValues('1-10000:1', 'integer')).toThrow()
  })
  it('only accepts the current backend query and clears errors without keeping old axes', () => {
    expect(acceptCapabilityEvent('new', { requestId: 'old', ok: true, axes: [{}] })).toBe(false)
    expect(acceptCapabilityEvent('new', { requestId: 'new', ok: false, axes: [] })).toBe(true)
    expect(acceptCapabilityEvent('new', { invalidated: true })).toBe(true)
  })
})
