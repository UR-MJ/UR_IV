<template>
  <div class="chat-view" @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop">
    <!-- 대화 목록 — GemmaStudio 처럼 왼쪽 열. 최근 것이 위. -->
    <aside class="chat-threads">
      <div class="ct-head">
        <button class="ct-new" type="button" @click="newThread" title="새 대화 (Ctrl+N)">
          <Icon name="plus" size="15" /> 새 대화
        </button>
        <div class="ct-search">
          <Icon name="search" size="13" />
          <input v-model="search" placeholder="대화 찾기" spellcheck="false" />
        </div>
      </div>
      <div class="ct-list">
        <div v-if="!visibleThreads.length" class="ct-empty">{{ search ? '맞는 대화가 없습니다' : '아직 대화가 없습니다' }}</div>
        <button v-for="t in visibleThreads" :key="t.id" type="button" class="ct-item"
          :class="{ on: t.id === activeId }" @click="activeId = t.id" :title="t.title || '새 대화'">
          <Icon name="message" size="14" />
          <span class="ct-title">{{ t.title || '새 대화' }}</span>
          <span class="ct-del" role="button" title="대화 삭제" @click.stop="deleteThread(t.id)"><Icon name="close" size="12" /></span>
        </button>
      </div>
      <div class="ct-foot">
        <span class="ct-foot-label">모델</span>
        <CustomSelect v-if="models.length" v-model="model" :options="models" placeholder="모델 선택..." @update:modelValue="saveModel" />
        <span v-else class="ct-foot-none" :title="url">Ollama 모델 없음 — Settings › AI 어시스트</span>
      </div>
    </aside>

    <!-- 대화 -->
    <section class="chat-main">
      <header class="cm-head">
        <div class="cm-title-wrap">
          <input v-if="renaming" ref="renameRef" v-model="renameDraft" class="cm-rename" @keydown.enter="finishRename" @keydown.esc="renaming = false" @blur="finishRename" />
          <h2 v-else class="cm-title" @dblclick="startRename" :title="'더블클릭해서 이름 바꾸기'">{{ active?.title || '새 대화' }}</h2>
          <span class="cm-sub">{{ model || '모델 없음' }}<template v-if="active?.messages.length"> · {{ active.messages.length }}개 메시지</template></span>
        </div>
        <div class="cm-tools">
          <span class="cm-status" :class="{ busy: !!busyId, off: !models.length }">
            <span class="dot"></span>{{ busyId ? '생각 중' : (models.length ? '준비됨' : '연결 안 됨') }}
          </span>
          <button class="cm-tool" type="button" title="대화 설정 — 지침 · 답변 최대 토큰 · 문맥 창 · 온도" @click="showSystem = !showSystem" :class="{ on: showSystem }"><Icon name="settings" size="14" /></button>
          <button class="cm-tool" type="button" title="Markdown 으로 내보내기" :disabled="!active?.messages.length" @click="exportMarkdown"><Icon name="download" size="14" /></button>
          <button class="cm-tool" type="button" title="대화 내용 비우기" :disabled="!active?.messages.length" @click="clearMessages"><Icon name="eraser" size="14" /></button>
        </div>
      </header>

      <div v-if="showSystem" class="cm-system">
        <label>지침 — 모든 대화의 맨 앞에 붙습니다</label>
        <textarea v-model="systemPrompt" rows="3" spellcheck="false" @change="saveSystemPrompt"></textarea>
        <div class="cm-opts">
          <label class="cm-opt">
            <span>답변 최대 토큰</span>
            <select v-model.number="chatOptions.numPredict" @change="saveChatOptions">
              <option :value="-1">제한 없음</option>
              <option v-for="n in PREDICT_CHOICES" :key="n" :value="n">{{ n.toLocaleString() }}</option>
            </select>
          </label>
          <label class="cm-opt">
            <span>문맥 창 (num_ctx)</span>
            <select v-model.number="chatOptions.numCtx" @change="saveChatOptions">
              <option :value="0">모델 기본</option>
              <option v-for="n in CTX_CHOICES" :key="n" :value="n">{{ n.toLocaleString() }}</option>
            </select>
          </label>
          <label class="cm-opt cm-opt-range">
            <span>온도 {{ chatOptions.temperature.toFixed(1) }}</span>
            <input type="range" min="0" max="2" step="0.1" v-model.number="chatOptions.temperature" @change="saveChatOptions" />
          </label>
          <span class="cm-opt-hint">답이 중간에 끊기면 답변 최대 토큰과 문맥 창을 같이 늘리세요. 문맥 창이 클수록 VRAM 을 더 씁니다 (이미지 한 장이 수백 토큰).</span>
        </div>
      </div>

      <div class="cm-scroll" ref="scrollRef" @scroll="onScroll" @wheel="onWheel">
        <div class="cm-col">
          <!-- 빈 상태 -->
          <div v-if="!active || !active.messages.length" class="cm-hero">
            <div class="cm-hero-mark"><Icon name="sparkles" size="22" /></div>
            <h3>무엇을 도와드릴까요?</h3>
            <p>로컬 Ollama 모델과 대화합니다. 이미지를 끌어 놓거나 붙여 넣으면 모델이 보고 답합니다<span v-if="model"> — {{ model }}</span>.</p>
            <div class="cm-suggest">
              <button v-for="s in SUGGESTIONS" :key="s" type="button" @click="draft = s; focusComposer()">{{ s }}</button>
            </div>
          </div>

          <!-- 메시지 — 말풍선이 아니라 한 열. GemmaStudio 와 같은 이유: 긴 답이 읽힌다. -->
          <article v-for="m in active?.messages || []" :key="m.id" class="msg" :class="[m.role, { pending: m.pending, error: !!m.error }]">
            <div class="msg-avatar" aria-hidden="true">{{ m.role === 'user' ? '나' : 'AI' }}</div>
            <div class="msg-body">
              <div class="msg-role">{{ m.role === 'user' ? '나' : (m.model || model || 'AI') }}<span v-if="m.evalCount" class="msg-meta"> · {{ m.evalCount.toLocaleString() }} 토큰<template v-if="m.durationMs"> · {{ (m.durationMs / 1000).toFixed(1) }}초</template></span></div>
              <div v-if="m.images?.length" class="msg-images">
                <img v-for="(src, i) in m.images" :key="i" :src="imageSrc(src)" alt="첨부 이미지" @load="onMediaLoad" />
              </div>
              <details v-if="m.thinking" class="msg-think" :open="!!m.pending">
                <summary><Icon name="bulb" size="12" /> {{ m.pending && !m.content ? '생각하는 중…' : `생각 (${m.thinking.length}자)` }}</summary>
                <pre>{{ m.thinking }}</pre>
              </details>
              <div v-if="m.role === 'assistant'" class="msg-content md" v-html="renderMarkdown(m.content)"></div>
              <div v-else class="msg-content plain">{{ m.content }}</div>
              <div v-if="m.pending && !m.content && !m.thinking" class="msg-thinking"><span></span><span></span><span></span></div>
              <div v-if="m.error" class="msg-error">{{ m.error }}</div>
              <div v-else-if="m.doneReason === 'length' && !m.pending" class="msg-cut">답변 최대 토큰에 걸려 잘렸습니다 — 톱니(설정)에서 늘릴 수 있습니다</div>
              <div class="msg-actions" v-if="!m.pending">
                <button type="button" title="복사" @click="copyText(m.content)"><Icon name="clipboard" size="13" /></button>
                <button v-if="m.role === 'assistant' && isLast(m)" type="button" title="다시 생성" @click="regenerate"><Icon name="refresh" size="13" /></button>
              </div>
            </div>
          </article>
        </div>
      </div>

      <!-- 컴포저 — 스크롤 영역 *아래*, 흐름 안에 둔다. 위에 띄우면 마지막 메시지가 그 뒤로 숨는다. -->
      <div class="cm-bottom" ref="bottomRef">
        <button v-if="!followBottom" class="cm-jump" type="button" @click="scrollToBottom(true)" title="맨 아래로"><Icon name="arrow-down" size="14" /></button>
        <div class="cm-composer" :class="{ drag: dragOver }">
        <div v-if="attachments.length" class="cmp-attach">
          <div v-for="(a, i) in attachments" :key="i" class="cmp-thumb">
            <img :src="imageSrc(a)" alt="" />
            <button type="button" title="첨부 제거" @click="attachments.splice(i, 1)"><Icon name="close" size="11" /></button>
          </div>
        </div>
        <textarea ref="composerRef" v-model="draft" class="cmp-input" rows="1" spellcheck="false"
          :placeholder="models.length ? '메시지를 입력하세요 — Enter 보내기 · Shift+Enter 줄바꿈' : 'Ollama 에 연결되지 않았습니다'"
          @keydown="onComposerKey" @input="autoGrow" @paste="onPaste"></textarea>
        <div class="cmp-bar">
          <span class="cmp-hint"><Icon name="image" size="13" /> 이미지·텍스트 파일을 끌어 놓거나 붙여 넣기 · 히스토리 카드도 됩니다</span>
          <span class="cmp-spacer"></span>
          <button type="button" class="cmp-think" :class="{ on: deepThink }" @click="toggleThink"
            :title="deepThink ? '깊은 추론 켜짐 — 답하기 전에 생각합니다 (느리고, 생각이 접힌 블록으로 보입니다)' : '깊은 추론 꺼짐 — 바로 답합니다 (빠름)'">
            <Icon name="bulb" size="13" /> 깊은 추론
          </button>
          <button v-if="busyId" type="button" class="cmp-send stop" title="중지 (Esc)" @click="stop"><Icon name="stop" size="14" /></button>
          <button v-else type="button" class="cmp-send" title="보내기 (Enter)" :disabled="!canSend" @click="send"><Icon name="arrow-up" size="15" /></button>
        </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 대화 탭 — 로컬 Ollama 와 스트리밍으로 대화한다.
 *
 * GemmaStudio 의 골격을 따랐다: 왼쪽에 대화 목록, 가운데에 **말풍선이 아닌 한 열**의
 * 메시지, 아래에 카드형 컴포저. 다른 점 하나 — 여기서는 이미지를 **모델에게 픽셀로**
 * 보낸다(GemmaStudio 는 OCR 글자만 보냈다). 그래서 Settings 의 추천 모델이 전부
 * 비전 모델이다.
 *
 * 상태는 Python 파일(config/chat_threads.json)에 저장한다 — localStorage 는 이미지가
 * 붙는 순간 5MB 를 넘겨 조용히 실패한다. 브리지: chat_load/chat_save/chat_send/chat_stop,
 * 시그널 chatThreads/chatToken/chatDone (tests/test_bridge_contract.py 가 이름을 지킨다).
 */
