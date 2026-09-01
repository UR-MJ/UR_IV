<template>
  <svg
    class="icon"
    :class="{ 'icon-filled': filled }"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    :fill="filled ? 'currentColor' : 'none'"
    :stroke="filled ? 'none' : 'currentColor'"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<script setup lang="ts">
/**
 * 단색 SVG 아이콘. 전역 등록되어 있어 import 없이 `<Icon name="save" />` 로 쓴다.
 *
 * 색은 `currentColor` 라 부모의 `color` 를 따라간다 — 기존 CSS(호버·활성·비활성)가
 * 그대로 먹고, 이모지처럼 제 색을 우기지 않는다.
 *
 * 접근성: 아이콘 자체는 `aria-hidden` 이다. 아이콘만 있는 버튼은 `title`(또는
 * `aria-label`)로 이름을 주어야 한다 — 이모지 시절에도 대부분 title 이 이미 있다.
 */
import { computed } from 'vue'
import { ICONS, FILLED } from '../icons'

const props = withDefaults(defineProps<{
  name: string
  /**
   * 기본값이 em 인 이유: 이모지는 글자였기 때문에 크기를 `font-size` 로 키우는
   * CSS 가 곳곳에 있다(`.drop-icon { font-size: 48px }` 등). px 로 고정하면 그런
   * 규칙이 전부 죽어 큰 장식 아이콘이 16px 로 쪼그라든다. em 이면 그대로 산다.
   * 1.15em 은 본문 13px 옆에서 15px — 선 아이콘이 글자와 광학적으로 맞는 크기다.
   */
  size?: number | string
  /** 선 두께(viewBox 단위라 크기와 무관하게 일정하다). */
  strokeWidth?: number | string
}>(), {
  size: '1.15em',
  strokeWidth: 1.6,
})

const paths = computed(() => ICONS[props.name] ?? [])
const filled = computed(() => !!FILLED[props.name])
</script>

<style scoped>
.icon {
  display: inline-block;
  vertical-align: -0.16em;
  flex-shrink: 0;
}
</style>
