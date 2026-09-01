/**
 * 톤 커브 — 제어점과 LUT. DOM 의존 없는 순수 로직.
 *
 * 곡선 정의는 **정렬된 제어점 사이의 선형보간** 하나뿐이고, 픽셀에 실제로 적용하는
 * `core/curves.py` 와 정의가 같아야 한다. 여기서 만드는 LUT 는 화면에 곡선을 그리고
 * 프리뷰를 보낼지 판단하는 데만 쓴다 — 실제 적용은 백엔드가 한다.
 *
 * 제어점은 0~1 정규화 좌표다: x 는 입력 레벨, y 는 출력 레벨.
 */

export const CURVE_CHANNELS = ['rgb', 'r', 'g', 'b'] as const
export type CurveChannel = (typeof CURVE_CHANNELS)[number]
export type CurvePoint = [number, number]
export type Curves = Record<CurveChannel, CurvePoint[]>

export const LUT_SIZE = 256

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

export function identityPoints(): CurvePoint[] {
  return [
    [0, 0],
    [1, 1],
  ]
}

export function identityCurves(): Curves {
  return {
    rgb: identityPoints(),
    r: identityPoints(),
    g: identityPoints(),
    b: identityPoints(),
  }
}

/** 0~1 로 자르고 x 순으로 정렬한다. 쓸 수 없으면 항등 커브로 돌린다. */
export function normalizePoints(points: CurvePoint[] | undefined): CurvePoint[] {
  if (!points || points.length < 2) return identityPoints()
  const cleaned = points
    .filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
    .map((p): CurvePoint => [clamp01(p[0]), clamp01(p[1])])
  if (cleaned.length < 2) return identityPoints()
  return cleaned.sort((a, b) => a[0] - b[0])
}

/** 제어점 → 256칸 LUT (0~255). `core/curves.build_lut` 와 같은 값을 내야 한다. */
export function buildLut(points: CurvePoint[] | undefined): Uint8Array {
  const pts = normalizePoints(points)
  const lut = new Uint8Array(LUT_SIZE)
  let segment = 0
  for (let i = 0; i < LUT_SIZE; i++) {
    const x = i / (LUT_SIZE - 1)
    while (segment < pts.length - 2 && x > pts[segment + 1][0]) segment++
    const [x0, y0] = pts[segment]
    const [x1, y1] = pts[segment + 1]
    let y: number
    if (x <= x0) y = y0
    else if (x >= x1) y = y1
    else {
      const span = x1 - x0
      // 같은 x 에 점이 겹치면 나누기가 터진다 — 그 구간은 계단으로 본다
      y = span > 0 ? y0 + ((x - x0) / span) * (y1 - y0) : y1
    }
    // 반올림이어야 한다. 잘라내면 항등 커브조차 대각선이 되지 않는다.
    lut[i] = Math.max(0, Math.min(255, Math.round(y * 255)))
  }
  return lut
}

/** 아무것도 바꾸지 않는 커브인지. 프리뷰를 왕복할지 판단하는 데 쓴다. */
export function isIdentity(curves: Partial<Curves> | null | undefined): boolean {
  if (!curves) return true
  for (const channel of CURVE_CHANNELS) {
    const lut = buildLut(curves[channel])
    for (let i = 0; i < LUT_SIZE; i++) {
      if (lut[i] !== i) return false
    }
  }
  return true
}

/**
 * (x, y) 에서 가장 가까운 제어점의 인덱스. 화면상 `tolerancePx` 밖이면 -1.
 *
 * 판정은 화면 거리로 한다 — 그래프가 정사각형이 아니면 정규화 거리로는
 * 가로로 먼 점이 세로로 가까운 점보다 가깝게 잡힌다.
 */
export function nearestPoint(
  points: CurvePoint[],
  x: number,
  y: number,
  tolerancePx: number,
  scaleX: number,
  scaleY: number,
): number {
  let best = -1
  let bestDistance = tolerancePx
  points.forEach((point, index) => {
    const distance = Math.hypot((point[0] - x) * scaleX, (point[1] - y) * scaleY)
    if (distance <= bestDistance) {
      bestDistance = distance
      best = index
    }
  })
  return best
}

/** 제어점 추가. x 순 정렬을 유지한 새 배열과 새 점의 인덱스를 돌려준다. */
export function addPoint(points: CurvePoint[], x: number, y: number): {
  points: CurvePoint[]
  index: number
} {
  const point: CurvePoint = [clamp01(x), clamp01(y)]
  const next = [...points, point].sort((a, b) => a[0] - b[0])
  // 값이 같은 점이 이미 있어도 방금 넣은 것을 집어야 한다 — 참조로 찾는다
  return { points: next, index: next.indexOf(point) }
}

/**
 * 제어점 이동. 양 끝점은 x 가 고정이다 — 끝을 안쪽으로 끌면 그 바깥 구간이
 * 정의되지 않아 곡선이 끊긴다.
 *
 * 옮긴 점이 이웃을 넘어가면 정렬 순서가 바뀐다. 그때 인덱스를 그대로 두면
 * 다음 이동부터 **옆 점이 끌려온다** — 그래서 새 인덱스를 같이 돌려준다.
 */
export function movePoint(points: CurvePoint[], index: number, x: number, y: number): {
  points: CurvePoint[]
  index: number
} {
  if (index < 0 || index >= points.length) return { points, index }
  const next = points.map((p): CurvePoint => [p[0], p[1]])
  const isFirst = index === 0
  const isLast = index === points.length - 1
  const moved: CurvePoint = [isFirst ? 0 : isLast ? 1 : clamp01(x), clamp01(y)]
  next[index] = moved
  next.sort((a, b) => a[0] - b[0])
  return { points: next, index: next.indexOf(moved) }
}

/** 제어점 삭제. 양 끝점은 지우지 않는다 — 지우면 곡선의 정의역이 사라진다. */
export function removePoint(points: CurvePoint[], index: number): CurvePoint[] {
  if (index <= 0 || index >= points.length - 1) return points
  return points.filter((_, i) => i !== index)
}
