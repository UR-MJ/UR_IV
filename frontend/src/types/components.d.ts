/**
 * 전역 등록 컴포넌트의 타입 선언.
 *
 * `main.js` 에서 `app.component('Icon', ...)` 로 등록한 것은 vue-tsc 가 알 수 없어
 * 템플릿에서 쓰면 "존재하지 않는 컴포넌트"로 잡힌다. 여기서 알려준다.
 */
declare module 'vue' {
  export interface GlobalComponents {
    Icon: typeof import('../components/Icon.vue')['default']
  }
}

export {}
