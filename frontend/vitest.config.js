import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    // `.test.ts` 만 본다. `src/studio/resumableTransport.test.mjs` 는 node:test 로 쓰여
    // (`node --test`) vitest 가 열면 "No test suite found" 로 실패한다 — 남의 러너다.
    include: ['src/**/*.test.ts'],
    // 순수 로직 + Vue SSR 렌더링은 DOM/브라우저 서버 없이 실행한다.
    environment: 'node',
  },
})
