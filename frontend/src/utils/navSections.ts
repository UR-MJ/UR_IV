/**
 * 세로 레일 '서랍'의 하위 항목 — 활성 탭이 펼치는 섹션 목록의 단일 출처.
 *
 * 왜 선언으로 두나: 레일이 DOM 을 훑어 섹션을 추측하면, 패널을 손볼 때마다
 * 목록이 **조용히** 달라진다. 이 저장소의 단골 실패 방식이 바로 그거다 —
 * 예외는 안 나고 화면만 틀리게 산다. 여기 적힌 `id` 가 실제 마크업에 있는지는
 * `tests/test_nav_rail_contract.py` 가 정적으로 잡는다.
 *
 * 억지로 채우지 않는다. 하위 항목이 마땅치 않은 탭은 목록에서 빠지고,
 * 그런 탭은 레일에서 그냥 한 줄로 남는다.
 */

/**
 * 섹션이 어느 패널에 사는지.
 * - `left`   : 왼쪽 패널(`.panel-scroll`) 안 — 항상 떠 있으므로 바로 스크롤하면 된다.
 * - `extend` : '고급 설정' 오버레이(`.extend-scroll`) 안 — 닫혀 있으면 DOM 에 아예
 *              없다(`v-if`). 먼저 열고 한 틱 기다려야 스크롤이 닿는다.
 */
export type SectionPanel = 'left' | 'extend'

/** 오른쪽 끝 숫자를 무엇으로 채울지. 없으면 숫자를 그리지 않는다. */
export type SectionBadge = 'tokens' | 'steps-cfg'

export interface NavSection {
  /** 스크롤 대상 요소의 DOM id. 마크업의 id 와 **글자 그대로** 같아야 한다. */
  id: string
  label: string
  panel: SectionPanel
  badge?: SectionBadge
}

export interface NavRouteSections {
  /** `router.js` 의 route name */
  route: string
  sections: NavSection[]
}

/**
 * T2I · I2I · Inpaint 는 같은 왼쪽 패널(`PromptPanel`)과 같은 '고급 설정'
 * 오버레이를 쓴다(`showLeftPanel` 이 이 세 탭에서만 참이다). 그래서 세 탭의
 * 서랍이 같다 — 베껴 넣은 게 아니라 실제로 같은 화면이다.
 */
const PROMPT_TAB_SECTIONS: NavSection[] = [
  { id: 'sec-prompt', label: '프롬프트', panel: 'left', badge: 'tokens' },
  { id: 'sec-params', label: '파라미터', panel: 'extend', badge: 'steps-cfg' },
  { id: 'sec-character', label: '캐릭터', panel: 'left' },
  { id: 'sec-lora', label: 'LoRA', panel: 'extend' },
]

export const NAV_SECTIONS: NavRouteSections[] = [
  { route: 't2i', sections: PROMPT_TAB_SECTIONS },
  { route: 'i2i', sections: PROMPT_TAB_SECTIONS },
  { route: 'inpaint', sections: PROMPT_TAB_SECTIONS },
]

/** 해당 탭의 하위 항목. 없으면 빈 배열 — 서랍이 안 열린다. */
export function sectionsFor(route: string): NavSection[] {
  return NAV_SECTIONS.find((entry) => entry.route === route)?.sections ?? []
}
