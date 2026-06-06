import { reactive } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

/**
 * 등급(rating) 필터 g/s/q/e — 검색 덱에 어떤 등급을 포함할지 (App.vue 분할 ④).
 * 단일 소스: config/ui_prefs.json 의 ratingFilter(bool[4], g/s/q/e 순). Python은 시작 시
 * _restore_runtime_prefs로 직접 읽고, set_rating_filter로도 갱신받는다.
 *
 * @param {object} deps
 * @param {Function} deps.saveUiPrefs (payload) ui_prefs 영속
 */
export function useRatingFilter({ saveUiPrefs }) {
  const ratingFilters = reactive([
    { key: 'g', label: 'G', on: true },
    { key: 's', label: 'S', on: true },
    { key: 'q', label: 'Q', on: false },
    { key: 'e', label: 'E', on: false },
  ])

  // localStorage 복원 (빠른 폴백 — 시작 시 uiPrefs가 override)
  try {
    const saved = JSON.parse(window.localStorage.getItem('ratingFilter') || '[]')
    if (saved.length === 4) saved.forEach((v, i) => { ratingFilters[i].on = v })
  } catch {}

  function pushRatingFilter() {
    requestAction('set_rating_filter', { ratings: ratingFilters.filter(r => r.on).map(r => r.key) })
  }

  function saveRatingFilter() {
    window.localStorage.setItem('ratingFilter', JSON.stringify(ratingFilters.map(r => r.on)))
    saveUiPrefs({ ratingFilter: ratingFilters.map(r => r.on) })
    pushRatingFilter()   // Python에 전달
  }

  // 단일 소스(ui_prefs) 복원 — App.vue uiPrefsLoaded 핸들러에서 호출
  function restoreFromPrefs(prefs) {
    if (!prefs || !Array.isArray(prefs.ratingFilter) || prefs.ratingFilter.length !== ratingFilters.length) return
    prefs.ratingFilter.forEach((v, i) => { ratingFilters[i].on = !!v })
    try { window.localStorage.setItem('ratingFilter', JSON.stringify(prefs.ratingFilter)) } catch {}
    pushRatingFilter()
  }

  return { ratingFilters, saveRatingFilter, pushRatingFilter, restoreFromPrefs }
}
