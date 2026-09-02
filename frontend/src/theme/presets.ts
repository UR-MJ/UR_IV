/**
 * 테마 프리셋 — `core/theme_presets.py` 의 사본.
 *
 * **원본은 Python 이다.** 앱은 Vue 가 뜨기 전에 PyQt 다이얼로그(백엔드 선택·스플래시)를
 * 먼저 그리므로 색을 시작 시점에 Python 이 읽을 수 있어야 한다. 여기는 브라우저가
 * 첫 페인트 전에 색을 넣기 위한 사본이고, 두 벌이 갈라지지 않는지는
 * `tests/test_theme_contract.py` 가 정적으로 검증한다.
 *
 * **이 파일을 직접 고치지 말 것** — `core/theme_presets.py` 를 고치고
 * `tools/gen_theme_css.py` 를 다시 돌린다.
 */

export type ThemeMode = 'dark' | 'light'

/** 색 표. `mode`/`label` 은 색이 아니라 메타데이터다. */
export type ThemeColors = Record<string, string>

/** 사용자가 설정에서 직접 바꿀 수 있는 색. 나머지는 프리셋이 정한다. */
export const EDITABLE_KEYS = ["accent", "state-info", "state-alert", "state-ok"] as const
export type EditableKey = (typeof EDITABLE_KEYS)[number]

/** 태그 분류의 색상각(도) — 프리셋이 바뀌어도 고정. */
export const TAG_HUES: Record<string, number> = {"person": 218, "scene": 178, "pose": 130, "wear": 272, "fx": 318, "nsfw": 356}

export const DEFAULT_PRESET = 'default'

export const PRESETS: Record<string, ThemeColors> = {
  default: {
    label: "기본",
    mode: "dark",
    'bg-primary': "#0A0A0A",
    'bg-secondary': "#131313",
    'bg-card': "#161616",
    'bg-input': "#131313",
    'bg-button': "#1E1E1E",
    'bg-button-hover': "#282828",
    accent: "#C9A227",
    'text-primary': "#E4E4E4",
    'text-secondary': "#A2A2A2",
    'text-muted': "#919191",
    edge: "#747474",
    rule: "#242424",
    border: "#242424",
    'border-strong': "#4A4A4A",
    'state-info': "#4C76B0",
    'state-info-fg': "#8FB8E6",
    'state-alert': "#D14141",
    'state-alert-fg': "#F87171",
    'state-ok': "#2C8549",
    'state-ok-fg': "#4ADE80",
    'state-warn': "#986D1C",
    'state-warn-fg': "#E0B341",
    'tag-person': "#8EADE1",
    'tag-scene': "#8EE1DE",
    'tag-pose': "#8EE19C",
    'tag-wear': "#BA8EE1",
    'tag-fx': "#E18EC8",
    'tag-nsfw': "#E18E94",
    'tag-neutral': "#C6C6C6",
    'tag-wild-edge': "#8A8A8A",
  },
  dark: {
    label: "다크",
    mode: "dark",
    'bg-primary': "#050505",
    'bg-secondary': "#0D0D0D",
    'bg-card': "#121212",
    'bg-input': "#181818",
    'bg-button': "#1E1E1E",
    'bg-button-hover': "#2A2A2A",
    accent: "#FACC15",
    'text-primary': "#FFFFFF",
    'text-secondary': "#B8B8B8",
    'text-muted': "#939393",
    edge: "#767676",
    rule: "#2E2E2E",
    border: "#363636",
    'border-strong': "#565656",
    'state-info': "#4C76B0",
    'state-info-fg': "#8FB8E6",
    'state-alert': "#D14141",
    'state-alert-fg': "#F87171",
    'state-ok': "#2C8549",
    'state-ok-fg': "#4ADE80",
    'state-warn': "#986D1C",
    'state-warn-fg': "#E0B341",
    'tag-person': "#8EADE1",
    'tag-scene': "#8EE1DE",
    'tag-pose': "#8EE19C",
    'tag-wear': "#BA8EE1",
    'tag-fx': "#E18EC8",
    'tag-nsfw': "#E18E94",
    'tag-neutral': "#C6C6C6",
    'tag-wild-edge': "#8A8A8A",
  },
  light: {
    label: "라이트",
    mode: "light",
    'bg-primary': "#F4F4F2",
    'bg-secondary': "#FFFFFF",
    'bg-card': "#FFFFFF",
    'bg-input': "#FFFFFF",
    'bg-button': "#E9E9E6",
    'bg-button-hover': "#DDDDD9",
    accent: "#775C00",
    'text-primary': "#1B1B19",
    'text-secondary': "#4E4E48",
    'text-muted': "#5F5F59",
    edge: "#6B6B64",
    rule: "#DCDCD7",
    border: "#DCDCD7",
    'border-strong': "#B4B4AD",
    'state-info': "#2F6099",
    'state-info-fg': "#2F6099",
    'state-alert': "#B3261E",
    'state-alert-fg': "#B3261E",
    'state-ok': "#1F7A38",
    'state-ok-fg': "#1C6D32",
    'state-warn': "#8A5A00",
    'state-warn-fg': "#845600",
    'tag-person': "#385EA1",
    'tag-scene': "#266968",
    'tag-pose': "#266C32",
    'tag-wear': "#793DAE",
    'tag-fx': "#9E3780",
    'tag-nsfw': "#A63A42",
    'tag-neutral': "#55554F",
    'tag-wild-edge': "#8A8A82",
  },
}

export const PRESET_IDS = Object.keys(PRESETS)
