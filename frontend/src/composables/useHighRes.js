import { ref, computed, watch } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

/**
 * 고해상도(단일 패스) 모드 — 입력 해상도 × 배율로 처음부터 크게 생성 (App.vue 분할 ④).
 * Hires.fix(hires_* 위젯)와는 별개. 단일 소스: config/ui_prefs.json (highResEnabled/highResFactor).
 *
 * @param {object} deps
 * @param {object} deps.storeWidgets  위젯 스토어 reactive (width_input/height_input 읽기)
 * @param {Function} deps.saveUiPrefs (payload) ui_prefs 영속
 */
export function useHighRes({ storeWidgets, saveUiPrefs }) {
  const highResEnabled = ref(localStorage.getItem('highRes.enabled') === 'true')
  const highResFactor = ref(parseFloat(localStorage.getItem('highRes.factor') || '1.5') || 1.5)

  // 미리보기 — 8 배수 정렬된 실제 생성 해상도
  const hrActualW = computed(() => {
    const w = parseInt(storeWidgets.width_input || 0) || 0
    return Math.max(8, Math.floor((w * highResFactor.value) / 8) * 8)
  })
  const hrActualH = computed(() => {
    const h = parseInt(storeWidgets.height_input || 0) || 0
    return Math.max(8, Math.floor((h * highResFactor.value) / 8) * 8)
  })

  // 토글/배율 변경 시 즉시 Python 동기화 + localStorage/ui_prefs 영속
  function _syncHighRes() {
    try {
      localStorage.setItem('highRes.enabled', highResEnabled.value ? 'true' : 'false')
      localStorage.setItem('highRes.factor', String(highResFactor.value))
    } catch {}
    saveUiPrefs({ highResEnabled: highResEnabled.value, highResFactor: highResFactor.value })
    requestAction('set_high_res_factor', {
      enabled: highResEnabled.value,
      factor: highResFactor.value,
    })
  }
  watch(highResEnabled, _syncHighRes)
  watch(highResFactor, _syncHighRes)
  // 앱 시작 직후 한 번 — Python이 옛 상태 갖고 있을 수 있어 동기화
  setTimeout(_syncHighRes, 400)

  // 단일 소스(ui_prefs) 복원 — App.vue uiPrefsLoaded 핸들러에서 호출
  function restoreFromPrefs(prefs) {
    if (!prefs) return
    if (typeof prefs.highResFactor === 'number') highResFactor.value = prefs.highResFactor
    if (typeof prefs.highResEnabled === 'boolean') highResEnabled.value = prefs.highResEnabled
  }

  return { highResEnabled, highResFactor, hrActualW, hrActualH, restoreFromPrefs }
}
