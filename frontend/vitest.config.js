import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    // `.test.ts` 만 본다. `src/studio/resumableTransport.test.mjs` 는 node:test 로 쓰여
    // (`node --test`) vitest 가 열면 "No test suite found" 로 실패한다 — 남의 러너다.
    include: ['src/**/*.test.ts'],
    // 순수 로직만 테스트한다. DOM 이 필요한 컴포넌트 테스트는 아직 없다 —
    // 필요해지면 jsdom 을 붙이고 이 줄을 environment: 'jsdom' 으로 바꾼다.
    environment: 'node',
  },
})
