import { describe, expect, it } from 'vitest'
import { EDITOR_TOOLS, toolById, toolByKey, toolsOfKind } from './editorTools'

describe('도구 레지스트리', () => {
  it('id 가 겹치지 않는다', () => {
    const ids = EDITOR_TOOLS.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('단축키가 겹치지 않는다', () => {
    const keys = EDITOR_TOOLS.map((t) => t.shortcut)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('단축키는 대문자 한 글자다', () => {
    for (const t of EDITOR_TOOLS) expect(t.shortcut).toMatch(/^[A-Z]$/)
  })

  it('묶음별로 나뉜다', () => {
    expect(toolsOfKind('mask').map((t) => t.id))
      .toEqual(['box', 'lasso', 'brush', 'eraser', 'stamp'])
    expect(toolsOfKind('draw').length).toBe(10)
  })

  it('자르기·이동·원근은 도구가 아니다 — 선택 영역이 있어야 도는 작업이다', () => {
    for (const id of ['crop', 'move', 'perspective']) {
      expect(toolById(id)).toBeUndefined()
    }
  })
})

describe('toolById', () => {
  it('찾고, 없으면 undefined', () => {
    expect(toolById('pen')?.label).toBe('펜')
    expect(toolById('없는도구')).toBeUndefined()
    expect(toolById(undefined)).toBeUndefined()
  })
})

describe('toolByKey — 조합키를 가로채면 안 된다', () => {
  it('맨 글자는 도구로 받는다 (대소문자 무관)', () => {
    expect(toolByKey('p')?.id).toBe('pen')
    expect(toolByKey('P')?.id).toBe('pen')
    expect(toolByKey('b')?.id).toBe('brush')
  })

  it('Ctrl/Alt/Meta 가 눌렸으면 무시 — Ctrl+S 를 도구로 먹으면 저장이 죽는다', () => {
    expect(toolByKey('s', { ctrl: true })).toBeUndefined()
    expect(toolByKey('s', { alt: true })).toBeUndefined()
    expect(toolByKey('s', { meta: true })).toBeUndefined()
    expect(toolByKey('s')?.id).toBe('stamp')
  })

  it('글자가 아닌 키는 무시', () => {
    expect(toolByKey('Enter')).toBeUndefined()
    expect(toolByKey('Escape')).toBeUndefined()
    expect(toolByKey('')).toBeUndefined()
  })

  it('배정되지 않은 글자는 무시', () => {
    expect(toolByKey('z')).toBeUndefined()
  })
})