import { computed, nextTick, onActivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { getBackend, onBackendEvent } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'
import { mediaUrl } from '../utils/media.js'
import { renderMarkdown } from '../utils/chatMarkdown'
import CustomSelect from '../components/CustomSelect.vue'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  images?: string[]
  model?: string
  thinking?: string
  evalCount?: number
  durationMs?: number
  doneReason?: string
  pending?: boolean
  requestId?: string
  error?: string
}
interface ChatThread {
  id: string
  title: string
  model: string
  createdAt: number
  updatedAt: number
  messages: ChatMessage[]
}

const SUGGESTIONS = [
  '이 프롬프트를 더 자연스럽게 다듬어 줘',
  '첨부한 이미지를 자세히 설명해 줘',
  '이 장면에 어울리는 Danbooru 태그를 추천해 줘',
]
const DEFAULT_SYSTEM = '너는 이미지 생성 작업을 돕는 조수다. 한국어로 간결하게 답하고, 태그나 프롬프트를 줄 때는 그대로 복사해 쓸 수 있게 한 줄로 적어라.'
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8)

// ── 상태 ──
const threads = ref<ChatThread[]>([])
const activeId = ref('')
const search = ref('')
const draft = ref('')
const attachments = ref<string[]>([])
const models = ref<string[]>([])
const model = ref(localStorage.getItem('ollamaModel') || '')
const url = ref(localStorage.getItem('ollamaUrl') || 'http://localhost:11434')
const systemPrompt = ref(localStorage.getItem('chatSystemPrompt') ?? DEFAULT_SYSTEM)
const showSystem = ref(false)
// 생성 옵션 — Ollama 기본 문맥 창(4096)은 지침 + 이미지 + 24턴 기록이면 금방 찬다. 답이 잘리면 여기서 늘린다.
interface ChatOptions { temperature: number; numPredict: number; numCtx: number }
const DEFAULT_OPTIONS: ChatOptions = { temperature: 0.7, numPredict: -1, numCtx: 8192 }
const PREDICT_CHOICES = [512, 1024, 2048, 4096, 8192, 16384]
const CTX_CHOICES = [4096, 8192, 16384, 32768, 65536, 131072]
function loadChatOptions(): ChatOptions {
  const o = { ...DEFAULT_OPTIONS }
  try {
    const raw = JSON.parse(localStorage.getItem('chatOptions.v1') || 'null')
    if (raw && typeof raw === 'object') {
      // 목록에 없는 값(구버전·손으로 고친 것)은 select 가 빈칸으로 보인다 — 기본값으로 되돌린다
      if (typeof raw.temperature === 'number' && raw.temperature >= 0 && raw.temperature <= 2) o.temperature = raw.temperature
      if (raw.numPredict === -1 || PREDICT_CHOICES.includes(raw.numPredict)) o.numPredict = raw.numPredict
      if (raw.numCtx === 0 || CTX_CHOICES.includes(raw.numCtx)) o.numCtx = raw.numCtx
    }
  } catch {}
  return o
}
const chatOptions = ref<ChatOptions>(loadChatOptions())
function saveChatOptions() { localStorage.setItem('chatOptions.v1', JSON.stringify(chatOptions.value)) }
function ollamaOptions(): Record<string, number> {
  const o: Record<string, number> = { temperature: chatOptions.value.temperature }
  // '제한 없음' 도 -1 로 명시한다 — 모델파일이 num_predict 를 박아 둔 모델이 있다
  o.num_predict = chatOptions.value.numPredict > 0 ? chatOptions.value.numPredict : -1
  if (chatOptions.value.numCtx > 0) o.num_ctx = chatOptions.value.numCtx
  return o
}
// 깊은 추론 — Gemma 4 / Qwen3.x 같은 thinking 모델은 기본으로 생각부터 하느라 첫 글자가 1분 뒤에 온다.
// GemmaStudio 처럼 빠른 답변이 기본, 원할 때만 켠다. 켜면 생각이 접힌 블록으로 같이 흐른다.
const deepThink = ref(localStorage.getItem('chatThink') === '1')
function toggleThink() { deepThink.value = !deepThink.value; localStorage.setItem('chatThink', deepThink.value ? '1' : '0') }
const busyId = ref('')
const dragOver = ref(false)
const followBottom = ref(true)
const renaming = ref(false)
const renameDraft = ref('')
const renameRef = ref<HTMLInputElement | null>(null)
const composerRef = ref<HTMLTextAreaElement | null>(null)
const scrollRef = ref<HTMLElement | null>(null)
const bottomRef = ref<HTMLElement | null>(null)

