export const ICON_ANIMATION_STYLES = ['none', 'claude', 'gpt'] as const

export type IconAnimationStyle = typeof ICON_ANIMATION_STYLES[number]

export const DEFAULT_ICON_ANIMATION_STYLE: IconAnimationStyle = 'none'
export const ICON_ANIMATION_ATTRIBUTE = 'data-icon-animation'

export interface IconAnimationRoot {
  setAttribute(name: string, value: string): void
}

export const ICON_ANIMATION_OPTIONS: ReadonlyArray<{
  id: IconAnimationStyle
  label: string
  description: string
}> = [
  { id: 'none', label: '없음', description: '현재처럼 움직임 없는 아이콘을 유지합니다.' },
  { id: 'claude', label: 'Claude', description: 'Claude 효과 프리셋을 위한 예약 선택입니다.' },
  { id: 'gpt', label: 'GPT', description: '아이콘 의미에 맞춘 정교한 마이크로 모션을 적용합니다.' },
]

export function normalizeIconAnimationStyle(value: unknown): IconAnimationStyle {
  return ICON_ANIMATION_STYLES.some(style => style === value)
    ? value as IconAnimationStyle
    : DEFAULT_ICON_ANIMATION_STYLE
}

/**
 * 닫힌 설정 계약을 문서 루트의 CSS seam에 적용한다.
 *
 * `gpt`만 실제 모션 CSS를 갖는다. `none`과 아직 예약 상태인 `claude`, 그리고
 * 잘못된 값은 움직임을 만들지 않는다. root 주입은 DOM 없이도 계약을 테스트하기
 * 위한 내부 seam이며 일반 호출부는 value 하나만 넘긴다.
 */
export function applyIconAnimationStyle(
  value: unknown,
  root?: IconAnimationRoot,
): IconAnimationStyle {
  const next = normalizeIconAnimationStyle(value)
  const target = root ?? (
    typeof document === 'undefined' ? undefined : document.documentElement
  )
  target?.setAttribute(ICON_ANIMATION_ATTRIBUTE, next)
  return next
}
