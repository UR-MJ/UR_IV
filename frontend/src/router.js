import { createRouter, createMemoryHistory } from 'vue-router'

import ImageViewer from './components/ImageViewer.vue'
import I2IView from './views/I2IView.vue'
import InpaintView from './views/InpaintView.vue'
import EventGenView from './views/EventGenView.vue'
import SearchView from './views/SearchView.vue'
import BatchView from './views/BatchView.vue'
import GalleryView from './views/GalleryView.vue'
import XYZPlotView from './views/XYZPlotView.vue'
import PngInfoView from './views/PngInfoView.vue'
import FavoritesView from './views/FavoritesView.vue'
import SettingsView from './views/SettingsView.vue'
import EditorView from './views/EditorView.vue'
import WebView from './views/WebView.vue'
import BackendView from './views/BackendView.vue'

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
  { path: '/web', name: 'web', component: WebView, meta: { title: 'Web' } },
  { path: '/backend', name: 'backend', component: BackendView, meta: { title: 'Backend UI' } },
]

const router = createRouter({
  history: createMemoryHistory(),
  routes,
})

export default router
export { routes }