const active = computed(() => threads.value.find((t) => t.id === activeId.value) || null)
const visibleThreads = computed(() => {
  const q = search.value.trim().toLowerCase()
  const list = [...threads.value].sort((a, b) => b.updatedAt - a.updatedAt)
  return q ? list.filter((t) => (t.title || '').toLowerCase().includes(q)) : list
})
const canSend = computed(() => models.value.length > 0 && !!model.value && (draft.value.trim().length > 0 || attachments.value.length > 0))

// ── 저장 — 파일로, 지연해서 ──
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    const snapshot = threads.value.map((t) => ({
      ...t,
      messages: t.messages.filter((m) => !m.pending).map(({ pending, requestId, ...rest }) => rest),
    }))
    requestAction('chat_save', { threads: snapshot })
  }, 600)
}
watch(threads, scheduleSave, { deep: true })

// ── 대화 목록 ──
function newThread() {
  // 이미 빈 대화가 있으면 그걸 쓴다 — 빈 것이 쌓이지 않게
  const empty = threads.value.find((t) => !t.messages.length)
  if (empty) { activeId.value = empty.id; focusComposer(); return }
  const t: ChatThread = { id: uid(), title: '', model: model.value, createdAt: Date.now(), updatedAt: Date.now(), messages: [] }
  threads.value.unshift(t)
  activeId.value = t.id
  focusComposer()
}
function deleteThread(id: string) {
  const t = threads.value.find((x) => x.id === id)
  if (t && t.messages.length && !confirm(`"${t.title || '새 대화'}" 를 삭제할까요?`)) return
  if (busyId.value && t?.messages.some((m) => m.requestId === busyId.value)) stop()
  threads.value = threads.value.filter((x) => x.id !== id)
  if (activeId.value === id) activeId.value = threads.value[0]?.id || ''
  if (!threads.value.length) newThread()
}
function clearMessages() {
  if (!active.value) return
  if (!confirm('이 대화의 메시지를 모두 비울까요?')) return
  // 다른 대화에서 흐르는 응답은 건드리지 않는다
  if (busyId.value && active.value.messages.some((m) => m.requestId === busyId.value)) stop()
  active.value.messages = []
  active.value.title = ''
  active.value.updatedAt = Date.now()
}
function exportMarkdown() {
  const t = active.value
  if (!t || !t.messages.length) return
  const title = t.title || '새 대화'
  const parts = [`# ${title}`, '', `_${new Date(t.createdAt).toLocaleString()} · ${t.model || model.value || ''}_`, '']
  for (const m of t.messages) {
    if (m.pending) continue   // 아직 흐르는 답은 반쪽이다
    parts.push(`## ${m.role === 'user' ? '나' : (m.model || 'AI')}`, '')
    if (m.images?.length) parts.push(`(이미지 ${m.images.length}장 첨부)`, '')
    parts.push(m.content || '', '')
  }
  requestAction('chat_export', { title, markdown: parts.join('\n') })
}
function startRename() {
  if (!active.value) return
  renameDraft.value = active.value.title || ''
  renaming.value = true
  nextTick(() => renameRef.value?.select())
}
function finishRename() {
  if (!renaming.value) return
  renaming.value = false
  if (active.value) { active.value.title = renameDraft.value.trim().slice(0, 80); active.value.updatedAt = Date.now() }
}

