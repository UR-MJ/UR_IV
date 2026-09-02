/**
 * Creator Studio 의 모드(영상 · 만화 · Krea2) — 레일과 화면이 함께 보는 단일 출처.
 *
 * 왜 뷰 안의 ref 가 아니라 여기냐: 모드 전환이 **왼쪽 레일**로 올라갔다.
 * 레일(`NavRail.vue`)과 화면(`CreatorStudioView.vue`)은 형제라서 props 로 못 잇는다.
 * 모듈 최상위 `ref` 는 import 하는 쪽마다 같은 인스턴스를 보므로, 둘 다
 * `useCreatorMode()` 를 부르면 같은 값을 읽고 같은 값을 쓴다.
 *
 * 왜 모드가 레일로 갔나: 예전엔 레일 → 화면 안의 VIDEO/COMIC/KREA2 알약 →
 * T2V/I2V/V2V 로 내비게이션이 **3층**이었다. 모드를 레일의 하위 항목으로 올리면
 * 2층이 되고, 화면 자체 헤더(`AI STUDIO PRO / CREATOR STUDIO`)도 같이 사라진다.
 * 그 헤더는 레일 브랜드와 글자까지 같았다.
 */
import { ref } from 'vue'

export type CreatorMode = 'video' | 'comic' | 'krea'

/** 레일에 그릴 목록의 단일 출처. `navSections.ts` 가 이걸 그대로 쓴다. */
export const CREATOR_MODES: { id: CreatorMode; label: string; icon: string }[] = [
  { id: 'video', label: '영상', icon: 'video' },
  { id: 'comic', label: '만화', icon: 'book' },
  { id: 'krea', label: 'Krea2', icon: 'wand' },
]

const STORAGE_KEY = 'creatorStudioMode.v1'
const VALID = new Set<string>(CREATOR_MODES.map((m) => m.id))

function read(): CreatorMode {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved && VALID.has(saved)) return saved as CreatorMode
  } catch {}
  return 'video'
}

/**
 * 모듈 최상위 — import 하는 모든 곳이 이 하나를 공유한다.
 * (컴포저블 함수 안에 두면 호출할 때마다 새로 생겨 레일과 화면이 갈라진다.)
 */
const mode = ref<CreatorMode>(read())

function setMode(next: CreatorMode) {
  if (!VALID.has(next) || mode.value === next) return
  mode.value = next
  try { window.localStorage.setItem(STORAGE_KEY, next) } catch {}
}

export function useCreatorMode() {
  return { mode, setMode, modes: CREATOR_MODES }
}
