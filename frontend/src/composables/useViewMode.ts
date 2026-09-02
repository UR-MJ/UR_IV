/**
 * 화면 안의 '모드' — 레일과 화면이 함께 보는 단일 출처.
 *
 * Creator 의 영상·만화·Krea2, Batch 의 일괄·업스케일·ADetailer·SAM3·캡션,
 * PNG Info 의 정보·비교처럼 **한 탭 안에서 화면이 통째로 바뀌는 선택**을 여기 둔다.
 *
 * 왜 뷰 안의 ref 가 아니라 여기냐: 모드 전환이 **왼쪽 레일의 서랍**으로 올라갔다.
 * 레일(`NavRail.vue`)과 화면은 형제라서 props 로 못 잇는다. 모듈 최상위에 scope 별
 * `ref` 를 하나씩 두면 import 하는 쪽마다 같은 인스턴스를 보므로, 레일이 바꾸면
 * 화면이 따라오고 화면이 바꾸면 레일 표시가 따라온다.
 *
 * 왜 모드가 레일로 갔나: 화면 위에 자기만의 탭 줄(알약·서브탭)이 또 있으면
 * 내비게이션이 레일 → 탭 줄 → (그 안의 선택) 으로 **3층**이 된다. 레일 서랍은
 * 이미 T2I 의 '프롬프트·파라미터' 같은 찾아가기 항목을 담고 있어, 모드도 같은
 * 자리에 두면 사용자에게는 '탭 아래 한 단계' 하나로 읽힌다.
 *
 * 목록(`VIEW_MODES`)이 곧 레일에 그려지는 항목이다 — `navSections.ts` 가 이걸
 * 그대로 쓴다. 여기서 빼면 레일에서도 빠진다.
 */
import { ref, type Ref } from 'vue'

export interface ViewModeItem {
  readonly id: string
  readonly label: string
  /** `icons/index.ts` 에 있는 이름. 접힌 레일(52px)에서는 이것만 보인다. */
  readonly icon: string
  /** 레일 항목 오른쪽 끝 숫자 — '지금 값'을 보여준다. 없으면 숫자를 그리지 않는다. */
  readonly badge?: 'tokens' | 'steps-cfg'
}

export const VIEW_MODES = {
  /**
   * T2I · I2I · Inpaint 의 왼쪽 열. 프롬프트(최종 프롬프트 … 접미)와 파라미터가
   * **같은 자리를 번갈아** 쓴다 — 예전엔 파라미터가 오른쪽으로 열리는 오버레이였다.
   */
  panel: [
    { id: 'prompt', label: '프롬프트', icon: 'type', badge: 'tokens' },
    { id: 'params', label: '파라미터', icon: 'sliders', badge: 'steps-cfg' },
  ],
  i2i: [
    { id: 'i2i', label: 'img2img', icon: 'image' },
    { id: 'refine', label: 'SAM3 정밀화', icon: 'lasso' },
  ],
  creator: [
    { id: 'video', label: '영상', icon: 'video' },
    { id: 'comic', label: '만화', icon: 'book' },
    { id: 'krea', label: 'Krea2', icon: 'wand' },
  ],
  batch: [
    { id: 'batch', label: '일괄', icon: 'layers' },
    { id: 'upscale', label: '업스케일', icon: 'arrow-up' },
    { id: 'adetailer', label: 'ADetailer', icon: 'target' },
    { id: 'sam3', label: 'SAM3', icon: 'lasso' },
    { id: 'caption', label: '캡션', icon: 'type' },
  ],
  png: [
    { id: 'info', label: 'PNG Info', icon: 'file' },
    { id: 'compare', label: '비교', icon: 'search' },
  ],
} as const satisfies Record<string, readonly ViewModeItem[]>

export type ViewScope = keyof typeof VIEW_MODES
export type ViewModeOf<S extends ViewScope> = (typeof VIEW_MODES)[S][number]['id']

/** 예전 Creator 전용 키. 그때 저장된 값을 버리지 않으려고 한 번 읽어 준다. */
const LEGACY_KEYS: Partial<Record<ViewScope, string>> = { creator: 'creatorStudioMode.v1', i2i: 'i2i.subTab' }
const storageKey = (scope: ViewScope) => `viewMode.${scope}.v1`

function isValid(scope: ViewScope, value: string | null): value is ViewModeOf<typeof scope> {
  return !!value && (VIEW_MODES[scope] as readonly ViewModeItem[]).some((m) => m.id === value)
}

function read(scope: ViewScope): string {
  try {
    const saved = window.localStorage.getItem(storageKey(scope))
    if (isValid(scope, saved)) return saved
    const legacy = LEGACY_KEYS[scope]
    if (legacy) {
      const old = window.localStorage.getItem(legacy)
      if (isValid(scope, old)) return old
    }
  } catch {}
  return VIEW_MODES[scope][0].id
}

/**
 * scope 마다 ref 하나 — 모듈 최상위라 import 하는 모든 곳이 공유한다.
 * (컴포저블 함수 안에 두면 호출할 때마다 새로 생겨 레일과 화면이 갈라진다.)
 */
const refs: Partial<Record<ViewScope, Ref<string>>> = {}

/** 그 scope 의 현재 모드. 같은 scope 는 언제나 같은 ref 다. */
export function viewMode<S extends ViewScope>(scope: S): Ref<ViewModeOf<S>> {
  let r = refs[scope]
  if (!r) {
    r = ref(read(scope))
    refs[scope] = r
  }
  return r as Ref<ViewModeOf<S>>
}

/** 모드를 바꾸고 저장한다. 목록에 없는 값은 조용히 무시한다 — 빈 화면보다 낫다. */
export function setViewMode(scope: ViewScope, next: string): void {
  if (!isValid(scope, next)) return
  const r = viewMode(scope)
  if (r.value === next) return
  ;(r as Ref<string>).value = next
  try { window.localStorage.setItem(storageKey(scope), next) } catch {}
}

export function useViewMode<S extends ViewScope>(scope: S) {
  return {
    mode: viewMode(scope),
    setMode: (next: ViewModeOf<S>) => setViewMode(scope, next),
    modes: VIEW_MODES[scope],
  }
}
