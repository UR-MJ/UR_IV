<template>
  <section class="panel-section" :class="{ open }">
    <button type="button" class="ps-head" :aria-expanded="open" @click="toggle">
      <Icon :name="open ? 'chevron-down' : 'chevron-right'" size="14" />
      <span class="ps-title">{{ title }}</span>
      <span v-if="badge" class="ps-badge">{{ badge }}</span>
    </button>
    <div v-show="open" class="ps-body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
/**
 * 접이식 섹션.
 *
 * 사이드 패널이 화면보다 길어진 원인은 모든 섹션이 항상 펼쳐져 있는 것이다
 * (모자이크 탭 1077px = 화면의 135%). 접을 수 있으면 지금 쓰는 것만 펴 둘 수 있다.
 *
 * 열림 상태는 localStorage 에 남긴다 — 매번 같은 섹션을 다시 펴는 건 일이다.
 * `storageKey` 를 주지 않으면 기억하지 않는다(임시 섹션용).
 */
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  /** 제목 오른쪽의 작은 보조 표시 — 접힌 상태에서 안에 뭐가 있는지 알려준다 */
  badge?: string | number
  /** 처음 열려 있을지. 저장된 값이 있으면 그쪽이 이긴다. */
  defaultOpen?: boolean
  storageKey?: string
}>(), {
  badge: '',
  defaultOpen: true,
  storageKey: '',
})

function initial(): boolean {
  if (!props.storageKey) return props.defaultOpen
  const saved = window.localStorage.getItem(`editorSection:${props.storageKey}`)
  return saved === null ? props.defaultOpen : saved === '1'
}

const open = ref(initial())

function toggle() {
  open.value = !open.value
  if (props.storageKey) {
    window.localStorage.setItem(`editorSection:${props.storageKey}`, open.value ? '1' : '0')
  }
}
</script>

<style scoped>
.panel-section {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--rule);
}

.ps-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  height: 34px;
  padding: 0 var(--sp-1);
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  text-align: left;
}
.ps-head:hover {
  color: var(--text-secondary);
}

.ps-title {
  flex: 1;
  color: var(--text-secondary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
}
.panel-section.open .ps-title {
  color: var(--text-primary);
}

.ps-badge {
  color: var(--text-muted);
  font-size: var(--fs-label);
  font-variant-numeric: tabular-nums;
}

.ps-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: 0 var(--sp-1) var(--sp-3);
}
</style>
