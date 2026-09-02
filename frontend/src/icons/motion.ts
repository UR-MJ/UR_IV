/**
 * 아이콘 의미 → 모션 문법.
 *
 * 호출부는 여전히 `<Icon name="save" />`만 알면 된다. 어떤 방향으로 움직이는지,
 * 어떤 SVG part가 반응하는지는 이 Module의 seam 뒤에 둬서 300여 사용처에 모션
 * 지식이 퍼지지 않게 한다.
 */

export const ICON_MOTION_GROUPS = {
  dismiss: ['close', 'minus'],
  confirm: ['check'],
  add: ['plus'],
  inspect: ['search', 'target', 'eyedropper'],
  configure: ['settings', 'sliders'],
  store: ['save', 'clipboard', 'file', 'folder', 'folder-open', 'book'],
  'travel-up': ['upload', 'arrow-up', 'chevron-up'],
  'travel-down': ['download', 'arrow-down', 'chevron-down'],
  'travel-left': ['arrow-left', 'chevron-left'],
  'travel-right': ['arrow-right', 'chevron-right'],
  spread: ['arrows-horizontal', 'move'],
  'cycle-cw': ['redo', 'rotate-cw', 'refresh', 'loop', 'history'],
  'cycle-ccw': ['undo', 'rotate-ccw'],
  delete: ['trash', 'eraser'],
  edit: ['pencil', 'brush', 'type'],
  cut: ['scissors', 'crop'],
  magic: ['wand', 'sparkles'],
  color: ['palette', 'bucket', 'gradient'],
  attract: ['magnet'],
  shape: ['marquee', 'lasso', 'grid', 'circle', 'square', 'bar'],
  signal: ['alert', 'info', 'bulb', 'message'],
  notify: ['bell'],
  compute: ['cpu'],
  launch: ['zap', 'rocket'],
  play: ['play'],
  pause: ['pause'],
  stop: ['stop'],
  wait: ['hourglass'],
  media: ['video', 'music'],
  random: ['dice'],
  stack: ['cards', 'layers', 'package'],
  security: ['lock', 'unlock', 'shield', 'keyboard'],
  content: ['image', 'globe', 'tag', 'filter'],
  favorite: ['star'],
} as const satisfies Record<string, readonly string[]>

export type IconMotionKind = keyof typeof ICON_MOTION_GROUPS | 'quiet'

function buildMotionRegistry(): Readonly<Record<string, IconMotionKind>> {
  const registry: Record<string, IconMotionKind> = {}
  for (const [kind, names] of Object.entries(ICON_MOTION_GROUPS) as Array<
    [keyof typeof ICON_MOTION_GROUPS, readonly string[]]
  >) {
    for (const name of names) {
      if (registry[name]) throw new Error(`duplicate icon motion mapping: ${name}`)
      registry[name] = kind
    }
  }
  return Object.freeze(registry)
}

export const ICON_MOTION_BY_NAME = buildMotionRegistry()

/** 알 수 없는 미래 아이콘은 의미를 추측하지 않고 가장 조용한 fallback으로 닫는다. */
export function motionForIcon(name: string): IconMotionKind {
  return ICON_MOTION_BY_NAME[name] ?? 'quiet'
}

/**
 * CSS가 개별 path를 움직이는 아이콘의 최소 path 계약.
 * 레지스트리 path를 줄이거나 순서를 바꿀 때 테스트가 조용한 모션 파손을 막는다.
 */
export const ICON_PART_MINIMUMS: Readonly<Record<string, number>> = Object.freeze({
  search: 2,
  settings: 2,
  save: 3,
  'folder-open': 2,
  trash: 2,
  download: 3,
  upload: 3,
  scissors: 2,
  wand: 2,
  sparkles: 2,
  bell: 2,
  cards: 2,
  layers: 3,
  lock: 2,
  unlock: 2,
  pause: 2,
})
