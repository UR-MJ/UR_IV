<template>
  <div v-if="data.source === 'comfyui' || data.raw_prompt || data.raw_workflow || data.metadata_warnings?.length" class="comfy-metadata">
    <p v-if="data.source === 'comfyui'" class="note">ComfyUI · 연결에서 확인된 문장과 기본 설정만 읽습니다. T2I 전송은 원본 워크플로 전체를 복원하지 않습니다.</p>
    <p v-for="warning in data.metadata_warnings || []" :key="warning" class="warning" role="status">{{ warning }}</p>
    <details v-if="data.prompt_candidates?.length && (data.metadata_ambiguous || data.prompt_candidates.length > 1)">
      <summary>샘플러·인코더별 프롬프트 후보 ({{ data.prompt_candidates.length }})</summary>
      <section v-for="candidate in data.prompt_candidates" :key="candidate.node_id" class="candidate">
        <strong>{{ candidate.sampler }} · 노드 {{ candidate.node_id }}</strong>
        <template v-for="role in (['positive', 'negative'] as const)" :key="role">
          <div v-for="(part, index) in candidate[`${role}_parts`] || []" :key="`${role}-${index}`" class="prompt-part">
            <div class="part-heading"><span>{{ role === 'positive' ? 'Prompt' : 'Negative' }} · {{ part.label }}</span><button type="button" :disabled="!part.text" @click="copy(part.text)">이 문장 복사</button></div>
            <pre>{{ part.text || '(빈 문장)' }}</pre>
          </div>
          <p v-if="!candidate[`${role}_known`]" class="note">{{ role === 'positive' ? 'Prompt' : 'Negative' }}: 여러 분기이거나 지원하지 않는 연결이어서 자동 적용하지 않습니다.</p>
        </template>
      </section>
    </details>
    <details v-if="data.raw_prompt">
      <summary>원본 ComfyUI prompt JSON</summary>
      <button type="button" class="raw-copy" @click="copy(data.raw_prompt)">원본 prompt JSON 복사</button>
      <pre>{{ data.raw_prompt }}</pre>
    </details>
    <details v-if="data.raw_workflow">
      <summary>원본 ComfyUI workflow JSON</summary>
      <button type="button" class="raw-copy" @click="copy(data.raw_workflow)">원본 workflow JSON 복사</button>
      <pre>{{ data.raw_workflow }}</pre>
    </details>
  </div>
</template>

<script setup lang="ts">
import { copyTextToClipboard } from '../utils/clipboard'
import { requestAction } from '../stores/widgetStore.js'
interface PromptPart { node_id: string; label: string; text: string }
interface Candidate { node_id: string; sampler: string; positive_parts: PromptPart[]; negative_parts: PromptPart[]; positive_known: boolean; negative_known: boolean }
defineProps<{ data: { source?: string; raw_prompt?: string; raw_workflow?: string; metadata_warnings?: string[]; prompt_candidates?: Candidate[]; metadata_ambiguous?: boolean } }>()
async function copy(text: string) {
  const ok = await copyTextToClipboard(text)
  requestAction('show_toast', { type: ok ? 'success' : 'error', msg: ok ? '복사되었습니다' : '클립보드에 복사하지 못했습니다' })
}
</script>

<style scoped>
.comfy-metadata { margin: 12px 0; font-size: 12px; min-width: 0; }
.note, .warning { line-height: 1.6; overflow-wrap: anywhere; }
.note { color: var(--text-muted); }
.warning { color: var(--state-alert-fg, #cf8730); }
details { margin: 10px 0; border-top: 1px solid var(--border); padding-top: 8px; }
summary { cursor: pointer; color: var(--text-secondary); }
.candidate { padding: 10px 0; border-bottom: 1px solid var(--border); }
.candidate strong { color: var(--text-primary); }
.prompt-part { margin: 10px 0; }
.part-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px; color: var(--text-muted); }
pre { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; max-height: 240px; overflow-y: auto; color: var(--text-secondary); background: var(--bg-secondary); padding: 8px; border-radius: 6px; font-size: 11px; }
button { border: 1px solid var(--border); border-radius: 6px; background: var(--bg-button); color: var(--text-secondary); font-size: 11px; padding: 5px 8px; cursor: pointer; }
.raw-copy { margin-top: 8px; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
</style>