// ── 보내기 · 받기 ──
function send() {
  if (!canSend.value || !active.value) return
  const thread = active.value
  const text = draft.value.trim()
  const user: ChatMessage = { id: uid(), role: 'user', content: text, createdAt: Date.now() }
  if (attachments.value.length) user.images = [...attachments.value]
  thread.messages.push(user)
  if (!thread.title) thread.title = (text || '이미지').replace(/\s+/g, ' ').slice(0, 36)
  draft.value = ''
  attachments.value = []
  nextTick(autoGrow)   // v-model 이 DOM 을 비운 *뒤에* 재야 컴포저가 한 줄로 돌아온다
  ask(thread)
}
function ask(thread: ChatThread) {
  const requestId = uid()
  const assistant: ChatMessage = { id: uid(), role: 'assistant', content: '', createdAt: Date.now(), pending: true, requestId, model: model.value }
  thread.messages.push(assistant)
  thread.model = model.value
  thread.updatedAt = Date.now()
  busyId.value = requestId
  followBottom.value = true
  nextTick(() => scrollToBottom(false))
  requestAction('chat_send', {
    id: requestId,
    url: url.value,
    model: model.value,
    system: systemPrompt.value,
    think: deepThink.value,
    options: ollamaOptions(),
    messages: thread.messages
      .filter((m) => !m.pending && !m.error)
      .map((m) => ({ role: m.role, content: m.content, images: m.images })),
  })
}
function stop() {
  if (!busyId.value) return
  requestAction('chat_stop', { id: busyId.value })
}
function regenerate() {
  const thread = active.value
  if (!thread || busyId.value) return
  const last = thread.messages[thread.messages.length - 1]
  if (last?.role === 'assistant') thread.messages.pop()
  ask(thread)
}
function findPending(requestId: string): ChatMessage | null {
  for (const t of threads.value) {
    const m = t.messages.find((x) => x.requestId === requestId)
    if (m) return m
  }
  return null
}
function onToken(json: string) {
  try {
    const { id, text, thinking } = JSON.parse(json)
    const m = findPending(id)
    if (!m) return
    if (thinking) m.thinking = (m.thinking || '') + thinking
    if (!text) { if (thinking && followBottom.value) nextTick(() => scrollToBottom(false)); return }
    m.content += text
    if (followBottom.value) nextTick(() => scrollToBottom(false))
  } catch {}
}
function onDone(json: string) {
  try {
    const d = JSON.parse(json)
    const m = findPending(d.id)
    if (m) {
      if (d.ok && typeof d.content === 'string' && d.content.length >= m.content.length) m.content = d.content
      if (!d.ok) m.error = d.error || '응답을 받지 못했습니다'
      else if (d.stopped) m.error = m.content ? '' : '중지됨'
      if (typeof d.evalCount === 'number') m.evalCount = d.evalCount
      if (typeof d.durationMs === 'number') m.durationMs = d.durationMs
      if (typeof d.doneReason === 'string' && d.doneReason) m.doneReason = d.doneReason
      m.pending = false
      delete m.requestId
      const t = threads.value.find((x) => x.messages.includes(m))
      if (t) t.updatedAt = Date.now()
      // 끝나면 액션 줄·메타가 생기고 생각 블록이 접혀 높이가 바뀐다 — 보고 있던 맨 아래를 지킨다
      if (followBottom.value) nextTick(() => scrollToBottom(false))
    }
    if (busyId.value === d.id) busyId.value = ''
  } catch { busyId.value = '' }
}
function isLast(m: ChatMessage) {
  const msgs = active.value?.messages || []
  return msgs[msgs.length - 1] === m
}

