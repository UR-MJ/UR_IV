import { describe, expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import ComfyMetadataDetails from './ComfyMetadataDetails.vue'

vi.mock('../utils/clipboard', () => ({ copyTextToClipboard: vi.fn() }))
vi.mock('../stores/widgetStore.js', () => ({ requestAction: vi.fn() }))

describe('read-only Comfy metadata details', () => {
  it('shows ambiguous encoder candidates with exact-text copy controls', async () => {
    const html = await renderToString(createSSRApp(ComfyMetadataDetails, { data: {
      source: 'comfyui', metadata_ambiguous: true, metadata_warnings: ['서로 다른 인코더 문장'],
      prompt_candidates: [{ node_id: '7', sampler: 'KSampler', positive_known: false, negative_known: true,
        positive_parts: [{ node_id: '1', label: 'CLIP-G', text: 'global scene' }, { node_id: '2', label: 'CLIP-L', text: 'local detail' }], negative_parts: [] }],
    } }))
    expect(html).toContain('global scene')
    expect(html).toContain('local detail')
    expect(html).toContain('이 문장 복사')
    expect(html).toContain('자동 적용하지 않습니다')
  })

  it('renders raw graph data as escaped text, never as executable markup', async () => {
    const html = await renderToString(createSSRApp(ComfyMetadataDetails, { data: {
      source: 'comfyui', raw_prompt: '{"text":"<script>alert(1)</script>"}', raw_workflow: '{"nodes":[]}',
    } }))
    expect(html).toContain('원본 ComfyUI prompt JSON')
    expect(html).toContain('원본 ComfyUI workflow JSON')
    expect(html).toContain('&lt;script&gt;')
    expect(html).not.toContain('<script>')
  })
})
