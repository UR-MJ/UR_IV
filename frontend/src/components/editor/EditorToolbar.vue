<template>
  <div class="editor-toolbar" role="toolbar" aria-label="에디터 도구">
    <template v-for="(group, gi) in groups" :key="gi">
      <div v-if="gi > 0" class="tb-rule" />
      <button
        v-for="tool in group"
        :key="tool.id"
        type="button"
        class="tb-btn"
        :class="{ active: modelValue === tool.id }"
        :aria-label="`${tool.label} (${tool.shortcut})`"
        :aria-pressed="modelValue === tool.id"
        @pointerenter="showTip(tool, $event)"
        @pointerleave="hideTip"
        @focus="showTip(tool, $event)"
        @blur="hideTip"
        @click="$emit('select', tool.id)"
      >
        <Icon :name="tool.icon" size="19" />
      </button>
    </template>
  </div>

  <!-- 툴팁은 body 로 보낸다. 툴바가 세로로 스크롤되면 그 안에 둔 툴팁은 잘린다
       (CSS 상 overflow-y: auto 는 x 를 visible 로 둘 수 없다). -->
  <Teleport to="body">
    <div v-if="tip" class="tb-tip" :style="{ top: tip.top + 'px', left: tip.left + 'px' }">
      <span class="tb-tip-name">{{ tip.label }}</span>
      <span class="tb-tip-key">{{ tip.shortcut }}</span>
      <span v-if="tip.hint" class="tb-tip-hint">{{ tip.hint }}</span>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 캔버스 도구 세로 툴바.
 *
 * 도구를 탭 안에 두면 펜을 쓰려고 탭을 옮겨야 하고, 도구 목록만 패널 세로를
 * 360px 먹는다. 여기로 빼면 도구는 항상 보이고 패널은 '고른 도구의 옵션' 만 담는다.
 *
 * 아이콘만 있으므로 이름을 알 방법이 필요하다 — 호버하면 이름·단축키·한 줄 설명이 뜬다.
 * `title` 속성은 쓰지 않는다: 뜨기까지 1초 넘게 걸리고, 위치와 모양을 정할 수 없다.
 */
import { computed, ref } from 'vue'
import { EDITOR_TOOLS, TOOL_GROUPS, type EditorTool } from '../../utils/editorTools'

const props = withDefaults(defineProps<{
  /** 현재 선택된 도구 id (`EditorCanvas` 의 props.tool 과 같은 문자열) */
  modelValue?: string
  /** 보여줄 도구 목록. 기본은 에디터 전체 — Inpaint 는 마스크 도구만 넘긴다. */
  tools?: EditorTool[]
}>(), { tools: () => EDITOR_TOOLS })

/** 넘어온 목록에 실제로 있는 묶음만, 원래 순서대로. */
const groups = computed(() =>
  TOOL_GROUPS
    .map((kind) => props.tools.filter((t) => t.kind === kind))
    .filter((list) => list.length > 0),
)

defineEmits<{
  select: [id: string]
}>()

interface Tip {
  label: string
  shortcut: string
  hint?: string
  top: number
  left: number
}

const tip = ref<Tip | null>(null)

function showTip(tool: EditorTool, event: Event) {
  const el = event.currentTarget as HTMLElement | null
  if (!el) return
  const rect = el.getBoundingClientRect()
  tip.value = {
    label: tool.label,
    shortcut: tool.shortcut,
    hint: tool.hint,
    top: Math.round(rect.top + rect.height / 2),
    left: Math.round(rect.right + 8),
  }
}

function hideTip() {
  tip.value = null
}
</script>

<style scoped>
.editor-toolbar {
  width: 48px;
  flex-shrink: 0;
  background: var(--bg-primary);
  border-right: 1px solid var(--rule);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--sp-1) 0;
  gap: 2px;
  overflow-y: auto;
}

.tb-rule {
  width: 30px;
  height: 1px;
  background: var(--rule);
  margin: var(--sp-1) 0;
  flex-shrink: 0;
}

.tb-btn {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-base);
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
}
.tb-btn:hover {
  color: var(--text-primary);
  border-color: var(--rule);
}
.tb-btn.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
</style>

<style>
/* Teleport 로 body 에 붙으므로 scoped 가 아니다 — 이름을 tb- 로 좁게 유지한다. */
.tb-tip {
  position: fixed;
  transform: translateY(-50%);
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 2px var(--sp-2);
  padding: var(--sp-1) var(--sp-2);
  background: var(--bg-card);
  border: 1px solid var(--edge);
  border-radius: var(--radius-base);
  white-space: nowrap;
  pointer-events: none;
  z-index: 3000;
}

.tb-tip-name {
  color: var(--text-primary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
}

/* 단축키는 키캡처럼 — 눌러야 할 것과 읽을 것을 구분한다 */
.tb-tip-key {
  justify-self: end;
  min-width: 18px;
  padding: 1px 5px;
  background: var(--bg-button);
  border: 1px solid var(--rule);
  border-radius: 3px;
  color: var(--text-secondary);
  font-size: var(--fs-label);
  font-weight: var(--fw-medium);
  text-align: center;
}

.tb-tip-hint {
  grid-column: 1 / -1;
  color: var(--text-muted);
  font-size: var(--fs-meta);
}
</style>
