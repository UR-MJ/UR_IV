import { describe, expect, it } from 'vitest'
import { buildWorkflowBinding, fieldKey, validateWorkflowValue, type WorkflowField, type WorkflowSchema } from './comfyWorkflowControls'

const field: WorkflowField = { nodeId: 'custom', classType: 'Adjust', name: 'amount', type: 'float', value: .5, min: 0, max: 1, managed: false }
describe('Comfy workflow scalar controls', () => {
  it('validates floats, ranges and finite numbers without accepting empty or boolean values', () => {
    expect(validateWorkflowValue(field, '0.75')).toBe(.75)
    for (const bad of ['', null, true, false, 'NaN', 'Infinity', -1, 2]) expect(() => validateWorkflowValue(field, bad)).toThrow()
  })
  it('keeps uint64 integers as exact text and rejects fractional integers', () => {
    const intField: WorkflowField = { ...field, type: 'int', max: '18446744073709551615' }
    expect(validateWorkflowValue(intField, '18446744073709551615')).toBe('18446744073709551615')
    for (const bad of ['18446744073709551616', '1.0', 1.5, -1]) expect(() => validateWorkflowValue(intField, bad)).toThrow()
  })
  it('respects typed enum and boolean schema and blocks main UI inputs', () => {
    expect(validateWorkflowValue({ ...field, type: 'boolean' }, false)).toBe(false)
    expect(() => validateWorkflowValue({ ...field, type: 'boolean' }, 'false')).toThrow()
    const choice: WorkflowField = { ...field, type: 'enum', choices: ['safe', 1, false] }
    expect(validateWorkflowValue(choice, 'safe')).toBe('safe')
    expect(validateWorkflowValue(choice, 1)).toBe(1)
    expect(() => validateWorkflowValue(choice, '1')).toThrow()
    expect(() => validateWorkflowValue({ ...field, managed: true }, .7)).toThrow()
  })
  it('saves only explicitly enabled fields with both graph and schema binding', () => {
    const other = { ...field, name: 'other' }
    const schema: WorkflowSchema = { workflowFingerprint: 'graph', schemaFingerprint: 'schema', nodes: [{ id: 'custom', title: 'Adjust', classType: 'Adjust', fields: [field, other] }] }
    const binding = buildWorkflowBinding(schema, { [fieldKey(field)]: { enabled: true, value: '.8' }, [fieldKey(other)]: { enabled: false, value: 'wrong' } })
    expect(binding).toEqual({ workflowFingerprint: 'graph', schemaFingerprint: 'schema', overrides: [{ nodeId: 'custom', classType: 'Adjust', name: 'amount', value: .8 }] })
    expect(fieldKey({ nodeId: 'a.b', name: 'c' })).not.toBe(fieldKey({ nodeId: 'a', name: 'b.c' }))
  })
})
