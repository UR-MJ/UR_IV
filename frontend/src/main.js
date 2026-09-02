import { createApp } from 'vue'
// 토큰 폴백을 맨 먼저 — 이게 다른 스타일보다 아래에 깔려야
// 스크립트가 실패해도 앱이 색 없이 뜨지 않는다(theme-fallback.css 주석 참조).
import './styles/theme-fallback.css'
import './style.css'
import './styles/panels.css'
import './styles/editorPanels.css'
import './styles/galleryShared.css'
import App from './App.vue'
import router from './router.js'
import Icon from './components/Icon.vue'
import { bootTheme } from './theme/applyTheme'

// 색은 첫 페인트 전에 넣는다. 영속 설정(config/ui_prefs.json)은 브리지로
// uiPrefsLoaded 가 와야 읽히는데 그건 Vue 가 뜬 뒤라, 그때 칠하면 기본 테마가
// 한 번 번쩍인 뒤 바뀐다. bootTheme() 은 localStorage 만 읽어 동기로 끝난다.
// (디스크 값과의 차이는 App.vue 의 uiPrefsLoaded 에서 reconcileTheme 이 맞춘다.)
bootTheme()

// 아이콘은 30개 파일에서 쓰는 원시 요소라 전역으로 등록한다 —
// 파일마다 import 를 넣으면 아이콘 하나 바꿀 때마다 import 줄부터 손봐야 한다.
createApp(App).use(router).component('Icon', Icon).mount('#app')
