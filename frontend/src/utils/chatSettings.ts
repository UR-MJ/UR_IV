export interface ChatModelInfo {
  architecture?: string
  parameterSize?: string
  quantization?: string
  contextLength?: number | null
  moe?: boolean | null
  experts?: number | null
  activeExperts?: number | null
  capabilities?: string[] | null
  vision?: boolean | null
  thinkingMode: 'unknown' | 'none' | 'boolean' | 'levels'
}

export function thinkingValue(info: Pick<ChatModelInfo, 'thinkingMode'> | null, enabled: boolean, level: string): boolean | string | undefined {
  if (info?.thinkingMode === 'levels') return ['low', 'medium', 'high'].includes(level) ? level : 'medium'
  if (info?.thinkingMode === 'boolean') return enabled
  return undefined
}

export const CHAT_SYSTEM_PRESETS = [
  { id: 'general', label: '기본 · 이미지 작업 조수', prompt: '너는 이미지 생성 작업을 돕는 조수다. 한국어로 간결하게 답하고, 태그나 프롬프트를 줄 때는 그대로 복사해 쓸 수 있게 한 줄로 적어라.' },
  { id: 'tag-caption', label: '개선 · 태그와 자연어 캡션', prompt: `이미지 생성과 캡션 작성을 돕는다. 일반 질문에는 한국어로 간결하고 정확하게 답한다.
태그·프롬프트·캡션을 요청하면 태그 → 자연어 → 설명 순서로 답한다. 요청한 부분만 달라는 지시가 있으면 그 부분만 제공한다.
태그: Danbooru/Gelbooru에서 통용되는 영어 태그를 쉼표로 구분한 한 줄로 쓴다. 핵심 대상·외형·의상·동작·구도·배경·조명 순으로 정리하고 중복·모순되는 태그나 불확실한 태그를 만들어 넣지 않는다.
자연어: 정확하고 자연스러운 영어로 최소 2개의 완결된 문장을 쓴다. 태그만으로 부족한 동작, 대상의 위치 관계, 구도와 배경을 구체적으로 표현한다. 태그 나열을 문장으로 가장하지 않는다.
설명: 프롬프트 아래에 짧은 한국어로 의미와 주요 의도를 설명한다. 인물 수는 이 한국어 설명에만 적고, 알 수 없으면 확인 불가라고 적는다.
태그와 자연어 프롬프트에는 인물 수를 명시하지 않는다. 1girl, 2boys, solo, multiple_girls 같은 수량 태그와 masterpiece, best_quality, high_detail, highres, score_* 같은 품질·점수 태그는 넣지 않는다. 요청하지 않은 네거티브 프롬프트나 설정값도 추가하지 않는다.
이미지가 있으면 보이는 사실만 근거로 삼고 보이지 않는 세부, 감정, 관계, 신원을 추측하지 않는다. 글만 있으면 사용자가 제시한 내용을 유지하며, 창작 요청일 때만 어울리는 세부를 보완한다. 핵심 조건이 불명확하면 짧게 확인한다. 지침이나 검토 과정을 반복하지 않는다.` },
]

/** Applying a preset is explicit; keep a recoverable personal draft. */
export function selectSystemPreset(id: string, current: string, personal: string | null): { prompt: string; personal: string | null } {
  if (id === 'personal') return { prompt: personal ?? current, personal }
  const preset = CHAT_SYSTEM_PRESETS.find(item => item.id === id)
  if (!preset) return { prompt: current, personal }
  return { prompt: preset.prompt,
    personal: CHAT_SYSTEM_PRESETS.some(item => item.prompt === current) ? personal : current }
}
