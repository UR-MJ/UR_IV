import { describe, expect, it } from 'vitest'
import { CHAT_SYSTEM_PRESETS, selectSystemPreset, thinkingValue } from './chatSettings'

describe('chat capability settings', () => {
  it('keeps counts in the Korean explanation below the copyable prompt', () => {
    const prompt = CHAT_SYSTEM_PRESETS[1].prompt
    expect(prompt).toContain('태그 → 자연어 → 설명')
    expect(prompt).toContain('인물 수는 이 한국어 설명에만')
    expect(prompt).toContain('최소 2개의 완결된 문장')
    expect(prompt).toContain('요청하지 않은 네거티브')
  })
  it('never sends a false off switch to GPT-OSS and leaves unknown models at default', () => {
    expect(thinkingValue({ thinkingMode: 'levels' }, false, 'low')).toBe('low')
    expect(thinkingValue({ thinkingMode: 'boolean' }, false, 'high')).toBe(false)
    expect(thinkingValue({ thinkingMode: 'none' }, true, 'high')).toBeUndefined()
    expect(thinkingValue(null, true, 'high')).toBeUndefined()
  })
  it('preserves personal instructions while an improved preset is selected', () => {
    const result = selectSystemPreset('tag-caption', '나의 개인 지침', '')
    expect(result.personal).toBe('나의 개인 지침')
    expect(result.prompt).toBe(CHAT_SYSTEM_PRESETS[1].prompt)
    expect(selectSystemPreset('personal', result.prompt, result.personal).prompt).toBe('나의 개인 지침')
    expect(selectSystemPreset('', '작성 중', '').prompt).toBe('작성 중')
    expect(selectSystemPreset('personal', 'preset', '').prompt).toBe('')
  })
})