// ── 첨부 — 이미지는 픽셀로 보낸다. 큰 사진은 1024px 로 줄여 base64 (모델·저장 둘 다 가볍게) ──
async function addImageFile(file: File) {
  if (!file.type.startsWith('image/')) return
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = reject; r.readAsDataURL(file)
  })
  attachments.value.push(await downscale(dataUrl))
}
function downscale(dataUrl: string, max = 1024): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height))
      if (scale >= 1) { resolve(dataUrl); return }
      const c = document.createElement('canvas')
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale)
      c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
      resolve(c.toDataURL('image/jpeg', 0.9))
    }
    img.onerror = () => resolve(dataUrl)
    img.src = dataUrl
  })
}
const TEXT_EXT = /\.(txt|md|json|ya?ml|toml|csv|py|js|ts|vue|html?|css|xml|ini|cfg|log|sh|ps1|bat)$/i
async function addTextFile(file: File) {
  // 텍스트·코드는 본문에 펜스로 넣는다 — 모델이 파일을 "읽는" 가장 확실한 길
  const text = (await file.text()).slice(0, 100_000)
  const lang = (file.name.match(/\.(\w+)$/)?.[1] || '').toLowerCase()
  draft.value = (draft.value ? draft.value + '\n\n' : '') + `파일 \`${file.name}\`:\n\`\`\`${lang}\n${text}\n\`\`\`\n`
  nextTick(autoGrow)
}
function onDrop(e: DragEvent) {
  dragOver.value = false
  const files = [...(e.dataTransfer?.files || [])]
  if (files.length) {
    files.slice(0, 8).forEach((f) => {
      if (f.type.startsWith('image/')) addImageFile(f)
      else if (f.type.startsWith('text/') || TEXT_EXT.test(f.name)) addTextFile(f)
    })
    return
  }
  // 히스토리·갤러리 카드는 경로 텍스트로 온다 — Python 이 파일을 읽어 base64 로 넣는다
  const path = e.dataTransfer?.getData('text/plain') || ''
  if (path && /[\\/]/.test(path) && attachments.value.length < 8) attachments.value.push(path.replace(/\\/g, '/'))
}
function onPaste(e: ClipboardEvent) {
  const items = [...(e.clipboardData?.items || [])].filter((it) => it.type.startsWith('image/'))
  if (!items.length) return
  e.preventDefault()
  items.forEach((it) => { const f = it.getAsFile(); if (f) addImageFile(f) })
}
function imageSrc(v: string) { return v.startsWith('data:') ? v : mediaUrl(v) }

// ── 입력 ──
function onComposerKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send() }
  else if (e.key === 'Escape' && busyId.value) { e.preventDefault(); stop() }
}
function autoGrow() {
  const el = composerRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}
function focusComposer() { nextTick(() => composerRef.value?.focus()) }
function onGlobalKey(e: KeyboardEvent) {
  if (e.ctrlKey && (e.key === 'n' || e.key === 'N') && document.querySelector('.chat-view')) { e.preventDefault(); newThread() }
}

// ── 스크롤 ──
let _settleUntil = 0   // 부드러운 점프 중에는 중간 scroll 이벤트가 followBottom 을 끄지 않게
function onScroll() {
  const el = scrollRef.value
  if (!el || performance.now() < _settleUntil) return
  followBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}
