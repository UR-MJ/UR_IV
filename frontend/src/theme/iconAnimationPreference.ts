export const ICON_ANIMATION_STYLES = ['none', 'claude', 'gpt'] as const

export type IconAnimationStyle = typeof ICON_ANIMATION_STYLES[number]

export const DEFAULT_ICON_ANIMATION_STYLE: IconAnimationStyle = 'none'

export const ICON_ANIMATION_OPTIONS: ReadonlyArray<{
  id: IconAnimationStyle
  label: string
  description: string
}> = [
  { id: 'none', label: '없음', description: '현재처럼 움직임 없는 아이콘을 유지합니다.' },
  { id: 'claude', label: 'Claude', description: 'Claude 효과 프리셋을 위한 예약 선택입니다.' },
  { id: 'gpt', label: 'GPT', description: 'GPT 효과 프리셋을 위한 예약 선택입니다.' },
]

export function normalizeIconAnimationStyle(value: unknown): IconAnimationStyle {
  return ICON_ANIMATION_STYLES.some(style => style === value)
    ? value as IconAnimationStyle
    : DEFAULT_ICON_ANIMATION_STYLE
}
