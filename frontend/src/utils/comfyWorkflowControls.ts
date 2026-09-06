export interface WorkflowField {
  nodeId: string; classType: string; name: string
  type: 'int' | 'float' | 'boolean' | 'string' | 'enum'
  value: string | number | boolean
  choices?: (string | number | boolean)[]
  min?: number | string; max?: number | string; step?: number | string
  multiline?: boolean; managed: boolean
}
export interface WorkflowSchema {
  workflowFingerprint: string; schemaFingerprint: string
  nodes: { id: string; classType: string; title: string; fields: WorkflowField[] }[]
}
export interface WorkflowOverride { nodeId: string; classType: string; name: string; value: string | number | boolean }
export interface WorkflowBinding {
  workflowFingerprint: string; schemaFingerprint: string; overrides: WorkflowOverride[]
}
export const fieldKey = (field: Pick<WorkflowField, 'nodeId' | 'name'>) => JSON.stringify([field.nodeId, field.name])

export function validateWorkflowValue(field: WorkflowField, value: unknown): string | number | boolean {
  const fail = (message: string): never => { throw new Error(`${field.nodeId}.${field.name}: ${message}`) }
  if (field.managed) return fail('앱의 기본 생성 설정에서 변경하세요.')
  if (field.type === 'boolean') return typeof value === 'boolean' ? value : fail('체크 상태를 확인하세요.')
  if (field.type === 'string') return typeof value === 'string' && value.length <= 262144 ? value : fail('텍스트 형식과 길이를 확인하세요.')
  if (field.type === 'enum') return field.choices?.some(choice => typeof choice === typeof value && choice === value)
    ? value as string | number | boolean : fail('현재 서버의 목록에서 선택하세요.')
  if (typeof value === 'boolean' || value === null || String(value).trim() === '') return fail('숫자를 입력하세요.')
  if (field.type === 'int') {
    const text = String(value).trim()
    if (!/^[+-]?\d+$/.test(text)) return fail('정수를 입력하세요.')
    const integer = BigInt(text)
    if (field.min !== undefined && integer < BigInt(field.min) || field.max !== undefined && integer > BigInt(field.max)) return fail('허용 범위를 확인하세요.')
    return text // uint64 must not round-trip through Number.
  }
  const number = Number(value)
  if (!Number.isFinite(number) || field.min !== undefined && number < Number(field.min) || field.max !== undefined && number > Number(field.max)) return fail('유효한 숫자와 허용 범위를 확인하세요.')
  return number
}

export function buildWorkflowBinding(schema: WorkflowSchema, entries: Record<string, { enabled: boolean; value: unknown }>): WorkflowBinding {
  const overrides: WorkflowOverride[] = []
  for (const node of schema.nodes) for (const field of node.fields) {
    const entry = entries[fieldKey(field)]
    if (entry?.enabled) overrides.push({ nodeId: field.nodeId, classType: field.classType, name: field.name, value: validateWorkflowValue(field, entry.value) })
  }
  return { workflowFingerprint: schema.workflowFingerprint, schemaFingerprint: schema.schemaFingerprint, overrides }
}
