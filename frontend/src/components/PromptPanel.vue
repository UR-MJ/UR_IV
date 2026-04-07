<template>
  <div class="prompt-panel">
    <!-- 1. FINAL OUTPUT PROMPT (최상단, 가장 중요) -->
    <div class="glass-card highlight">
      <div class="card-header">
        FINAL OUTPUT PROMPT
        <span class="token-info">{{ tokenCount }} tokens</span>
      </div>
      <textarea ref="totalPromptRef" v-model="widgets.total_prompt"
        class="total-prompt auto-grow" placeholder="인물수, 캐릭터, 작품, 작가, 선행, 메인, 후행 순서로 종합됩니다"
        @input="autoGrow($event.target)"></textarea>
      <div class="neg-section">
        <label class="danger-label">NEGATIVE</label>
        <textarea ref="negRef" v-model="widgets.negative_prompt"
          class="neg-prompt auto-grow" placeholder="Negative prompt..."
          @input="autoGrow($event.target)"></textarea>
      </div>
    </div>

    <!-- 2. CHARACTER & MODEL -->
    <div class="glass-card">
      <div class="card-header">CHARACTER & MODEL</div>
      <div class="input-group">
        <label>Char Count</label>
        <input type="text" v-model="widgets.char_count" placeholder="e.g. 1girl, 2girls..." />
      </div>
      <div class="input-group">
        <label>Character</label>
        <div class="row">
          <input type="text" v-model="widgets.character" placeholder="e.g. hatsune miku" />
          <button class="small-btn" @click="requestAction('open_character_preset')">PRESET</button>
        </div>
      </div>
      <div class="input-group">
        <label>Copyright</label>
        <input type="text" v-model="widgets.copyright" placeholder="Copyright / Series..." />
      </div>
      <div class="input-group">
        <div class="row label-row">
          <label>Artist</label>
          <button class="lock-btn" :class="{ locked: artistLocked }" @click="toggleArtistLock" title="잠금: 랜덤 프롬프트로 변경되지 않음">
            {{ artistLocked ? '🔒' : '🔓' }}
          </button>
        </div>
        <textarea ref="artistRef" v-model="widgets.artist" class="auto-grow" placeholder="Artist tags..."
          @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Checkpoint</label>
        <select v-model="widgets.model">
          <option v-for="m in modelItems" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
    </div>

    <!-- 3. PROMPT BLOCKS -->
    <details class="glass-card" open>
      <summary class="card-header">PROMPT BLOCKS</summary>
      <div class="input-group">
        <label>Prefix</label>
        <textarea ref="prefixRef" v-model="widgets.prefix_prompt" class="auto-grow" placeholder="선행 프롬프트..."
          @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Main Tags</label>
        <textarea ref="mainRef" v-model="widgets.main_prompt" class="auto-grow" placeholder="메인 태그..."
          @input="autoGrow($event.target)" rows="3"></textarea>
      </div>
      <div class="input-group">
        <label>Suffix</label>
        <textarea ref="suffixRef" v-model="widgets.suffix_prompt" class="auto-grow" placeholder="후행 프롬프트..."
          @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Exclude (Local)</label>
        <textarea ref="excludeRef" v-model="widgets.exclude_local" class="auto-grow" placeholder="제외 태그..."
          @input="autoGrow($event.target)"></textarea>
      </div>
    </details>

    <!-- 4. PARAMETERS -->
    <details class="glass-card">
      <summary class="card-header">PARAMETERS</summary>
      <div class="input-group">
        <label>Resolution</label>
        <div class="res-row">
          <input type="number" v-model="widgets.width" />
          <span>×</span>
          <input type="number" v-model="widgets.height" />
          <button class="icon-btn" @click="requestAction('swap_resolution')">↔</button>
        </div>
      </div>
      <div class="grid-2">
        <div class="input-group">
          <label>Sampler</label>
          <select v-model="widgets.sampler">
            <option v-for="s in samplerItems" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="input-group">
          <label>Scheduler</label>
          <select v-model="widgets.scheduler">
            <option v-for="s in schedulerItems" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </div>
      <div class="grid-2">
        <div class="input-group">
          <label>Steps</label>
          <input type="number" v-model="widgets.steps" min="1" max="150" />
        </div>
        <div class="input-group">
          <label>CFG Scale</label>
          <input type="number" v-model="widgets.cfg" step="0.5" />
        </div>
      </div>
      <div class="input-group">
        <label>Seed</label>
        <div class="row">
          <input type="text" v-model="widgets.seed" />
          <button class="icon-btn" @click="widgets.seed = '-1'">🎲</button>
        </div>
      </div>
    </details>

    <!-- 5. 확장 패널 열기 버튼 -->
    <button class="expand-btn" @click="$emit('toggle-extend')">
      ⚙ ADVANCED (ADetailer / Hires / LoRA)
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useWidgetStore, requestAction } from '../stores/widgetStore.js'

