export interface XYZAxisDefinition {
  id: string
  label: string
  type: 'integer' | 'number' | 'choice' | 'replace'
  min?: number
  max?: number
  step?: number
  choices?: string[]
}

export function acceptCapabilityEvent(requestId: string, event: any): boolean {
  return event?.invalidated === true || (!!requestId && event?.requestId === requestId)
}

export function parseAxisValues(text: string, type: string): string[] {
  if (!text.trim()) return []
  if (type === 'number' || type === 'integer') {
    const number = '(-?\\d+(?:\\.\\d+)?)'
    const range = text.trim().match(new RegExp(`^${number}\\s*-\\s*${number}\\s*:\\s*${number}$`))
    if (range) {
      const start = Number(range[1]), end = Number(range[2]), step = Number(range[3])
      if (!Number.isFinite(step) || step <= 0 || end < start) throw new Error('범위 간격은 0보다 크고 끝값은 시작값 이상이어야 합니다.')
      const count = Math.floor((end - start) / step + 1e-8) + 1
      if (count > 256) throw new Error('XYZ 값은 축마다 최대 256개입니다.')
      return Array.from({ length: count }, (_, i) => String(Number((start + i * step).toFixed(8))))
    }
  }
  const values: string[] = []
  let quoted = false, value = ''
  for (let i = 0; i < text.length; i++) {
    const character = text[i]
    if (character === '"') {
      if (quoted && text[i + 1] === '"') { value += '"'; i++ }
      else quoted = !quoted
    } else if (character === ',' && !quoted) { values.push(value.trim()); value = '' }
    else value += character
  }
  if (quoted) throw new Error('값의 따옴표를 닫아 주세요.')
  values.push(value.trim())
  if (values.length > 256) throw new Error('XYZ 값은 축마다 최대 256개입니다.')
  return type === 'replace' ? values : values.filter(Boolean)
}

export function quoteAxisValue(value: string): string {
  return /[,"\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}
