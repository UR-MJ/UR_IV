/**
 * 에디터 캔버스 도구 목록 — 세로 툴바와 키보드 단축키의 단일 출처.
 *
 * 지금까지 도구는 세 군데에 흩어져 있었다: `MosaicPanel` 의 숫자 id(0~4),
 * `DrawPanel` 의 별도 id(0~9), 그리고 `EditorView` 안의 변환 도구. 그래서 도구를
 * 바꾸려면 탭을 옮겨야 했고, 어떤 도구가 있는지 한눈에 볼 방법이 없었다.
 * 여기 모아두면 툴바·툴팁·단축키가 같은 목록을 본다.
 *
 * `id` 는 `EditorCanvas` 의 `props.tool` 문자열과 정확히 같아야 한다 —
 * 캔버스가 `props.tool === 'brush'` 처럼 문자열로 분기한다.
 */

export type ToolKind = 'mask' | 'draw' | 'transform'

export interface EditorTool {
  /** `EditorCanvas` 의 props.tool 값 */
  id: string
  label: string
  /** 아이콘 레지스트리의 이름 */
  icon: string
  /** 대문자 한 글자. 툴팁에 함께 보여주고 키보드로도 받는다. */
  shortcut: string
  kind: ToolKind
  /** 툴팁 두 번째 줄 — 도구가 뭘 하는지 한 줄. 없으면 생략된다. */
  hint?: string
}

export const EDITOR_TOOLS: EditorTool[] = [
  // ── 선택 · 마스크 ──
  { id: 'box', label: '사각 선택', icon: 'marquee', shortcut: 'M', kind: 'mask', hint: '드래그해서 영역 지정' },
  { id: 'lasso', label: '올가미', icon: 'lasso', shortcut: 'L', kind: 'mask', hint: '자유 곡선으로 영역 지정' },
  { id: 'brush', label: '마스크 브러시', icon: 'brush', shortcut: 'B', kind: 'mask', hint: '칠한 곳이 효과 대상' },
  { id: 'eraser', label: '지우개', icon: 'eraser', shortcut: 'E', kind: 'mask', hint: '마스크를 지운다' },
  { id: 'stamp', label: '스탬프', icon: 'circle', shortcut: 'S', kind: 'mask', hint: '같은 모양을 반복해 찍는다' },

  // ── 그리기 (드로잉 레이어) ──
  { id: 'pen', label: '펜', icon: 'pencil', shortcut: 'P', kind: 'draw', hint: '자유 곡선' },
  { id: 'line', label: '직선', icon: 'minus', shortcut: 'N', kind: 'draw' },
  { id: 'rect', label: '사각형', icon: 'square', shortcut: 'R', kind: 'draw' },
  { id: 'ellipse', label: '원 · 타원', icon: 'circle', shortcut: 'O', kind: 'draw' },
  { id: 'fill', label: '채우기', icon: 'bucket', shortcut: 'G', kind: 'draw', hint: '비슷한 색 영역을 한 번에' },
  { id: 'eyedropper', label: '스포이트', icon: 'eyedropper', shortcut: 'I', kind: 'draw', hint: '화면의 색을 집는다' },
  { id: 'clone_stamp', label: '클론 스탬프', icon: 'cards', shortcut: 'Y', kind: 'draw', hint: 'Alt+클릭으로 원점 지정' },
  { id: 'text_overlay', label: '텍스트', icon: 'type', shortcut: 'T', kind: 'draw', hint: '찍은 자리에 바로 입력' },
  { id: 'gradient', label: '그라디언트', icon: 'gradient', shortcut: 'D', kind: 'draw', hint: '드래그 방향으로 두 색' },
  { id: 'heal', label: '복원 브러시', icon: 'wand', shortcut: 'J', kind: 'draw', hint: '칠한 자리를 주변으로 메운다' },
]

/**
 * 툴바에 구분선을 넣기 위한 묶음 순서.
 *
 * 자르기·영역 이동·원근 보정은 여기 없다. 셋 다 **선택 영역이 있어야** 도는 작업이라
 * 상시 모드가 아니고(자르기는 누르는 즉시 적용된다), 빈 상태로 골라두면 "골랐는데
 * 아무 일도 없다"가 된다. 그건 변형 탭에 남긴다.
 */
export const TOOL_GROUPS: ToolKind[] = ['mask', 'draw']

const BY_ID = new Map(EDITOR_TOOLS.map((t) => [t.id, t]))
const BY_SHORTCUT = new Map(EDITOR_TOOLS.map((t) => [t.shortcut, t]))

export function toolById(id: string | undefined): EditorTool | undefined {
  return id ? BY_ID.get(id) : undefined
}

/**
 * 키 입력 → 도구. 조합키가 눌렸으면 무시한다 (Ctrl+S 같은 것을 가로채면 안 된다).
 * 대소문자는 구분하지 않는다.
 */
export function toolByKey(key: string, modifiers: { ctrl?: boolean; alt?: boolean; meta?: boolean } = {}) {
  if (modifiers.ctrl || modifiers.alt || modifiers.meta) return undefined
  if (!key || key.length !== 1) return undefined
  return BY_SHORTCUT.get(key.toUpperCase())
}

export function toolsOfKind(kind: ToolKind): EditorTool[] {
  return EDITOR_TOOLS.filter((t) => t.kind === kind)
}
