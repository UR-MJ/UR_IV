<template>
  <button type="button" class="tsw" :class="{ on: modelValue, sm: size === 'sm' }"
    role="switch" :aria-checked="modelValue" @click.stop="$emit('update:modelValue', !modelValue)">
    <span class="tsw-knob"></span>
  </button>
</template>

<script setup lang="ts">
// 첫 TypeScript 컴포넌트(② 점진 전환). 타입 기반 props/emits.
withDefaults(defineProps<{ modelValue?: boolean; size?: 'sm' | 'md' }>(), {
  modelValue: false,
  size: 'md',
})
defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<style scoped>
.tsw { width: 36px; height: 20px; border-radius: 11px; background: var(--bg-button); border: 1px solid var(--border); position: relative; cursor: pointer; transition: background .18s, border-color .18s; padding: 0; flex-shrink: 0; display: inline-block; vertical-align: middle; }
.tsw-knob { position: absolute; top: 1px; left: 1px; width: 16px; height: 16px; border-radius: 50%; background: var(--text-muted); transition: left .18s, background .18s; }
/* 켜짐 표시는 '면'이 아니라 표시등이라 --state-ok(어두운 채움) 이 아닌 -fg 를 쓴다.
   초록 틴트 트랙 위에서 채움색 노브는 대비가 죽어 상태가 안 보인다. */
.tsw.on { background: rgba(74,222,128,0.28); border-color: var(--state-ok-fg); }
.tsw.on .tsw-knob { left: 17px; background: var(--state-ok-fg); }
.tsw.sm { width: 30px; height: 17px; border-radius: 9px; }
.tsw.sm .tsw-knob { width: 13px; height: 13px; }
.tsw.sm.on .tsw-knob { left: 14px; }
</style>
