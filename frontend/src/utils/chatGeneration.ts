export interface ChatArtifact {
  kind: 'image' | 'animated' | 'video' | 'audio'
  path: string
  filename?: string
  mime?: string
}
export interface GenerationRequest {
  mode: 'auto' | 'chat' | 'image' | 'video'
  family: 'current' | 'krea2'
  duration: number
  denoise: number
  hadImage?: boolean
}
export interface GenerationState {
  kind: 'image' | 'video'
  phase: string
  progress?: number
  message?: string
}
interface MediaMessage {
  requestId?: string
  pending?: boolean
  content: string
  error?: string
  generation?: GenerationState
  artifacts?: ChatArtifact[]
}

export function applyGenerationEvent(message: MediaMessage, event: Record<string, any>): boolean {
  if (!message.pending || !message.requestId || event.id !== message.requestId) return false
  const kind = event.kind === 'video' ? 'video' : 'image'
  const progress = Number(event.progress)
  message.generation = {
    kind, phase: String(event.phase || 'preparing'), message: String(event.message || ''),
    progress: Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : message.generation?.progress,
  }
  if (event.done) {
    message.pending = false
    delete message.requestId
    message.content = event.stopped ? '생성을 중지했습니다.'
      : String(event.message || (event.ok ? `${kind === 'video' ? '영상' : '이미지'} 생성 완료` : '생성에 실패했습니다.'))
    message.error = event.stopped || event.ok ? '' : String(event.error || '생성에 실패했습니다')
    message.artifacts = event.ok && !event.stopped && Array.isArray(event.artifacts)
      ? event.artifacts.filter((a: any) => a && ['image', 'animated', 'video', 'audio'].includes(a.kind)
        && typeof a.path === 'string' && a.path && !/^(https?|data|blob|javascript|file):/i.test(a.path))
        .map((a: any) => ({ kind: a.kind, path: a.path, filename: a.filename, mime: a.mime })) : []
  }
  return true
}

export function artifactMarkdown(artifact: ChatArtifact): string {
  const url = 'file:///' + encodeURI(artifact.path.replace(/\\/g, '/'))
    .replace(/[#?()]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase())
  return `[${artifact.kind === 'video' ? '생성 영상' : artifact.kind === 'audio' ? '생성 오디오' : '생성 이미지'}](<${url}>)`
}