function onWheel(e: WheelEvent) {
  // 스트리밍 중 위로 굴리면 즉시 놓아준다 — scroll 이벤트보다 먼저 토큰이 와서 도로 끌려가지 않게
  if (e.deltaY < 0) followBottom.value = false
}
function onMediaLoad() {
  // 이미지가 늦게 떠서 내용이 자라면 맨 아래를 지킨다
  if (followBottom.value) scrollToBottom(false)
}
function scrollToBottom(smooth: boolean) {
  const el = scrollRef.value
  if (!el) return
  if (smooth) _settleUntil = performance.now() + 700
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  followBottom.value = true
}
watch(activeId, () => { followBottom.value = true; nextTick(() => scrollToBottom(false)) })
// 스크롤 영역이 줄어들면(컴포저가 자람 · 설정 패널 열림 · 창 세로 축소) 맨 아래를 보고 있었으면 계속 맨 아래.
// 위에서 줄어들 땐 scrollTop 이 그대로라 scroll 이벤트도 안 오므로, 스크롤 영역 자체를 관찰해야 한다.
let _bottomObserver: ResizeObserver | null = null
onMounted(() => {
  if (typeof ResizeObserver === 'undefined' || !bottomRef.value) return
  _bottomObserver = new ResizeObserver(() => { if (followBottom.value) scrollToBottom(false) })
  _bottomObserver.observe(bottomRef.value)
  if (scrollRef.value) _bottomObserver.observe(scrollRef.value)
})
onUnmounted(() => { _bottomObserver?.disconnect(); _bottomObserver = null })

// ── 모델 · 설정 ──
function saveModel() {
  localStorage.setItem('ollamaModel', model.value)
  requestAction('save_ui_prefs', { ollamaModel: model.value, ollamaUrl: url.value })
}
function saveSystemPrompt() { localStorage.setItem('chatSystemPrompt', systemPrompt.value) }
async function requestModels() {
  try {
    const bk: any = await getBackend()
    url.value = localStorage.getItem('ollamaUrl') || url.value
    if (bk?.requestOllamaModels) bk.requestOllamaModels(url.value)
  } catch {}
}
function onModels(json: string) {
  try {
    const p = JSON.parse(json)
    const list = Array.isArray(p) ? p : p.models
    if (!Array.isArray(list)) return
    models.value = list
    if (list.length && !list.includes(model.value)) {
      const base = (s: string) => (s || '').split(':')[0].toLowerCase()
      model.value = list.find((m: string) => base(m) === base(model.value)) || list[0]
    }
  } catch {}
}
async function copyText(text: string) {
  // QWebEngine 은 비보안 컨텍스트라 navigator.clipboard 가 막힐 수 있다 — execCommand 로 받친다
  try { await navigator.clipboard.writeText(text) }
  catch {
    const ta = document.createElement('textarea')
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } finally { ta.remove() }
  }
  requestAction('show_toast', { type: 'success', msg: '복사됨' })
}

const unsubs: Array<() => void> = []
onMounted(() => {
  unsubs.push(onBackendEvent('chatThreads', (json: string) => {
    try {
      const list = JSON.parse(json)
      if (Array.isArray(list)) threads.value = list
    } catch {}
    // GemmaStudio 처럼 열 때마다 빈 새 대화에서 시작한다 — 기존 기록은 목록에 남는다
    if (!activeId.value) newThread()
  }))
  unsubs.push(onBackendEvent('chatToken', onToken))
  unsubs.push(onBackendEvent('chatDone', onDone))
  unsubs.push(onBackendEvent('ollamaModelsReady', onModels))
  window.addEventListener('keydown', onGlobalKey)
  requestAction('chat_load')
  requestModels()
  // 백엔드가 목록을 안 돌려줘도(웹 모드·개발 서버) 빈 대화 하나는 있어야 입력이 된다
  setTimeout(() => { if (!threads.value.length) newThread() }, 1500)
})
onActivated(() => { requestModels(); focusComposer() })
onUnmounted(() => {
  unsubs.forEach((u) => { try { u() } catch {} })
  window.removeEventListener('keydown', onGlobalKey)
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
})
</script>

<style scoped>
.chat-view { height: 100%; display: flex; background: var(--bg-primary); overflow: hidden; }

/* ── 대화 목록 ── */
.chat-threads { width: 268px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); background: var(--bg-secondary); }
.ct-head { padding: 12px 12px 8px; display: flex; flex-direction: column; gap: 8px; }
.ct-new { height: 34px; display: flex; align-items: center; justify-content: center; gap: 6px; border-radius: var(--radius-base); border: 1px solid var(--border); background: var(--bg-button); color: var(--text-primary); font-size: var(--fs-body); font-weight: var(--fw-medium); cursor: pointer; }
.ct-new:hover { border-color: var(--accent); color: var(--accent); }
.ct-search { display: flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border-radius: var(--radius-base); background: var(--bg-input); border: 1px solid var(--border); color: var(--text-muted); }
.ct-search input { flex: 1; min-width: 0; background: transparent; border: 0; outline: 0; color: var(--text-primary); font-size: var(--fs-meta); }
.ct-list { flex: 1; min-height: 0; overflow-y: auto; padding: 0 8px 8px; display: flex; flex-direction: column; gap: 2px; }
.ct-empty { padding: 18px 8px; color: var(--text-muted); font-size: var(--fs-meta); text-align: center; }
.ct-item { position: relative; display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 8px; border: 0; border-radius: var(--radius-base); background: transparent; color: var(--text-secondary); font-size: var(--fs-body); text-align: left; cursor: pointer; }
.ct-item:hover { background: var(--bg-button); color: var(--text-primary); }
.ct-item.on { background: var(--accent-dim); color: var(--text-primary); }
.ct-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ct-del { display: none; width: 20px; height: 20px; align-items: center; justify-content: center; border-radius: 4px; color: var(--text-muted); }
.ct-item:hover .ct-del { display: flex; }
.ct-del:hover { background: rgba(248,113,113,.12); color: var(--state-alert-fg); }
.ct-foot { padding: 10px 12px 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
.ct-foot-label { font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--text-muted); }
.ct-foot-none { font-size: var(--fs-label); color: var(--state-alert-fg); }

