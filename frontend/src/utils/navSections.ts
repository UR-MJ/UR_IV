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
import { CREATOR_MODES, type CreatorMode } from '../composables/useCreatorMode'

/**
 * 섹션이 어느 패널에 사는지.
 * - `left`   : 왼쪽 패널(`.panel-scroll`) 안 — 항상 떠 있으므로 바로 스크롤하면 된다.
 * - `extend` : '고급 설정' 오버레이(`.extend-scroll`) 안 — 닫혀 있으면 DOM 에 아예
 *              없다(`v-if`). 먼저 열고 한 틱 기다려야 스크롤이 닿는다.
 */
export type SectionPanel = 'left' | 'extend'

/** 오른쪽 끝 숫자를 무엇으로 채울지. 없으면 숫자를 그리지 않는다. */
export type SectionBadge = 'tokens' | 'steps-cfg'

/**
 * 하위 항목은 두 종류다.
 *
 * - `scroll` : 같은 화면 안의 어느 지점으로 **찾아간다**. 원래 있던 종류.
 * - `mode`   : 화면 자체를 **바꾼다**. Creator 의 영상 · 만화 · Krea2 가 이것이다.
 *
 * 왜 한 목록에 섞나: 사용자에게는 둘 다 '탭 아래 한 단계'로 보인다. 레일이 두
 * 목록을 각각 그리면 같은 자리에 두 벌의 규칙이 생긴다. 대신 두 종류가 하는 일이
 * 정말 다르므로 `kind` 로 **말로** 갈라 둔다 — 이걸 `panel` 같은 기존 필드에
 * 얹으면 나중에 읽는 사람이 못 알아본다.
 */
export interface NavScrollSection {
  kind?: 'scroll'
  /** 스크롤 대상 요소의 DOM id. 마크업의 id 와 **글자 그대로** 같아야 한다. */
  id: string
  label: string
  panel: SectionPanel
  badge?: SectionBadge
}

/**
 * 화면 안의 모드를 바꾸는 항목.
 *
 * `id` 는 스크롤 대상이 아니라 **목록 안의 이름표**일 뿐이다(`:key` 와 활성 표시에
 * 쓰인다). 그래서 `NavScrollSection` 과 달리 DOM 에 같은 id 가 있으면 안 되고,
 * 있을 필요도 없다 — 이 구분은 tests/test_nav_rail_contract.py 가 지킨다.
 */
export interface NavModeSection {
  kind: 'mode'
  id: string
  label: string
  /** `icons/index.ts` 에 있는 이름. 접힌 레일(52px)에서는 이것만 보인다. */
  icon: string
  /** 어느 모드로 바꾸는지. */
  mode: CreatorMode
}

export type NavSection = NavScrollSection | NavModeSection

/** 좁히기용. `section.panel` 은 스크롤 항목에만 있다. */
export function isModeSection(section: NavSection): section is NavModeSection {
  return section.kind === 'mode'
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
const PROMPT_TAB_SECTIONS: NavScrollSection[] = [
  { id: 'sec-prompt', label: '프롬프트', panel: 'left', badge: 'tokens' },
  { id: 'sec-params', label: '파라미터', panel: 'extend', badge: 'steps-cfg' },
  { id: 'sec-character', label: '캐릭터', panel: 'left' },
  { id: 'sec-lora', label: 'LoRA', panel: 'extend' },
]

/**
 * Creator 는 한 탭 안에 성격이 다른 화면 셋이 산다(영상 · 만화 문서 · Krea2).
 * 예전엔 화면 안에 알약 줄이 하나 더 있어서 레일 → 알약 → T2V/I2V/V2V 로
 * 내비게이션이 **3층**이었다. 모드를 레일로 올려 2층으로 만든다.
 *
 * 목록의 원본은 `composables/useCreatorMode.ts` 의 `CREATOR_MODES` 다 — 여기서
 * 다시 적으면 레일과 화면이 갈라진다.
 */
const CREATOR_MODE_SECTIONS: NavModeSection[] = CREATOR_MODES.map((m) => ({
  kind: 'mode',
  id: `creator-mode-${m.id}`,
  label: m.label,
  icon: m.icon,
  mode: m.id,
}))

export const NAV_SECTIONS: NavRouteSections[] = [
  { route: 't2i', sections: PROMPT_TAB_SECTIONS },
  { route: 'i2i', sections: PROMPT_TAB_SECTIONS },
  { route: 'inpaint', sections: PROMPT_TAB_SECTIONS },
  { route: 'creator', sections: CREATOR_MODE_SECTIONS },
]

/** 해당 탭의 하위 항목. 없으면 빈 배열 — 서랍이 안 열린다. */
export function sectionsFor(route: string): NavSection[] {
  return NAV_SECTIONS.find((entry) => entry.route === route)?.sections ?? []
}
