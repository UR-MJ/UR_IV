<template>
  <div class="csel" :class="{ open: isOpen }" ref="root">
    <div class="csel-display" @click="isOpen = !isOpen">
      <span class="csel-text">{{ displayText }}</span>
      <span class="csel-arrow">▾</span>
    </div>
    <div class="csel-dropdown" v-if="isOpen">
      <div v-for="opt in options" :key="opt" class="csel-option"
        :class="{ selected: modelValue === opt }"
        @click="select(opt)">{{ opt }}</div>
      <div v-if="options.length === 0" class="csel-empty">No options</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Select...' },
})
const emit = defineEmits(['update:modelValue'])

const isOpen = ref(false)
const root = ref(null)

const displayText = computed(() => props.modelValue || props.placeholder)

function select(opt) {
  emit('update:modelValue', opt)
  isOpen.value = false
}

function onClickOutside(e) {
  if (root.value && !root.value.contains(e.target)) isOpen.value = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.csel { position: relative; width: 100%; }
.csel-display {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-primary); font-size: 14px;
  cursor: pointer; transition: var(--transition);
}
.csel.open .csel-display { border-color: var(--accent); }
.csel-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.csel-arrow { color: var(--text-muted); font-size: 12px; flex-shrink: 0; }
.csel-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 200;
  max-height: 240px; overflow-y: auto;
  background: #1A1A1A; border: 1px solid var(--border); border-radius: 8px;
  margin-top: 2px; box-shadow: 0 12px 32px rgba(0,0,0,0.7);
}
.csel-option {
  padding: 8px 14px; color: var(--text-secondary); font-size: 13px;
  cursor: pointer; transition: background 0.1s;
}
.csel-option:hover { background: var(--accent-dim); color: var(--accent); }
.csel-option.selected { background: var(--accent); color: #000; font-weight: 700; }
.csel-empty { padding: 12px; color: var(--text-muted); text-align: center; font-size: 12px; }
</style>
