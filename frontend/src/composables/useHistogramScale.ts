/**
 * 히스토그램 세로축(선형/로그) — 사용자 설정 하나를 모두가 나눠 쓴다.
 *
 * 히스토그램 상자와 커브 편집기 배경이 같은 분포를 서로 다른 축으로 그리면,
 * 같은 그림인데 위아래가 다르게 보여 사용자가 둘 중 뭘 믿을지 알 수 없다.
 * 컴포넌트마다 상태를 두는 대신 모듈 스코프 ref 하나로 묶는다.
 *
 * 기본은 선형이다 — 정직하고, 사진 도구의 관행이다. 다만 단색 면이 넓은 그림은
 * 배경 한 덩어리가 천장을 다 먹어 나머지가 바닥에 눕는다. 그때 로그로 바꾼다.
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'editorHistogramLog'

const logScale = ref(window.localStorage.getItem(STORAGE_KEY) === '1')

watch(logScale, (on) => {
  window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
})

export function useHistogramScale() {
  return { logScale }
}
