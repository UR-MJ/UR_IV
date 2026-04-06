import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',  // 상대 경로 (QWebEngineView 로컬 로드용)
  build: {
    outDir: '../frontend_dist',  // 프로젝트 루트/frontend_dist에 빌드
    emptyOutDir: true,
  },
})
