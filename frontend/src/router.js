import { createRouter, createMemoryHistory } from 'vue-router'

import ImageViewer from './components/ImageViewer.vue'

// T2I만 초기 번들에 포함하고 나머지 탭은 첫 방문 시 로드한다.
// 로컬 QWebEngine에서도 초기 JS 파싱과 컴포넌트 생성 비용을 줄일 수 있다.
const I2IView = () => import('./views/I2IView.vue')
const InpaintView = () => import('./views/InpaintView.vue')
const EventGenView = () => import('./views/EventGenView.vue')
const SearchView = () => import('./views/SearchView.vue')
const BatchView = () => import('./views/BatchView.vue')
const GalleryView = () => import('./views/GalleryView.vue')
const XYZPlotView = () => import('./views/XYZPlotView.vue')
const PngInfoView = () => import('./views/PngInfoView.vue')
const FavoritesView = () => import('./views/FavoritesView.vue')
const SettingsView = () => import('./views/SettingsView.vue')
const EditorView = () => import('./views/EditorView.vue')
const CreatorStudioView = () => import('./views/CreatorStudioView.vue')

const routes = [
  { path: '/', name: 't2i', component: ImageViewer, meta: { title: 'T2I' } },
  { path: '/i2i', name: 'i2i', component: I2IView, meta: { title: 'I2I' } },
  { path: '/inpaint', name: 'inpaint', component: InpaintView, meta: { title: 'Inpaint' } },
  { path: '/event', name: 'event', component: EventGenView, meta: { title: 'Event Gen' } },
  { path: '/search', name: 'search', component: SearchView, meta: { title: 'Search' } },
  { path: '/batch', name: 'batch', component: BatchView, meta: { title: 'Batch / Upscale' } },
  { path: '/gallery', name: 'gallery', component: GalleryView, meta: { title: 'Gallery' } },
  { path: '/xyz', name: 'xyz', component: XYZPlotView, meta: { title: 'XYZ Plot' } },
  { path: '/png', name: 'png', component: PngInfoView, meta: { title: 'PNG Info' } },
  { path: '/fav', name: 'fav', component: FavoritesView, meta: { title: 'Favorites' } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { title: 'Settings' } },
  { path: '/editor', name: 'editor', component: EditorView, meta: { title: 'Editor' } },
  { path: '/creator', name: 'creator', component: CreatorStudioView, meta: { title: 'Creator' } },
  { path: '/chat', name: 'chat', component: () => import('./views/ChatView.vue'), meta: { title: '대화' } },
]

const router = createRouter({
  history: createMemoryHistory(),
  routes,
})

export default router
export { routes }