const emit = defineEmits(['toggle-extend'])

const store = useWidgetStore()
const widgets = store.widgets

const artistLocked = ref(false)
const totalPromptRef = ref(null)
const negRef = ref(null)
const artistRef = ref(null)
const prefixRef = ref(null)
const mainRef = ref(null)
const suffixRef = ref(null)
const excludeRef = ref(null)

const modelItems = computed(() => store.getProperty('model_combo', 'items') || [])
const samplerItems = computed(() => store.getProperty('sampler_combo', 'items') || [])
const schedulerItems = computed(() => store.getProperty('scheduler_combo', 'items') || [])
const tokenCount = computed(() => {
  const t = widgets.total_prompt
  if (!t) return 0
  return t.split(',').filter(s => s.trim()).length
})

function toggleArtistLock() {
  artistLocked.value = !artistLocked.value
  requestAction('set_artist_locked', { locked: artistLocked.value })
}

function autoGrow(el) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

// 초기 로드 시 모든 textarea 자동 크기 조절
function growAll() {
  nextTick(() => {
    ;[totalPromptRef, negRef, artistRef, prefixRef, mainRef, suffixRef, excludeRef].forEach(r => {
      if (r.value) autoGrow(r.value)
    })
  })
}

onMounted(() => {
  // 초기 값 로드 후 autoGrow
  setTimeout(growAll, 500)
  setTimeout(growAll, 1500) // 배치 업데이트 후 재조정
})

// 위젯 값 변경 시 자동 크기
watch(() => widgets.total_prompt, () => nextTick(() => { if (totalPromptRef.value) autoGrow(totalPromptRef.value) }))
watch(() => widgets.negative_prompt, () => nextTick(() => { if (negRef.value) autoGrow(negRef.value) }))
watch(() => widgets.artist, () => nextTick(() => { if (artistRef.value) autoGrow(artistRef.value) }))
watch(() => widgets.main_prompt, () => nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }))
</script>

<style scoped>
.prompt-panel { display: flex; flex-direction: column; gap: 12px; }

.glass-card {
  background: rgba(20, 20, 20, 0.6);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 14px;
  transition: var(--transition);
}
.glass-card.highlight { border-color: var(--accent-dim); background: rgba(250, 204, 21, 0.02); }
.glass-card:hover { border-color: #333; }

.card-header {
  font-size: 10px; font-weight: 800; color: var(--text-muted);
  letter-spacing: 1.5px; margin-bottom: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: space-between;
}

summary { list-style: none; outline: none; }
summary::-webkit-details-marker { display: none; }

.input-group { margin-bottom: 10px; }
.mt-4 { margin-top: 4px; }
.row { display: flex; gap: 6px; }
.label-row { align-items: center; margin-bottom: 4px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

.small-btn {
  padding: 0 12px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-secondary);
  font-size: 10px; font-weight: 700; cursor: pointer; white-space: nowrap;
}

.icon-btn {
  width: 36px; height: 36px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-primary); cursor: pointer; flex-shrink: 0;
}

.lock-btn {
  background: none; border: none; cursor: pointer; font-size: 14px; padding: 0 4px;
  opacity: 0.5; transition: var(--transition);
}
.lock-btn.locked { opacity: 1; }

.total-prompt {
  min-height: 60px; font-family: 'Consolas', monospace; font-size: 12px;
  line-height: 1.5; color: var(--accent); border-color: var(--accent-dim);
}

.neg-section { margin-top: 8px; }
.danger-label { color: #f87171; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
.neg-prompt { min-height: 30px; color: #f87171; border-color: rgba(248,113,113,0.2); }

.auto-grow { resize: none; overflow: hidden; min-height: 32px; }

.token-info { font-size: 9px; color: var(--text-muted); }

.res-row { display: flex; align-items: center; gap: 8px; }
.res-row input { text-align: center; }

.expand-btn {
  width: 100%; padding: 10px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-card); color: var(--text-secondary);
  font-size: 11px; font-weight: 700; cursor: pointer; letter-spacing: 0.5px;
  transition: var(--transition);
}
.expand-btn:hover { border-color: var(--accent-dim); color: var(--accent); }

label.danger { color: #f87171; }
input[type="number"] { -moz-appearance: textfield; }
input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }
</style>
