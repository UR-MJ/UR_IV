import { createApp } from 'vue'
import './style.css'
import './styles/editorPanels.css'
import App from './App.vue'
import router from './router.js'
import Icon from './components/Icon.vue'

// 아이콘은 30개 파일에서 쓰는 원시 요소라 전역으로 등록한다 —
// 파일마다 import 를 넣으면 아이콘 하나 바꿀 때마다 import 줄부터 손봐야 한다.
createApp(App).use(router).component('Icon', Icon).mount('#app')
