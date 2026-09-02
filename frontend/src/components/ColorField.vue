<template>
  <div class="cf">
    <div class="cf-head">
      <span class="cf-label">{{ label }}</span>
      <button
        type="button"
        class="cf-reset"
        :disabled="!isOverridden"
        :title="isOverridden ? `프리셋 기본값 ${presetSwatch} 로 되돌립니다` : '프리셋 기본값 그대로입니다'"
        @click="emit('reset')"
      >되돌리기</button>
    </div>
    <p v-if="hint" class="cf-hint">{{ hint }}</p>

    <div class="cf-row">
      <!-- 견본 자체가 버튼이다 — 네이티브 색 선택기를 덮어 씌워 클릭 대상을 넓힌다 -->
      <label class="cf-swatch" :style="{ background: applied }">
        <input
          class="cf-picker"
          type="color"
          :value="applied"
          :aria-label="`${label} 색 고르기`"
          @input="onPick"
        />
      </label>
      <input
        class="cf-hex"
        :class="{ bad: !draftValid }"
        :value="draft"
        :aria-label="`${label} hex 코드`"
        spellcheck="false"
        autocomplete="off"
        maxlength="7"
        @input="onType"
        @blur="onBlur"
      />
      <span
        v-if="isOverridden"
        class="cf-preset"
        :style="{ background: presetSwatch }"
        :title="`프리셋 기본값 ${presetSwatch}`"
      ></span>
    </div>

    <p v-if="!draftValid" class="cf-note bad">
      <Icon name="alert" size="12" />
      <span><code>#RRGGBB</code> 형식이 아닙니다 — 입력만 남기고 색은 바꾸지 않았습니다.</span>
    </p>
    <p v-else-if="lowContrast" class="cf-note bad">
      <Icon name="alert" size="12" />
      <span>
        {{ contrastLabel }} <strong>{{ ratioText }}:1</strong> —
        기준 {{ MIN_CONTRAST }}:1 에 못 미칩니다. {{ contrastConsequence }}
      </span>
    </p>
    <p v-else class="cf-note ok">
      <Icon name="check" size="12" />
      <span>{{ contrastLabel }} <strong>{{ ratioText }}:1</strong></span>
    </p>
  </div>
</template>

<script setup lang="ts">
/**
 * 색 하나를 고르는 칸 — 견본 · hex 직접 입력 · 되돌리기 · 대비 경고.
 *
 * **왜 대비를 숫자로 보여주는가**: 사용자는 아무 색이나 고를 수 있어야 하지만
 * (자기 화면이다), 고른 색이 안 읽힌다는 사실은 알고 골라야 한다. 조용히 넘어가면
 * "글씨가 왜 안 보이지" 로 돌아온다. 막지는 않고 알리기만 한다.
 *
 * **잘못된 hex 는 반영하지 않는다**: 타이핑 중간의 `#F8` 마다 화면 색이 튀면
 * 무슨 색을 고르는 중인지 알 수 없다. 입력칸에만 남기고 테마에는 넣지 않는다.
 */
import { computed, ref, watch } from 'vue'
import {
  MIN_ON_ACCENT_CONTRAST, contrastRatio, deriveAccent, isValidHex, normalizeHex,
} from '../theme/applyTheme'

const props = withDefaults(defineProps<{
  /** 현재 색(hex). 유효하지 않으면 검정으로 보여 준다. */
  modelValue: string
  label: string
  hint?: string
  /** 프리셋이 정한 기본값 — '되돌리기' 의 목적지이자 덮어썼는지 판단 기준. */
  presetValue: string
  /**
   * 이 색이 화면에서 하는 일. **판정 기준이 여기서 갈린다.**
   * - `accent` — 주 버튼의 면. 그 위 글자가 읽히는지 본다(`on-accent` ↔ `accent-fill`).
   * - `fill`   — 배지의 면. 그 위 흰 글자가 읽히는지 본다.
   * 배경 대비로 재면 **채움색이 배경 위 글자인 척** 하게 되어, 기본 프리셋조차
   * 경고가 뜬다(실제로 그랬다: 선택·알림·연결이 전부 3.9:1 로 빨갛게 떴다).
   */
  role?: 'accent' | 'fill'
  /** 파생색 계산에 쓰는 테마 밝기. */
  mode?: string
}>(), { hint: '', role: 'fill', mode: 'dark' })

const emit = defineEmits<{ 'update:modelValue': [value: string]; reset: [] }>()

/** 경고 기준은 applyTheme 의 값을 그대로 쓴다 — 두 곳에 4.5 를 적지 않는다. */
const MIN_CONTRAST = MIN_ON_ACCENT_CONTRAST

/** 입력칸에 보이는 문자열. 유효할 때만 부모로 올라간다. */
const draft = ref(props.modelValue)