/* ── 대화 본문 ── */
.chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; }
/* 오른쪽 여백은 알림 종 자리다 (style.css --notif-gutter) */
.cm-head { height: 52px; flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 0 var(--notif-gutter) 0 20px; border-bottom: 1px solid var(--border); }
.cm-title-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.cm-title { margin: 0; font-size: 14px; font-weight: var(--fw-bold); color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: text; }
.cm-rename { font: inherit; font-size: 14px; font-weight: var(--fw-bold); color: var(--text-primary); background: var(--bg-input); border: 1px solid var(--accent); border-radius: 4px; padding: 2px 6px; outline: 0; }
.cm-sub { font-size: var(--fs-label); color: var(--text-muted); }
.cm-tools { display: flex; align-items: center; gap: 6px; }
.cm-status { display: flex; align-items: center; gap: 6px; height: 24px; padding: 0 10px; border-radius: var(--radius-pill); background: var(--bg-button); color: var(--text-secondary); font-size: var(--fs-label); }
.cm-status .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--state-ok-fg); }
.cm-status.busy .dot { background: var(--accent); animation: chat-pulse 1s ease-in-out infinite; }
.cm-status.off .dot { background: var(--state-alert-fg); }
@keyframes chat-pulse { 50% { opacity: .35; } }
.cm-tool { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: var(--radius-base); background: var(--bg-button); color: var(--text-secondary); cursor: pointer; }
.cm-tool:hover { color: var(--text-primary); border-color: var(--text-muted); }
.cm-tool.on { color: var(--accent); border-color: var(--accent); }
.cm-tool:disabled { opacity: .35; cursor: default; }
.cm-system { padding: 10px 20px; border-bottom: 1px solid var(--border); background: var(--bg-secondary); display: flex; flex-direction: column; gap: 6px; max-height: 45vh; overflow-y: auto; flex-shrink: 0; }
.cm-system label { font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--text-muted); }
.cm-opts { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 14px; padding-top: 2px; }
.cm-opt { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-label); color: var(--text-muted); }
.cm-opt select { height: 28px; padding: 0 8px; border-radius: var(--radius-base); border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); font: inherit; font-size: var(--fs-meta); outline: 0; }
.cm-opt-range input { width: 140px; accent-color: var(--accent); }
.cm-opt-hint { flex-basis: 100%; font-size: var(--fs-label); color: var(--text-muted); }
.msg-meta { font-weight: normal; }
.msg-cut { font-size: var(--fs-meta); color: var(--state-alert-fg); }
.cm-system textarea { width: 100%; resize: vertical; padding: 8px 10px; border-radius: var(--radius-base); border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); font: inherit; font-size: var(--fs-meta); line-height: 1.5; outline: 0; user-select: text; }

.cm-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 20px 24px; }
.cm-col { width: min(790px, 100%); margin: 0 auto; display: flex; flex-direction: column; gap: 22px; }

