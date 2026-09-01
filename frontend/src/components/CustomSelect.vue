<template>
  <div class="csel" :class="{ open: isOpen }" ref="root">
    <button
      ref="trigger"
      type="button"
      class="csel-display"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
      :aria-controls="listboxId"
      :aria-activedescendant="activeDescendant"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <span class="csel-text">{{ displayText }}</span>
      <span class="csel-arrow" aria-hidden="true"><Icon name="chevron-down" /></span>
    </button>
    <div :id="listboxId" class="csel-dropdown" role="listbox" v-if="isOpen">
      <template v-if="normalizedGroups.length">
        <section v-for="(group, groupIndex) in normalizedGroups"
          :key="`${group.source || group.label}-${groupIndex}`" class="csel-group"
          role="group" :aria-label="group.label">
          <div class="csel-group-header" role="presentation">
            <span>{{ group.label }}</span>
            <span v-if="group.primary" class="csel-group-main">메인</span>
            <span v-else-if="group.source" class="csel-group-source">{{ group.source }}</span>
          </div>
          <div v-for="(opt, optionIndex) in group.options"
            :key="`${group.source || group.label}-${String(opt)}-${optionIndex}`"
            class="csel-option csel-group-option"
            :class="{ selected: modelValue === opt, active: activeIndex === optionFlatIndex(groupIndex, optionIndex) }"
            :id="optionDomId(optionFlatIndex(groupIndex, optionIndex))"
            role="option"
            :aria-selected="modelValue === opt"
            @mouseenter="activeIndex = optionFlatIndex(groupIndex, optionIndex)"
            @click="select(opt)"
          >{{ opt }}</div>
        </section>
      </template>
      <template v-else>
        <div v-for="(opt, optionIndex) in options" :key="`${String(opt)}-${optionIndex}`" class="csel-option"
          :class="{ selected: modelValue === opt, active: activeIndex === optionIndex }"
          :id="optionDomId(optionIndex)"
          role="option"
          :aria-selected="modelValue === opt"
          @mouseenter="activeIndex = optionIndex"
          @click="select(opt)">{{ opt }}</div>
      </template>
      <div v-if="!hasOptions" class="csel-empty">항목 없음</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, useId, watch } from 'vue'

type SelectValue = string | number
interface SelectOptionGroup {
  label: string
  source?: string
  primary?: boolean
  options: SelectValue[]
}

const props = withDefaults(defineProps<{
  modelValue?: SelectValue
  options?: SelectValue[]
  optionGroups?: SelectOptionGroup[]
  placeholder?: string
}>(), {
  modelValue: '',
  options: () => [],
  optionGroups: () => [],
  placeholder: '선택...',
})
const emit = defineEmits<{ 'update:modelValue': [value: SelectValue] }>()

const isOpen = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const activeIndex = ref(-1)
const listboxId = `csel-listbox-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

const displayText = computed(() => props.modelValue || props.placeholder)
const normalizedGroups = computed<SelectOptionGroup[]>(() => props.optionGroups
  .filter(group => group && Array.isArray(group.options) && group.options.length > 0)
  .map(group => ({
    label: String(group.label || group.source || 'Models'),
    source: group.source ? String(group.source).toUpperCase() : '',
    primary: Boolean(group.primary),
    options: group.options,
  })))
const hasOptions = computed(() => normalizedGroups.value.length > 0 || props.options.length > 0)
const flatOptions = computed<SelectValue[]>(() => normalizedGroups.value.length
  ? normalizedGroups.value.flatMap(group => group.options)
  : props.options)
const activeDescendant = computed(() => activeIndex.value >= 0
  ? optionDomId(activeIndex.value)
  : undefined)

watch(activeIndex, index => {
  if (!isOpen.value || index < 0) return
  void nextTick(() => {
    document.getElementById(optionDomId(index))?.scrollIntoView({ block: 'nearest' })
  })
})

function optionFlatIndex(groupIndex: number, optionIndex: number) {
  return normalizedGroups.value
    .slice(0, groupIndex)
    .reduce((total, group) => total + group.options.length, optionIndex)
}

function optionDomId(index: number) {
  return `${listboxId}-option-${index}`
}

function open(direction: 1 | -1 = 1) {
  if (!flatOptions.value.length) return
  isOpen.value = true
  const selectedIndex = flatOptions.value.findIndex(option => option === props.modelValue)
  activeIndex.value = selectedIndex >= 0
    ? selectedIndex
    : direction > 0 ? 0 : flatOptions.value.length - 1
}

function toggle() {
  if (isOpen.value) isOpen.value = false
  else open()
}

function moveActive(delta: 1 | -1) {
  if (!isOpen.value) {
    open(delta)
    return
  }
  const length = flatOptions.value.length
  if (!length) return
  activeIndex.value = (activeIndex.value + delta + length) % length
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Home' || event.key === 'End') {
    if (!isOpen.value) return
    event.preventDefault()
    activeIndex.value = event.key === 'Home' ? 0 : flatOptions.value.length - 1
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!isOpen.value) open()
    else if (activeIndex.value >= 0) select(flatOptions.value[activeIndex.value])
    return
  }
  if (event.key === 'Escape' && isOpen.value) {
    event.preventDefault()
    isOpen.value = false
  } else if (event.key === 'Tab') {
    isOpen.value = false
  }
}

function select(opt: SelectValue) {
  emit('update:modelValue', opt)
  isOpen.value = false
  void nextTick(() => trigger.value?.focus())
}

function onClickOutside(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) isOpen.value = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.csel { position: relative; width: 100%; }
.csel-display {
  width: 100%; text-align: left;
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-primary); font-size: 14px;
  cursor: pointer; transition: var(--transition);
}
.csel.open .csel-display { border-color: var(--accent); }
.csel-display:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
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
.csel-option.active:not(.selected) { background: var(--accent-dim); color: var(--accent); }
.csel-option.selected { background: var(--accent); color: #000; font-weight: var(--fw-bold); }
.csel-group + .csel-group { border-top: 1px solid var(--border); }
.csel-group-header {
  position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px;
  padding: 7px 11px; background: #141414; color: var(--text-muted);
  font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0; cursor: default;
}
.csel-group-main, .csel-group-source {
  padding: 2px 5px; border: 1px solid rgba(96,165,250,.35); border-radius: 7px;
  background: rgba(96,165,250,.1); color: #60a5fa; font-size: 7px; letter-spacing: 0;
}
.csel-group-source { border-color: var(--border); background: var(--bg-input); color: var(--text-muted); }
.csel-group-option { padding-left: 17px; }
.csel-empty { padding: 12px; color: var(--text-muted); text-align: center; font-size: 12px; }
</style>
