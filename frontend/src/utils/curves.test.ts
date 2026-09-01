import { describe, expect, it } from 'vitest'
import {
  addPoint,
  buildLut,
  identityCurves,
  identityPoints,
  isIdentity,
  LUT_SIZE,
  movePoint,
  nearestPoint,
  normalizePoints,
  removePoint,
  type CurvePoint,
} from './curves'

/**
 * 이 곡선은 두 언어에 같은 정의로 살아 있다 — 여기서 그리고, `core/curves.py` 가
 * 픽셀에 적용한다. 정의가 갈라지면 화면에 그린 곡선과 저장된 결과가 달라진다.
 * 아래 golden 값은 파이썬 쪽 `build_lut` 이 실제로 낸 값이다.
 */
describe('buildLut — 파이썬 구현과 같은 값', () => {
  it('golden: [[0,0],[0.25,0.55],[1,1]]', () => {
    const lut = buildLut([[0, 0], [0.25, 0.55], [1, 1]])
    expect([0, 32, 64, 128, 192, 255].map((i) => lut[i])).toEqual([0, 70, 140, 179, 217, 255])
  })

  it('항등 커브는 대각선이다 (잘라내면 한 칸씩 어긋난다)', () => {
    const lut = buildLut(identityPoints())
    for (let i = 0; i < LUT_SIZE; i++) expect(lut[i]).toBe(i)
  })

  it('끝값이 정확하다', () => {
    const lut = buildLut([[0, 0.25], [1, 0.75]])
    expect(lut[0]).toBe(64)
    expect(lut[255]).toBe(191)
  })

  it('제어점 순서가 뒤섞여도 같은 곡선', () => {
    const forward = buildLut([[0, 0], [0.5, 0.9], [1, 1]])
    const shuffled = buildLut([[1, 1], [0, 0], [0.5, 0.9]])
    expect(Array.from(shuffled)).toEqual(Array.from(forward))
  })

  it('범위를 벗어난 점은 잘린다', () => {
    expect(Array.from(buildLut([[-3, -1], [2, 5]]))).toEqual(
      Array.from(buildLut(identityPoints())),
    )
  })

  it('쓸 수 없는 입력은 항등으로', () => {
    for (const bad of [undefined, [] as CurvePoint[], [[0, 0]] as CurvePoint[]]) {
      expect(buildLut(bad)[128]).toBe(128)
    }
  })

  it('중간을 올리면 단조증가하면서 밝아진다', () => {
    const lut = buildLut([[0, 0], [0.5, 0.7], [1, 1]])
    for (let i = 1; i < LUT_SIZE; i++) expect(lut[i]).toBeGreaterThanOrEqual(lut[i - 1])
    expect(lut[128]).toBeGreaterThan(128)
  })

  it('같은 x 에 점이 겹쳐도 터지지 않는다', () => {
    const lut = buildLut([[0, 0], [0.5, 0.2], [0.5, 0.8], [1, 1]])
    expect(lut.length).toBe(LUT_SIZE)
    expect(Number.isFinite(lut[128])).toBe(true)
  })
})

describe('normalizePoints', () => {
  it('0~1 로 자르고 x 순으로 세운다', () => {
    expect(normalizePoints([[0.9, 2], [0.1, -1]])).toEqual([[0.1, 0], [0.9, 1]])
  })
})

describe('isIdentity — 프리뷰를 왕복할지 정한다', () => {
  it('빈 값과 기본 커브는 항등', () => {
    expect(isIdentity(null)).toBe(true)
    expect(isIdentity({})).toBe(true)
    expect(isIdentity(identityCurves())).toBe(true)
  })

  it('대각선 위에 점을 더 찍은 것도 항등', () => {
    expect(isIdentity({ rgb: [[0, 0], [0.5, 0.5], [1, 1]] })).toBe(true)
  })

  it('점을 옮기면 항등이 아니다', () => {
    expect(isIdentity({ b: [[0, 0], [0.5, 0.6], [1, 1]] })).toBe(false)
  })
})

describe('제어점 편집', () => {
  it('추가하면 x 순을 지키고 새 점의 인덱스를 준다', () => {
    const { points, index } = addPoint(identityPoints(), 0.4, 0.7)
    expect(points.map((p) => p[0])).toEqual([0, 0.4, 1])
    expect(points[index]).toEqual([0.4, 0.7])
  })

  it('값이 같은 점이 이미 있어도 방금 넣은 것을 집는다', () => {
    const base: CurvePoint[] = [[0, 0], [0.4, 0.7], [1, 1]]
    const { points, index } = addPoint(base, 0.4, 0.7)
    expect(points.length).toBe(4)
    expect(index).toBeGreaterThanOrEqual(0)
  })

  it('양 끝점은 x 가 고정이다', () => {
    const first = movePoint(identityPoints(), 0, 0.8, 0.3)
    expect(first.points[first.index]).toEqual([0, 0.3])
    const last = movePoint(identityPoints(), 1, 0.2, 0.4)
    expect(last.points[last.index]).toEqual([1, 0.4])
  })

  it('이웃을 넘어가면 인덱스가 따라간다 (안 그러면 옆 점이 끌려온다)', () => {
    const base: CurvePoint[] = [[0, 0], [0.3, 0.3], [0.6, 0.6], [1, 1]]
    const moved = movePoint(base, 1, 0.8, 0.9)
    expect(moved.points[moved.index]).toEqual([0.8, 0.9])
    expect(moved.points.map((p) => p[0])).toEqual([0, 0.6, 0.8, 1])
  })

  it('양 끝점은 지워지지 않는다', () => {
    const base: CurvePoint[] = [[0, 0], [0.5, 0.5], [1, 1]]
    expect(removePoint(base, 0)).toBe(base)
    expect(removePoint(base, 2)).toBe(base)
    expect(removePoint(base, 1).length).toBe(2)
  })
})

describe('nearestPoint — 화면 거리로 판정한다', () => {
  const pts: CurvePoint[] = [[0, 0], [0.5, 0.5], [1, 1]]

  it('허용 범위 안이면 그 점을 집는다', () => {
    expect(nearestPoint(pts, 0.5, 0.5, 11, 300, 300)).toBe(1)
  })

  it('범위 밖이면 -1', () => {
    expect(nearestPoint(pts, 0.5, 0.2, 11, 300, 300)).toBe(-1)
  })

  it('그래프가 정사각이 아니면 축마다 다르게 잰다', () => {
    // 가로로 아주 납작한 그래프: x 로 0.1 떨어져도 화면상 2px 뿐이다
    expect(nearestPoint(pts, 0.6, 0.5, 11, 20, 400)).toBe(1)
    // 같은 0.1 이 세로에서는 40px — 잡히지 않는다
    expect(nearestPoint(pts, 0.5, 0.6, 11, 20, 400)).toBe(-1)
  })
})