// 부모가 값을 바꿨을 때만 입력칸을 덮어쓴다. 무조건 덮어쓰면 내가 친 `#f87`이
// 정규화된 `#FF8877` 로 바뀌면서 커서가 튄다 — 같은 색이면 건드리지 않는다.
watch(() => props.modelValue, (next) => {
  if (!isValidHex(draft.value) || normalizeHex(draft.value) !== normalizeHex(next)) {
    draft.value = next
  }
})

const draftValid = computed(() => isValidHex(draft.value))
const applied = computed(() => (isValidHex(props.modelValue) ? normalizeHex(props.modelValue) : '#000000'))
const presetSwatch = computed(() => (isValidHex(props.presetValue) ? normalizeHex(props.presetValue) : applied.value))
const isOverridden = computed(() => applied.value !== presetSwatch.value)

// 아직 부모에 올라가지 않은 유효한 입력도 미리 평가한다 — 경고가 한 박자 늦으면
// 사용자는 이미 다음 색을 치고 있다.
/** 지금 평가할 색 — 아직 부모에 안 올라간 유효한 입력도 포함. */
const candidate = computed(() =>
  draftValid.value ? normalizeHex(draft.value) : applied.value,
)

const ratio = computed(() => {
  if (props.role === 'accent') {
    // 주 버튼: 면(accent-fill)과 그 위 글자(on-accent). 둘 다 사용자의 색에서 파생된다.
    const derived = deriveAccent(candidate.value, props.mode)
    return contrastRatio(derived['on-accent'], derived['accent-fill'])
  }
  // 배지: 채움 위의 흰 글자.
  return contrastRatio('#FFFFFF', candidate.value)
})
const ratioText = computed(() => ratio.value.toFixed(2))
const lowContrast = computed(() => ratio.value < MIN_CONTRAST)

const contrastLabel = computed(() =>
  props.role === 'accent' ? '버튼 글자 대비' : '배지의 흰 글자 대비',
)
const contrastConsequence = computed(() =>
  props.role === 'accent'
    ? '주 버튼의 글자가 잘 안 보입니다.'
    : '이 색으로 채운 배지 위의 글자가 잘 안 보입니다. (본문 글자색은 자동으로 맞춰집니다.)',
)

function onType(event: Event) {
  const value = (event.target as HTMLInputElement).value
  draft.value = value
  if (isValidHex(value)) emit('update:modelValue', normalizeHex(value))
}

/** 포커스를 떠나면 입력칸을 실제 적용된 값으로 맞춘다(잘못 친 값은 되돌아간다). */
function onBlur() {
  draft.value = applied.value
}

function onPick(event: Event) {
  const value = normalizeHex((event.target as HTMLInputElement).value)
  draft.value = value
  emit('update:modelValue', value)
}
</script>

<style scoped>
.cf { display: flex; flex-direction: column; gap: 6px; }
.cf-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cf-label { color: var(--text-primary); font-size: 12px; font-weight: var(--fw-bold); letter-spacing: 0; }
.cf-hint { margin: 0; color: var(--text-muted); font-size: var(--fs-label); line-height: 1.45; }

.cf-reset {
  flex-shrink: 0; padding: 3px 9px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--bg-button); color: var(--text-secondary);
  font-family: inherit; font-size: var(--fs-label); font-weight: var(--fw-bold); letter-spacing: 0;
  cursor: pointer; transition: var(--transition);
}
.cf-reset:hover:not(:disabled) { background: var(--bg-button-hover); border-color: var(--edge); color: var(--text-primary); }
.cf-reset:disabled { opacity: .38; cursor: default; }

.cf-row { display: flex; align-items: center; gap: 8px; }
.cf-swatch {
  position: relative; overflow: hidden; flex-shrink: 0;
  width: 34px; height: 30px; border: 1px solid var(--border-strong); border-radius: var(--radius-base);
  cursor: pointer;
}
/* 네이티브 색 선택기는 브라우저마다 생김새가 달라 숨기고, 견본 전체를 클릭 대상으로 쓴다 */
.cf-picker { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; border: none; padding: 0; cursor: pointer; }

.cf-hex {
  flex: 1; min-width: 0; padding: 7px 10px;
  border: 1px solid var(--border); border-radius: var(--radius-base);
  background: var(--bg-input); color: var(--text-primary);
  font-family: 'Consolas', monospace; font-size: 12px; font-weight: var(--fw-bold);
  outline: none;
}
.cf-hex:focus { border-color: var(--accent); }
.cf-hex.bad { border-color: var(--state-alert-fg); }

/* 프리셋 기본값 견본 — 되돌리면 무슨 색이 되는지 보여 준다 */
.cf-preset {
  flex-shrink: 0; width: 14px; height: 14px; border-radius: 50%;
  border: 1px solid var(--border-strong);
}

.cf-note { margin: 0; display: flex; align-items: flex-start; gap: 5px; font-size: var(--fs-label); line-height: 1.45; }
.cf-note code { font-family: 'Consolas', monospace; }
.cf-note.ok { color: var(--text-muted); }
.cf-note.bad { color: var(--state-alert-fg); }
.cf-note .icon { margin-top: 2px; }
</style>
