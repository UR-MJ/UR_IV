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
.tsw.on { background: rgba(74,222,128,0.28); border-color: #4ade80; }
.tsw.on .tsw-knob { left: 17px; background: #4ade80; }
.tsw.sm { width: 30px; height: 17px; border-radius: 9px; }
.tsw.sm .tsw-knob { width: 13px; height: 13px; }
.tsw.sm.on .tsw-knob { left: 14px; }
</style>
