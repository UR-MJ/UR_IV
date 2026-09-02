/**
 * 세로 레일 '서랍'의 하위 항목 — 활성 탭이 펼치는 목록의 단일 출처.
 *
 * 하위 항목은 전부 **모드**다: 누르면 그 탭 안의 화면이 통째로 바뀐다.
 * (T2I 의 프롬프트 ↔ 파라미터, Creator 의 영상 · 만화 · Krea2, Batch 의 서브탭 …)
 * 예전엔 '같은 화면 안의 어느 지점으로 찾아가는' 스크롤 항목도 있었는데,
 * 파라미터가 오버레이에서 왼쪽 열 자체로 들어오면서 찾아갈 곳이 없어졌다.
 *
 * 왜 선언으로 두나: 레일이 DOM 을 훑어 목록을 추측하면, 패널을 손볼 때마다
 * 목록이 **조용히** 달라진다. 이 저장소의 단골 실패 방식이 바로 그거다 —
 * 예외는 안 나고 화면만 틀리게 산다. 목록의 원본은 `composables/useViewMode.ts`
 * 의 `VIEW_MODES` 이고, 여기선 라우트에 붙이기만 한다. 라우트·화면·아이콘이
 * 서로 맞는지는 tests/test_nav_rail_contract.py 가 정적으로 잡는다.
 */
import { VIEW_MODES, type ViewModeItem, type ViewScope } from '../composables/useViewMode'

/** 오른쪽 끝 숫자를 무엇으로 채울지. 없으면 숫자를 그리지 않는다. */
export type SectionBadge = 'tokens' | 'steps-cfg'

export interface NavSection {
  /** 목록 안의 이름표 — `:key` 와 활성 표시에 쓴다. DOM id 가 **아니다**. */
  id: string
  label: string
  /** `icons/index.ts` 에 있는 이름. 접힌 레일(52px)에서는 이것만 보인다. */
  icon: string
  /** 어느 화면의 모드인지 (`useViewMode` 의 scope). */
  scope: ViewScope
  /** 어느 모드로 바꾸는지. */
  mode: string
  badge?: SectionBadge
}

export interface NavRouteSections {
  /** `router.js` 의 route name */
  route: string
  sections: NavSection[]
}

function modeSections(scope: ViewScope): NavSection[] {
  return (VIEW_MODES[scope] as readonly ViewModeItem[]).map((m) => ({
    id: `${scope}-mode-${m.id}`,
    label: m.label,
    icon: m.icon,
    scope,
    mode: m.id,
    badge: m.badge,
  }))
}

/**
 * T2I · I2I · Inpaint 는 같은 왼쪽 열을 쓴다 — 프롬프트 · 파라미터 서랍이 같은 건
 * 베껴 넣은 게 아니라 실제로 같은 화면이다. I2I 는 거기에 제 서브탭이 더 붙는다.
 */
export const NAV_SECTIONS: NavRouteSections[] = [
  { route: 't2i', sections: modeSections('panel') },
  { route: 'i2i', sections: [...modeSections('panel'), ...modeSections('i2i')] },
  { route: 'inpaint', sections: modeSections('panel') },
  { route: 'creator', sections: modeSections('creator') },
  { route: 'batch', sections: modeSections('batch') },
  { route: 'png', sections: modeSections('png') },
]

/** 해당 탭의 하위 항목. 없으면 빈 배열 — 서랍이 안 열린다. */
export function sectionsFor(route: string): NavSection[] {
  return NAV_SECTIONS.find((entry) => entry.route === route)?.sections ?? []
}