.cm-hero { margin: 60px auto 0; max-width: 560px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.cm-hero-mark { width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: 12px; background: var(--accent-dim); color: var(--accent); }
.cm-hero h3 { margin: 4px 0 0; font-size: 18px; font-weight: var(--fw-bold); color: var(--text-primary); }
.cm-hero p { margin: 0; color: var(--text-muted); font-size: var(--fs-body); line-height: 1.6; }
.cm-suggest { margin-top: 10px; display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.cm-suggest button { padding: 8px 12px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--bg-card); color: var(--text-secondary); font-size: var(--fs-meta); cursor: pointer; }
.cm-suggest button:hover { border-color: var(--accent); color: var(--text-primary); }

.msg { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 12px; }
.msg-avatar { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 8px; font-size: 11px; font-weight: var(--fw-bold); background: var(--bg-button); color: var(--text-secondary); }
.msg.assistant .msg-avatar { background: var(--accent-fill); color: var(--on-accent); }
.msg-body { min-width: 0; display: flex; flex-direction: column; gap: 6px; position: relative; }
.msg-role { font-size: var(--fs-label); font-weight: var(--fw-medium); color: var(--text-muted); }
.msg-images { display: flex; flex-wrap: wrap; gap: 6px; }
.msg-images img { max-width: 220px; max-height: 220px; border-radius: 8px; border: 1px solid var(--border); object-fit: cover; }
.msg-content { color: var(--text-primary); font-size: var(--fs-body); line-height: 1.65; user-select: text; }
.msg-content.plain { white-space: pre-wrap; word-break: break-word; }
.msg-error { font-size: var(--fs-meta); color: var(--state-alert-fg); }
.msg-thinking { display: flex; gap: 4px; padding: 4px 0; }
.msg-thinking span { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); animation: chat-dots 1.2s ease-in-out infinite; }
.msg-thinking span:nth-child(2) { animation-delay: .2s; } .msg-thinking span:nth-child(3) { animation-delay: .4s; }
@keyframes chat-dots { 0%, 80%, 100% { opacity: .25; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
.msg-actions { display: flex; gap: 4px; opacity: 0; transition: opacity .15s; }
.msg:hover .msg-actions { opacity: 1; }
.msg-actions button { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-button); color: var(--text-muted); cursor: pointer; }
.msg-actions button:hover { color: var(--text-primary); border-color: var(--text-muted); }

/* 마크다운 — v-html 로 들어오는 태그들 (chatMarkdown.ts 가 만드는 것만) */
.md :deep(p) { margin: 0 0 8px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(h1), .md :deep(h2), .md :deep(h3) { margin: 10px 0 6px; font-weight: var(--fw-bold); color: var(--text-primary); }
.md :deep(h1) { font-size: 16px; } .md :deep(h2) { font-size: 15px; } .md :deep(h3) { font-size: 14px; }
.md :deep(ul), .md :deep(ol) { margin: 0 0 8px; padding-left: 22px; }
.md :deep(li) { margin: 2px 0; }
.md :deep(blockquote) { margin: 0 0 8px; padding: 4px 12px; border-left: 3px solid var(--accent); color: var(--text-secondary); }
.md :deep(hr) { border: 0; border-top: 1px solid var(--border); margin: 10px 0; }
.md :deep(code) { padding: 1px 5px; border-radius: 4px; background: var(--bg-input); font-family: Consolas, 'JetBrains Mono', monospace; font-size: 12px; }
.md :deep(pre) { position: relative; margin: 0 0 8px; padding: 10px 12px; border-radius: 8px; background: var(--bg-input); border: 1px solid var(--border); overflow-x: auto; }
.md :deep(pre code) { padding: 0; background: transparent; white-space: pre; }
.md :deep(pre[data-lang]:not([data-lang=""]))::before { content: attr(data-lang); position: absolute; top: 6px; right: 10px; font-size: var(--fs-label); color: var(--text-muted); }
.md :deep(a) { color: var(--accent); text-decoration: underline; }
.md :deep(strong) { font-weight: var(--fw-bold); }

.cm-jump { position: absolute; right: 24px; top: -40px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: 50%; border: 1px solid var(--border); background: var(--bg-card); color: var(--text-secondary); cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.3); }
.cm-jump:hover { color: var(--accent); border-color: var(--accent); }

/* ── 컴포저 — 스크롤 영역 아래, 흐름 안의 카드 (메시지를 가리지 않는다) ── */
.cm-bottom { position: relative; flex-shrink: 0; display: flex; justify-content: center; padding: 6px 20px 16px; }
.cm-composer { position: relative; width: min(790px, 100%); display: flex; flex-direction: column; gap: 6px; padding: 10px 12px 8px; border-radius: 14px; background: var(--bg-card); border: 1px solid var(--border-strong); box-shadow: 0 10px 40px rgba(0,0,0,.35); }
.cm-composer.drag { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.cmp-attach { display: flex; flex-wrap: wrap; gap: 6px; }
.cmp-thumb { position: relative; width: 56px; height: 56px; }
.cmp-thumb img { width: 100%; height: 100%; object-fit: cover; border-radius: 6px; border: 1px solid var(--border); }
.cmp-thumb button { position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; border-radius: 50%; border: 1px solid var(--border-strong); background: var(--bg-card); color: var(--text-secondary); cursor: pointer; }
.cmp-input { width: 100%; min-height: 40px; max-height: 180px; resize: none; padding: 8px 4px; background: transparent; border: 0; outline: 0; color: var(--text-primary); font: inherit; font-size: var(--fs-body); line-height: 1.5; user-select: text; }
.cmp-bar { display: flex; align-items: center; gap: 8px; }
.cmp-hint { display: flex; align-items: center; gap: 5px; color: var(--text-muted); font-size: var(--fs-label); }
.cmp-spacer { flex: 1; }
.cmp-think { display: flex; align-items: center; gap: 5px; height: 28px; padding: 0 10px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: var(--fs-label); cursor: pointer; }
.cmp-think:hover { color: var(--text-primary); border-color: var(--text-muted); }
.cmp-think.on { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.msg-think { border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); font-size: var(--fs-meta); }
.msg-think summary { display: flex; align-items: center; gap: 6px; padding: 6px 10px; color: var(--text-muted); cursor: pointer; user-select: none; list-style: none; }
.msg-think summary::-webkit-details-marker { display: none; }
.msg-think[open] summary { border-bottom: 1px solid var(--border); }
.msg-think pre { margin: 0; padding: 8px 10px; max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word; color: var(--text-secondary); font: inherit; font-size: var(--fs-meta); line-height: 1.5; user-select: text; }
.cmp-send { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 50%; border: 0; background: var(--accent-fill); color: var(--on-accent); cursor: pointer; }
.cmp-send:disabled { opacity: .3; cursor: default; }
.cmp-send.stop { background: var(--state-alert); color: var(--state-alert-fg); }

@media (max-width: 1100px) {
  .chat-threads { width: 220px; }
}
</style>
