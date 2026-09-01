import { describe, expect, it } from 'vitest'
import {
  BINS,
  barRatio,
  clippingRatio,
  computeHistograms,
  emptyHistograms,
  normalizationCeiling,
  sampleSize,
} from './histogram'

/** RGBA 픽셀 배열을 만든다. `[r,g,b,a]` 를 `count` 번 반복. */
function pixels(...runs: [number, number, number, number, number][]): Uint8ClampedArray {
  const total = runs.reduce((n, r) => n + r[4], 0)
  const data = new Uint8ClampedArray(total * 4)
  let i = 0
  for (const [r, g, b, a, count] of runs) {
    for (let n = 0; n < count; n++) {
      data[i++] = r; data[i++] = g; data[i++] = b; data[i++] = a
    }
  }
  return data
}

describe('computeHistograms', () => {
  it('채널별로 센다', () => {
    const h = computeHistograms(pixels([10, 20, 30, 255, 3], [10, 40, 30, 255, 2]))
    expect(h.count).toBe(5)
    expect(h.r[10]).toBe(5)
    expect(h.g[20]).toBe(3)
    expect(h.g[40]).toBe(2)
    expect(h.b[30]).toBe(5)
  })

  it('완전 투명 픽셀은 빼고 센다', () => {
    // 투명 영역의 RGB 는 보통 0 이라, 세면 화면에 보이지도 않는 픽셀이
    // 좌단에 가짜 봉우리를 세운다.
    const h = computeHistograms(pixels([0, 0, 0, 0, 100], [200, 200, 200, 255, 4]))
    expect(h.count).toBe(4)
    expect(h.r[0]).toBe(0)
    expect(h.r[200]).toBe(4)
  })

  it('휘도는 Rec.601 근사 (계수 합이 256이라 어긋나지 않는다)', () => {
    expect(computeHistograms(pixels([255, 255, 255, 255, 1])).lum[255]).toBe(1)
    expect(computeHistograms(pixels([0, 0, 0, 255, 1])).lum[0]).toBe(1)
    // 순초록은 사람 눈에 가장 밝다 — 순빨강보다 높은 칸에 들어가야 한다
    const green = computeHistograms(pixels([0, 255, 0, 255, 1])).lum.findIndex((v) => v > 0)
    const red = computeHistograms(pixels([255, 0, 0, 255, 1])).lum.findIndex((v) => v > 0)
    expect(green).toBeGreaterThan(red)
  })

  it('빈 히스토그램은 256칸 0', () => {
    const h = emptyHistograms()
    expect(h.r.length).toBe(BINS)
    expect(h.count).toBe(0)
  })
})

describe('normalizationCeiling — 채널이 하나의 천장을 나눠 쓴다', () => {
  it('표시할 채널들의 최댓값', () => {
    const h = emptyHistograms()
    h.r[10] = 50
    h.g[10] = 120
    h.b[10] = 30
    expect(normalizationCeiling(h, ['r', 'b'])).toBe(50)
    expect(normalizationCeiling(h, ['r', 'g', 'b'])).toBe(120)
  })

  it('비어 있어도 0 으로 나누지 않게 최소 1', () => {
    expect(normalizationCeiling(emptyHistograms(), ['r'])).toBe(1)
  })
})

describe('barRatio — 세로축', () => {
  it('선형은 그대로 비율', () => {
    expect(barRatio(50, 100, false)).toBeCloseTo(0.5)
    expect(barRatio(100, 100, false)).toBe(1)
    expect(barRatio(0, 100, false)).toBe(0)
  })

  it('로그도 0 은 0, 천장은 1 (눈금이 어긋나지 않는다)', () => {
    expect(barRatio(0, 100, true)).toBe(0)
    expect(barRatio(100, 100, true)).toBeCloseTo(1)
  })

  it('로그는 작은 값을 끌어올린다 — 단색 배경에 눌린 꼬리를 보이게 하는 목적', () => {
    expect(barRatio(1, 10000, true)).toBeGreaterThan(barRatio(1, 10000, false))
  })

  it('천장을 넘겨도 1 을 넘지 않는다', () => {
    expect(barRatio(500, 100, false)).toBe(1)
  })

  it('천장이 0 이면 0', () => {
    expect(barRatio(5, 0, false)).toBe(0)
  })
})

describe('clippingRatio', () => {
  it('채널 하나만 터져도 잡는다 (그 색은 복구가 안 된다)', () => {
    const h = emptyHistograms()
    h.count = 100
    h.r[0] = 20
    h.g[0] = 5
    h.b[BINS - 1] = 9
    const clip = clippingRatio(h)
    expect(clip.shadow).toBeCloseTo(0.2)
    expect(clip.highlight).toBeCloseTo(0.09)
  })

  it('픽셀이 없으면 0', () => {
    expect(clippingRatio(emptyHistograms())).toEqual({ shadow: 0, highlight: 0 })
  })
})

describe('sampleSize', () => {
  it('긴 변을 상한에 맞춘다', () => {
    expect(sampleSize(2048, 1024, 512)).toEqual({ w: 512, h: 256 })
    expect(sampleSize(1024, 2048, 512)).toEqual({ w: 256, h: 512 })
  })

  it('상한보다 작으면 키우지 않는다', () => {
    expect(sampleSize(300, 200, 512)).toEqual({ w: 300, h: 200 })
  })

  it('아주 납작해도 0 이 되지 않는다', () => {
    expect(sampleSize(4000, 3, 512).h).toBeGreaterThanOrEqual(1)
  })

  it('크기가 없으면 0', () => {
    expect(sampleSize(0, 0)).toEqual({ w: 0, h: 0 })
  })
})
