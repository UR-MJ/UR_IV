<template>
  <div class="prompt-panel">
    <!-- 1. FINAL OUTPUT PROMPT -->
    <div class="glass-card highlight">
      <div class="card-header">
        FINAL OUTPUT PROMPT
        <span class="token-info">{{ tokenCount }} tokens</span>
      </div>
      <TagBlockField v-if="tagBlockMode" :model-value="widgets.total_prompt_display" :color-fn="blockColorClass" placeholder=""
        @update:model-value="onTotalBlockChange" @open-wildcard="(n) => emit('open-wildcard', n)" />
      <textarea v-else ref="totalPromptRef" v-model="widgets.total_prompt_display"
        class="total-prompt auto-grow" placeholder="최종 프롬프트" @input="autoGrow($event.target)"></textarea>
      <div class="prompt-actions">
        <button class="optimize-btn" @click="optimizePrompt">🧹 OPTIMIZE</button>
        <button class="optimize-btn" @click="toggleSeparate" title="표정/배경/포즈/사물/메타 태그를 분류해서 제거하거나 추출">🏷 분류</button>
        <span class="opt-result" v-if="optResult">{{ optResult }}</span>
      </div>
      <!-- 🧹 OPTIMIZE before/after 미리보기 → [적용] 클릭 시 반영 -->
      <div class="opt-preview" v-if="optPreview">
        <div class="opt-prev-head">
          <span>🧹 OPTIMIZE 미리보기</span>
          <span class="opt-prev-stat">중복 {{ optPreview.removed }}개 제거 · {{ optPreview.tagCount }}개 태그</span>
        </div>
        <div class="opt-prev-cols">
          <div class="opt-prev-col"><label>BEFORE</label><div class="opt-prev-text before">{{ optPreview.before }}</div></div>
          <div class="opt-prev-col"><label>AFTER</label><div class="opt-prev-text after">{{ optPreview.after }}</div></div>
        </div>
        <div class="opt-prev-conf" v-if="optPreview.conflicts.length">⚠ 충돌: <span v-for="c in optPreview.conflicts" :key="c.group">{{ c.group }}({{ c.tags.join('/') }}) </span></div>
        <div class="opt-prev-btns">
          <button class="opt-apply" @click="applyOptimize">✓ 적용</button>
          <button class="opt-cancel" @click="cancelOptimize">취소</button>
        </div>
      </div>

      <!-- ⑤ 카테고리 분리 토글 -->
      <div class="separate-panel" v-if="showSeparate">
        <div class="sep-chips">
          <button v-for="c in SEP_CATS" :key="c.key" class="sep-chip" :class="{ on: sepCats[c.key] }"
            @click="sepCats[c.key] = !sepCats[c.key]">
            {{ c.label }}<span class="sep-n" v-if="sepCounts[c.key]">{{ sepCounts[c.key] }}</span>
          </button>
        </div>
        <div class="sep-actions">
          <button class="sep-act remove" @click="applySeparate('remove')">🗑 선택 제거</button>
          <button class="sep-act extract" @click="applySeparate('extract')">✂ 선택만 남기기</button>
          <span class="sep-hint" v-if="sepResult">{{ sepResult }}</span>
        </div>
      </div>
      <div class="conflicts" v-if="promptConflicts.length > 0">
        <div v-for="c in promptConflicts" :key="c.group" class="conflict-item">⚠ {{ c.group }}: {{ c.tags.join(', ') }}</div>
      </div>
      <details class="neg-section">
        <summary class="danger-label neg-toggle">
          NEGATIVE ▾
          <button class="ai-btn neg-ai" @click.prevent.stop="runSmartNegative()" :disabled="ollamaLoading" title="AI 네거티브 자동 생성">🤖</button>
        </summary>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.neg_prompt_text" :color-fn="() => 'neg'" class="neg" placeholder="네거티브 추가..." />
        <textarea v-else ref="negRef" v-model="widgets.neg_prompt_text" class="neg-prompt auto-grow" placeholder="Negative prompt..." @input="autoGrow($event.target)"></textarea>
      </details>
    </div>

    <!-- 2. CHARACTER & MODEL -->
    <div class="glass-card">
      <div class="card-header">CHARACTER & MODEL</div>
      <div class="input-group">
        <label>Char Count</label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.char_count_input" :color-fn="() => 'bc-count'" placeholder="인물수..." />
        <input v-else type="text" v-model="widgets.char_count_input" placeholder="e.g. 1girl, 2girls..." />
      </div>
      <div class="input-group autocomplete-wrap">
        <div class="row label-row">
          <label>Character <span v-if="sectionTokens.character" class="tk-badge" :class="tokenBadgeClass(sectionTokens.character)">{{ sectionTokens.character }}t</span></label>
          <button class="small-btn" @click="openCharPresetModal(); loadCharTags()">PRESET</button>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.character_input" :color-fn="() => 'bc-count'" placeholder="캐릭터..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <input v-else type="text" v-model="widgets.character_input" placeholder="e.g. hatsune miku"
          @input="onFieldInput($event, 'character_input')" @keydown="onFieldKey($event, 'character_input')" @blur="loadCharTags" />
        <div class="char-insight" v-if="charInsight.tags.length > 0">
          <div class="insight-header">
            <span class="insight-label">📖 Official Tags</span>
            <button class="insight-apply" @click="applyOfficialTags">APPLY ALL</button>
          </div>
          <div class="insight-tags">
            <button v-for="tag in charInsight.tags" :key="tag" class="char-tag-chip" @click="insertCharTag(tag)">{{ tag.replace(/_/g, ' ') }}</button>
          </div>
        </div>
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'character_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'character_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group autocomplete-wrap">
        <label>Copyright <span v-if="sectionTokens.copyright" class="tk-badge" :class="tokenBadgeClass(sectionTokens.copyright)">{{ sectionTokens.copyright }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.copyright_input" :color-fn="() => ''" placeholder="작품..." />
        <input v-else type="text" v-model="widgets.copyright_input" placeholder="Copyright / Series..."
          @input="onFieldInput($event, 'copyright_input')" @keydown="onFieldKey($event, 'copyright_input')" />
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'copyright_input' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptFieldSuggestion(tag, 'copyright_input')">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <div class="row label-row">
          <label>Artist <span v-if="sectionTokens.artist" class="tk-badge" :class="tokenBadgeClass(sectionTokens.artist)">{{ sectionTokens.artist }}t</span></label>
          <button class="lock-btn" :class="{ locked: artistLocked }" @click="toggleArtistLock">{{ artistLocked ? '🔒' : '🔓' }}</button>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.artist_input" :color-fn="() => ''" placeholder="작가..." />
        <textarea v-else ref="artistRef" v-model="widgets.artist_input" class="auto-grow" placeholder="Artist tags..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div v-if="showGenerationFamily" class="input-group generation-family">
        <label>Generation Engine</label>
        <CustomSelect v-model="widgets.generation_family_combo" :options="generationFamilyItems" />
        <span class="engine-hint">T2I와 I2I에 공통 적용됩니다.</span>
      </div>
      <div v-if="!isKrea2Generation" class="input-group">
        <label>Checkpoint</label>
        <CustomSelect v-model="widgets.model_combo" :options="modelItems" placeholder="Select model..." />
      </div>
      <div v-if="!isKrea2Generation" class="input-group">
        <label>VAE <span class="hint">(ANIMA 등 외부 VAE)</span></label>
        <CustomSelect v-model="widgets.vae_main_combo" :options="vaeItems" placeholder="(체크포인트 기본 사용)" />
      </div>
      <div v-if="!isKrea2Generation" class="input-group">
        <label>Text Encoder <span class="hint">(드롭다운에서 추가 · 칩 클릭으로 제거)</span></label>
        <CustomSelect :modelValue="''" @update:modelValue="addTeFile"
          :options="teUnselectedItems"
          :placeholder="teItems.length === 0 ? '(text_encoder 폴더 비어있음)' : '+ TE 파일 추가...'" />
        <div v-if="teSelectedList.length > 0" class="te-chips">
          <button v-for="f in teSelectedList" :key="f" type="button"
            class="te-chip active" @click="removeTeFile(f)">
            {{ f }} <span class="te-chip-x">×</span>
          </button>
        </div>
      </div>
      <div v-else class="krea-engine-note">
        <strong>KREA 2 TURBO</strong>
        <span>전용 UNET · Qwen3-VL · VAE 워크플로를 실행하며 ComfyUI 백엔드가 필요합니다.</span>
        <span>T2I 전환 시 8 steps / CFG 1을 설정합니다. Sampler는 Euler 권장, Scheduler는 Simple 고정입니다.</span>
        <span v-if="isI2IRoute">I2I Identity Edit에는 Identity Edit · TextFusion LoRA와 Krea2 Edit custom node가 추가로 필요합니다.</span>
        <span>일반 Checkpoint · VAE · TE · LoRA Stack · Forge 확장과 Negative는 이 모드에서 적용되지 않습니다.</span>
      </div>
    </div>

    <!-- 3. PROMPT BLOCKS -->
    <details class="glass-card" open>
      <summary class="card-header">
        <span>PROMPT BLOCKS</span>
        <span class="undo-btns" @click.stop>
          <button class="undo-btn" :disabled="undoStack.length < 2" @click="performUndo" title="실행 취소 (Ctrl+Z)">↶</button>
          <button class="undo-btn" :disabled="redoStack.length === 0" @click="performRedo" title="다시 실행 (Ctrl+Y)">↷</button>
        </span>
      </summary>
      <div class="input-group autocomplete-wrap">
        <div class="row label-row">
          <label>Main Tags <span v-if="sectionTokens.main" class="tk-badge" :class="tokenBadgeClass(sectionTokens.main)">{{ sectionTokens.main }}t</span></label>
          <div class="ai-btns">
            <!-- 태그형 출력 AI -->
            <div class="ai-menu-wrap">
              <button class="ai-btn ai-menu-btn" @click.stop="toggleAiMenu('tag')" :disabled="ollamaLoading" title="태그를 만드는 AI">✨ 태그 AI ▾</button>
              <div class="ai-menu" v-if="aiMenu === 'tag'">
                <button @click="runAi('expand')">태그 확장 <em>연관 태그 추가</em></button>
                <button @click="runAi('suggest')">유사 태그 <em>비슷한 태그 추천</em></button>
                <button @click="openNlInput('nl2tags')">자연어 → 태그 <em>문장을 태그로</em></button>
              </div>
            </div>
            <!-- 자연어형 출력 AI -->
            <div class="ai-menu-wrap">
              <button class="ai-btn ai-menu-btn" @click.stop="toggleAiMenu('nl')" :disabled="ollamaLoading" title="자연어/문장을 만드는 AI">💬 자연어 AI ▾</button>
              <div class="ai-menu" v-if="aiMenu === 'nl'">
                <button @click="runAi('nl_caption')">자연어 캡션 <em>태그 → 영어 문장</em></button>
                <button @click="openNlInput('nl_scene')">영문 장면묘사 <em>키워드 → 장면</em></button>
                <button @click="runAi('translate')">한↔영 번역</button>
                <button @click="runAi('creative')">창의 생성 <em>캐릭터 기반 창작</em></button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="aiMenu" class="ai-menu-backdrop" @click="aiMenu = ''"></div>
        <div class="nl-input-row" v-if="showNlInput">
          <input v-model="nlPrompt" ref="nlInputRef" :placeholder="pendingNlMode === 'nl2tags' ? '자연어 설명을 입력...' : '키워드를 입력...'" @keydown.enter="runPendingNl()" class="nl-input" />
          <button class="ai-btn go" @click="runPendingNl()" :disabled="ollamaLoading">실행</button>
          <button class="ai-btn" @click="showNlInput = false" title="닫기">✕</button>
        </div>
        <div class="ai-loading" v-if="ollamaLoading">🤖 AI 처리 중...</div>
        <div class="nl-result" v-if="nlResult">
          <textarea :value="nlResult" readonly class="nl-result-text" rows="4"></textarea>
          <div class="nl-result-btns">
            <button class="ai-btn go" @click="copyNlResult" title="복사">복사</button>
            <button class="ai-btn go" @click="useNlAsMain" title="메인 프롬프트에 넣기">메인에 넣기</button>
            <button v-if="nlRes" class="ai-btn go" @click="applyNlRes" :title="`추천 해상도 ${nlRes.w}×${nlRes.h} 적용`">📐 {{ nlRes.w }}×{{ nlRes.h }}</button>
            <button class="ai-btn" @click="nlResult = ''; nlRes = null" title="닫기">✕</button>
          </div>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.main_prompt_text" :color-fn="blockColorClass" placeholder="태그 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="mainRef" v-model="widgets.main_prompt_text" class="auto-grow" placeholder="메인 태그..."
          @input="onMainInput($event)" @keydown="onAutoKey($event)" rows="3"></textarea>
        <div class="ac-popup" v-if="!tagBlockMode && fieldAcTarget === 'main_prompt_text' && acItems.length > 0">
          <div v-for="(tag, i) in acItems" :key="tag" class="ac-item" :class="{ selected: acIdx === i }" @mousedown.prevent="acceptSuggestion(tag)">{{ tag }}</div>
        </div>
      </div>
      <div class="input-group">
        <label>Prefix <span v-if="sectionTokens.prefix" class="tk-badge" :class="tokenBadgeClass(sectionTokens.prefix)">{{ sectionTokens.prefix }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.prefix_prompt_text" :color-fn="blockColorClass" placeholder="선행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="prefixRef" v-model="widgets.prefix_prompt_text" class="auto-grow" placeholder="선행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <div class="input-group">
        <label>Suffix <span v-if="sectionTokens.suffix" class="tk-badge" :class="tokenBadgeClass(sectionTokens.suffix)">{{ sectionTokens.suffix }}t</span></label>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.suffix_prompt_text" :color-fn="blockColorClass" placeholder="후행 추가..." @open-wildcard="(n) => emit('open-wildcard', n)" />
        <textarea v-else ref="suffixRef" v-model="widgets.suffix_prompt_text" class="auto-grow" placeholder="후행..." @input="autoGrow($event.target)"></textarea>
      </div>
      <details class="input-group exclude-section">
        <summary class="exclude-toggle">EXCLUDE (LOCAL)
          <span v-if="excludeRuleCount" class="excl-badge">{{ excludeRuleCount }}</span> ▾
          <button class="excl-mgr-btn" @click.prevent.stop="showExcludeManager = true">🔍 MANAGER</button></summary>
        <div class="exclude-help">
          <span>단어 → 포함하는 모든 태그 제외 (short → short hair, very short hair)</span>
          <span>*단어 → 완전 일치만 제외 (*blue hair → blue hair만)</span>
          <span>_단어 → 앞에 붙는 태그 제외 (_short → very short, too short)</span>
          <span>단어_ → 뒤에 붙는 태그 제외 (short_ → short hair, short pants)</span>
          <span>_단어_ → 포함 (단어와 동일, 명시적)</span>
          <span>~단어 → 예외 완전일치 유지</span>
          <span>~_단어 → 예외 접미 유지 (~_tank top → tank top 유지)</span>
          <span>~단어_ → 예외 접두 유지 (~tank_ → tank top 유지)</span>
          <span>~_단어_ → 예외 포함 유지 (~_tank top_ → blue tank top 등 유지)</span>
        </div>
        <TagBlockField v-if="tagBlockMode" v-model="widgets.exclude_prompt_local_input" :color-fn="excludeColorFn" placeholder="제외 규칙 추가..." />
        <textarea v-else v-model="widgets.exclude_prompt_local_input" class="auto-grow exclude-textarea" placeholder="제외 규칙 (쉼표 구분)..." rows="2"></textarea>
      </details>
    </details>

    <!-- Exclude Manager Modal -->
    <transition name="fade">
      <div v-if="showExcludeManager" class="em-overlay" @mousedown.self="showExcludeManager = false">
        <div class="em-modal">
          <div class="em-header">
            <h3>EXCLUDE MANAGER</h3>
            <span class="em-desc">제외 규칙별 매칭 태그 미리보기</span>
            <button class="close-btn" @click="showExcludeManager = false">✕</button>
          </div>
          <div class="em-body">
            <!-- 좌측: 규칙 목록 + 추가 -->
            <div class="em-rules">
              <input v-model="exRuleSearch" class="em-search" placeholder="🔍 규칙 검색..." />
              <div v-for="item in filteredExRules" :key="item.i" class="em-rule-item"
                :class="[excludeColorFn(item.rule), { active: selectedExRule === item.i }]"
                @click="selectedExRule = item.i; loadExcludeMatches(item.rule)">
                <!-- 편집 모드 -->
                <input v-if="editingExRule === item.i" class="em-rule-edit" v-model="editExRuleText"
                  @blur="finishEditExRule(item.i)" @keydown.enter="finishEditExRule(item.i)" @keydown.escape="editingExRule = -1"
                  @click.stop ref="exRuleEditRef" />
                <!-- 표시 모드 -->
                <span v-else class="em-rule-text" @dblclick.stop="startEditExRule(item.i)">{{ item.rule }}</span>
                <span class="em-match-count">{{ excludeMatches[item.rule]?.length || '...' }}</span>
                <button class="em-rule-rm" @click.stop="removeExcludeRule(item.i)">✕</button>
              </div>
              <div v-if="excludeRules.length === 0" class="em-empty-sm">제외 규칙 없음</div>
              <div v-else-if="filteredExRules.length === 0" class="em-empty-sm">검색 결과 없음</div>
              <div class="em-add-row">
                <input v-model="newExcludeRule" placeholder="규칙 추가..." class="em-add-input" @keydown.enter="addExcludeRule" />
                <button class="em-add-btn" @click="addExcludeRule">+</button>
              </div>
            </div>
            <!-- 우측: 매칭 태그 목록 -->
            <div class="em-matches">
              <template v-if="selectedExRule >= 0 && currentExMatches.length > 0">
                <div class="em-match-header">
                  "{{ excludeRules[selectedExRule] }}" — {{ currentExMatches.length }}개 매칭
                </div>
                <div class="em-match-list">
                  <button v-for="tag in currentExMatches" :key="tag" class="em-tag"
                    :class="{ excepted: isExcepted(tag) }"
                    @click="toggleException(tag)"
                    @contextmenu.prevent="addExactExclude(tag)">
                    {{ tag.replace(/_/g, ' ') }}
                  </button>
                </div>
              </template>
              <div v-else class="em-empty">좌측에서 규칙을 선택하세요</div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useWidgetStore, requestAction } from '../stores/widgetStore.js'
import { openCharPresetModal } from '../composables/uiModals.js'
import { getBackend, onBackendEvent } from '../bridge.js'
import CustomSelect from './CustomSelect.vue'
import TagBlockField from './TagBlockField.vue'

const emit = defineEmits(['toggle-extend', 'open-wildcard'])
const store = useWidgetStore()
const widgets = store.widgets
const route = useRoute()

const generationFamilyItems = ['STANDARD', 'KREA2']
const generationFamilyStorageKey = 'generationFamily'
const standardSnapshotStorageKey = 'generationFamily.standardParams'
const savedGenerationFamily = String(window.localStorage.getItem(generationFamilyStorageKey) || 'STANDARD').toUpperCase()
const showGenerationFamily = computed(() => ['t2i', 'i2i'].includes(String(route.name || '')))
const isI2IRoute = computed(() => String(route.name || '') === 'i2i')
const isKrea2Generation = computed(
  () => showGenerationFamily.value && String(widgets.generation_family_combo || '').toUpperCase() === 'KREA2')
function loadStandardGenerationSnapshot(): { steps: string; cfg: string } | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(standardSnapshotStorageKey) || 'null')
    if (value && typeof value.steps === 'string' && typeof value.cfg === 'string') return value
  } catch {}
  return null
}
let standardGenerationSnapshot: { steps: string; cfg: string } | null = loadStandardGenerationSnapshot()
let generationFamilyRestored = false
let generationFamilyRestoreTimer: ReturnType<typeof setTimeout> | null = null

function saveStandardGenerationSnapshot() {
  if (!standardGenerationSnapshot) return
  try { window.localStorage.setItem(standardSnapshotStorageKey, JSON.stringify(standardGenerationSnapshot)) } catch {}
}

function clearStandardGenerationSnapshot() {
  standardGenerationSnapshot = null
  try { window.localStorage.removeItem(standardSnapshotStorageKey) } catch {}
}

watch(() => widgets.generation_family_combo, (value: any, previous: any) => {
  if (!generationFamilyRestored) return
  const family = String(value || 'STANDARD').toUpperCase()
  try { window.localStorage.setItem(generationFamilyStorageKey, family) } catch {}
  if (family === 'KREA2' && String(previous || '').toUpperCase() !== 'KREA2') {
    if (!standardGenerationSnapshot) {
      standardGenerationSnapshot = {
        steps: String(widgets.steps_input || '25'),
        cfg: String(widgets.cfg_input || '7'),
      }
      saveStandardGenerationSnapshot()
    }
    widgets.steps_input = '8'
    widgets.cfg_input = '1'
  } else if (family !== 'KREA2' && String(previous || '').toUpperCase() === 'KREA2' && standardGenerationSnapshot) {
    widgets.steps_input = standardGenerationSnapshot.steps
    widgets.cfg_input = standardGenerationSnapshot.cfg
    clearStandardGenerationSnapshot()
  }
})

onMounted(() => {
  getBackend().then(() => {
    let attempts = 0
    const restore = () => {
      // QWebChannel의 초기 getAllWidgetValues 콜백이 끝난 뒤 복원해야
      // Python 기본값이 localStorage 선택을 다시 덮어쓰지 않는다.
      if (widgets.generation_family_combo === undefined && attempts++ < 40) {
        generationFamilyRestoreTimer = setTimeout(restore, 50)
        return
      }
      const family = generationFamilyItems.includes(savedGenerationFamily)
        ? savedGenerationFamily : 'STANDARD'
      generationFamilyRestored = true
      if (family === 'STANDARD' && standardGenerationSnapshot) {
        widgets.steps_input = standardGenerationSnapshot.steps
        widgets.cfg_input = standardGenerationSnapshot.cfg
        clearStandardGenerationSnapshot()
      } else if (family === 'KREA2' && String(widgets.generation_family_combo || '').toUpperCase() === 'KREA2') {
        if (!standardGenerationSnapshot) {
          standardGenerationSnapshot = {
            steps: String(widgets.steps_input || '25'),
            cfg: String(widgets.cfg_input || '7'),
          }
          saveStandardGenerationSnapshot()
        }
        widgets.steps_input = '8'
        widgets.cfg_input = '1'
      }
      widgets.generation_family_combo = family
    }
    restore()
  })
})

onUnmounted(() => {
  if (generationFamilyRestoreTimer) clearTimeout(generationFamilyRestoreTimer)
})

// 블록 모드 (Settings에서 제어)
const tagBlockMode = ref(window.localStorage.getItem('tagBlockMode') === 'true')
watch(tagBlockMode, v => window.localStorage.setItem('tagBlockMode', String(v)))

// 같은 SPA 내 변경 감지 (keep-alive 환경)
let _blockModeTimer: ReturnType<typeof setInterval> | null = null
const _backendUnsubs: Array<() => void> = []   // onBackendEvent 해제 함수 (탭 전환 시 누수 방지)
onMounted(() => {
  _blockModeTimer = setInterval(() => {
    const stored = window.localStorage.getItem('tagBlockMode') === 'true'
    if (stored !== tagBlockMode.value) {
      tagBlockMode.value = stored
      console.log('[PromptPanel] Block mode synced:', stored)
    }
  }, 300)
  // Undo/Redo 키보드 단축키 + 초기 스냅 (현재 상태)
  window.addEventListener('keydown', onKeyDownGlobal)
  // 초기 스냅은 약간 지연 (widgets 초기 로드 후)
  setTimeout(pushUndoSnapshot, 800)
})
onUnmounted(() => {
  if (_blockModeTimer) clearInterval(_blockModeTimer)
  window.removeEventListener('keydown', onKeyDownGlobal)
  if (debounceTimer) clearTimeout(debounceTimer)
  for (const off of _backendUnsubs) { try { off() } catch {} }
  _backendUnsubs.length = 0
  // UNDO watch들 일괄 해제
  for (const stop of _undoWatchStops) {
    try { stop() } catch {}
  }
  _undoWatchStops.length = 0
})

const artistLocked = computed({
  get: () => widgets.btn_lock_artist === 'true',
  set: (v) => { widgets.btn_lock_artist = v ? 'true' : 'false' }
})
function toggleArtistLock() { artistLocked.value = !artistLocked.value; requestAction('set_artist_locked', { locked: artistLocked.value }) }

const totalPromptRef = ref<HTMLTextAreaElement | null>(null)
const negRef = ref<HTMLTextAreaElement | null>(null)
const artistRef = ref<HTMLTextAreaElement | null>(null)
const prefixRef = ref<HTMLTextAreaElement | null>(null)
const mainRef = ref<HTMLTextAreaElement | null>(null)
const suffixRef = ref<HTMLTextAreaElement | null>(null)

const modelItems = computed(() => store.getProperty('model_combo', 'items') || [])
const vaeItems = computed(() => store.getProperty('vae_main_combo', 'items') || [])
const teItems = computed(() => store.getProperty('te_main_input', 'items') || [])
const teSelectedList = computed(() => {
  const raw = widgets.te_main_input || ''
  return raw.split(',').map((s: string) => s.trim()).filter(Boolean)
})
const teUnselectedItems = computed(() => {
  const selected = new Set(teSelectedList.value)
  return teItems.value.filter((f: string) => !selected.has(f))
})
function _serializeTe(list: string[]) {
  widgets.te_main_input = list.join(', ')
}
function addTeFile(name: any) {
  if (!name) return
  const cur = teSelectedList.value
  if (cur.includes(name)) return
  // teItems 정렬 순서 유지
  const next = teItems.value.filter((f: string) => cur.includes(f) || f === name)
  _serializeTe(next)
}
function removeTeFile(name: string) {
  _serializeTe(teSelectedList.value.filter((f: string) => f !== name))
}
// 토큰 카운트 헬퍼 — SD/CLIP 근사 (실제 토크나이저보다 약간 보수적)
// 규칙: 각 태그(쉼표 구분) → 단어 수 합산 + 쉼표 수
function approxTokens(text: string) {
  if (!text || !String(text).trim()) return 0
  const chunks = String(text).split(',').map(s => s.trim()).filter(Boolean)
  let total = 0
  for (const c of chunks) {
    const words = c.split(/\s+/).filter(Boolean)
    total += words.length
  }
  return total + Math.max(0, chunks.length - 1) // 쉼표
}
const tokenCount = computed(() => approxTokens(widgets.total_prompt_display))

// 섹션별 토큰 — 블록모드에서도 동작 (widgets 값은 join된 문자열)
const sectionTokens = computed(() => ({
  character: approxTokens(widgets.character_input),
  copyright: approxTokens(widgets.copyright_input),
  artist:    approxTokens(widgets.artist_input),
  main:      approxTokens(widgets.main_prompt_text),
  prefix:    approxTokens(widgets.prefix_prompt_text),
  suffix:    approxTokens(widgets.suffix_prompt_text),
}))
// 75 = CLIP 1청크 한계, 150 = 2청크(BREAK), 225 = 3청크
// 0=숨김, <75=녹색, <150=노랑, ≥150=빨강
function tokenBadgeClass(n: number) {
  if (!n) return ''
  if (n < 75) return 'tk-ok'
  if (n < 150) return 'tk-warn'
  return 'tk-over'
}

// ── Undo/Redo ──
// 추적 필드: 6개 프롬프트 입력 + 캐릭터/저작권/작가
const UNDO_KEYS = [
  'character_input', 'copyright_input', 'artist_input',
  'main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text',
  'neg_prompt_text',
  'exclude_prompt_local_input',
]
type Snapshot = Record<string, string>
const undoStack = ref<Snapshot[]>([])    // 과거 스냅샷
const redoStack = ref<Snapshot[]>([])    // 미래 (Ctrl+Y용)
const MAX_UNDO = 50
let applying = false         // undo 적용 중에는 watch 다시 push 안 함
let debounceTimer: ReturnType<typeof setTimeout> | null = null     // 빠른 타이핑 묶기

function _snap(): Snapshot {
  const s: Snapshot = {}
  for (const k of UNDO_KEYS) s[k] = widgets[k] || ''
  return s
}
function _eq(a: Snapshot, b: Snapshot) {
  for (const k of UNDO_KEYS) if ((a[k] || '') !== (b[k] || '')) return false
  return true
}
function pushUndoSnapshot() {
  const cur = _snap()
  const last = undoStack.value[undoStack.value.length - 1]
  if (last && _eq(last, cur)) return
  undoStack.value.push(cur)
  if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
  redoStack.value = []  // 새 변경 시 redo 초기화
}
function applySnapshot(snap: Snapshot) {
  applying = true
  for (const k of UNDO_KEYS) {
    if (widgets[k] !== snap[k]) widgets[k] = snap[k]
  }
  nextTick(() => { applying = false })
}
function performUndo() {
  if (undoStack.value.length < 2) return  // 첫 스냅(현재) 외에 없으면 안 함
  const cur = undoStack.value.pop() as Snapshot       // 현재 상태
  redoStack.value.push(cur)
  const prev = undoStack.value[undoStack.value.length - 1]
  applySnapshot(prev)
}
function performRedo() {
  if (redoStack.value.length === 0) return
  const next = redoStack.value.pop() as Snapshot
  undoStack.value.push(next)
  applySnapshot(next)
}

// 디바운스 watch — 빠른 타이핑이 끝나면 스냅샷 (500ms)
// 메모리 누수 방지: stop 함수를 모아 onUnmounted에서 일괄 해제
const _undoWatchStops: Array<() => void> = []
for (const k of UNDO_KEYS) {
  _undoWatchStops.push(watch(() => widgets[k], () => {
    if (applying) return
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(pushUndoSnapshot, 500)
  }))
}

// 키보드 단축키 (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z)
function onKeyDownGlobal(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey)) return
  // 입력 요소 안에서도 동작 — input 자체 undo는 우회됨 (덜 자주 쓰임)
  // 단, contenteditable이나 textarea의 native undo는 그대로 (이건 우리가 못 막음)
  const key = e.key.toLowerCase()
  if (key === 'z' && !e.shiftKey) {
    e.preventDefault()
    performUndo()
  } else if (key === 'y' || (key === 'z' && e.shiftKey)) {
    e.preventDefault()
    performRedo()
  }
}

// 블록 색상 분류
const countPattern = /^(\d+)?(girl|boy|other)s?$|^solo$|^multiple_/
const blockColorCache = ref<Record<string, string>>({})

// ── Exclude Manager ──
const showExcludeManager = ref(false)
const excludeRuleCount = computed(() =>
  (widgets.exclude_prompt_local_input || '').split(',').filter((t: string) => t.trim()).length)
const selectedExRule = ref<any>(-1)
const excludeMatches = ref<Record<string, string[]>>({})  // {규칙텍스트: [tags]} — 인덱스 아닌 규칙 문자열로 키잉(중간 삭제/순서변경에도 안 어긋남)

const excludeRules = computed(() => {
  const text = widgets.exclude_prompt_local_input || ''
  return text.split(',').map((t: string) => t.trim()).filter(Boolean)
})

// 매니저 규칙 검색 — 원본 인덱스(i)를 함께 들고 다녀 selectedExRule/remove가 정확히 동작
const exRuleSearch = ref('')
const filteredExRules = computed(() => {
  const q = exRuleSearch.value.trim().toLowerCase()
  const items = excludeRules.value.map((rule: string, i: number) => ({ rule, i }))
  return q ? items.filter((x: { rule: string; i: number }) => x.rule.toLowerCase().includes(q)) : items
})

const currentExMatches = computed(() => {
  const r = excludeRules.value[selectedExRule.value]
  return r ? (excludeMatches.value[r] || []) : []
})

async function loadExcludeMatches(rule: string) {
  const backend: any = await getBackend()
  if (!backend.getExcludeMatches) return
  backend.getExcludeMatches(rule, (json: string) => {
    try {
      const tags = JSON.parse(json)
      if (Array.isArray(tags)) {
        excludeMatches.value = { ...excludeMatches.value, [rule]: tags }
      }
    } catch {}
  })
}

const newExcludeRule = ref('')
const editingExRule = ref(-1)
const editExRuleText = ref('')
const exRuleEditRef = ref<any>(null)

function startEditExRule(idx: any) {
  editingExRule.value = idx
  editExRuleText.value = excludeRules.value[idx]
  nextTick(() => { if (exRuleEditRef.value?.[0]) exRuleEditRef.value[0].focus() })
}

function finishEditExRule(idx: any) {
  if (editingExRule.value !== idx) return
  const newText = editExRuleText.value.trim()
  editingExRule.value = -1
  if (!newText) { removeExcludeRule(idx); return }
  const rules = excludeRules.value.slice()
  rules[idx] = newText
  widgets.exclude_prompt_local_input = rules.join(', ')
  // 매칭 갱신
  selectedExRule.value = idx
  loadExcludeMatches(newText)
}

function addExcludeRule() {
  const rule = newExcludeRule.value.trim()
  if (!rule) return
  const cur = widgets.exclude_prompt_local_input || ''
  widgets.exclude_prompt_local_input = cur ? cur + ', ' + rule : rule
  newExcludeRule.value = ''
}

function removeExcludeRule(idx: any) {
  const rules = excludeRules.value.slice()
  rules.splice(idx, 1)
  widgets.exclude_prompt_local_input = rules.join(', ')
  if (selectedExRule.value >= rules.length) selectedExRule.value = -1
}

function isExcepted(tag: string) {
  const cur = (widgets.exclude_prompt_local_input || '').toLowerCase()
  return cur.includes('~' + tag.toLowerCase())
}

function addExactExclude(tag: string) {
  // 우클릭: *완전일치 제외 규칙 추가
  const cur = widgets.exclude_prompt_local_input || ''
  const rule = '*' + tag
  if (!cur.includes(rule)) {
    widgets.exclude_prompt_local_input = cur ? cur + ', ' + rule : rule
  }
}

function toggleException(tag: string) {
  const cur = widgets.exclude_prompt_local_input || ''
  const exception = '~' + tag
  if (isExcepted(tag)) {
    // 예외 해제 — ~tag 제거
    const rules = cur.split(',').map((r: string) => r.trim()).filter((r: string) => r.toLowerCase() !== exception.toLowerCase())
    widgets.exclude_prompt_local_input = rules.join(', ')
  } else {
    // 예외 추가
    widgets.exclude_prompt_local_input = cur ? cur + ', ' + exception : exception
  }
}

// 최종 프롬프트 블록 변경 시 → 원본 필드에서 태그 제거
function onTotalBlockChange(newVal: string) {
  // FINAL 블록의 새 순서 — 태그(소문자) → 위치 인덱스
  const order = newVal.split(',').map((t: string) => t.trim()).filter(Boolean)
  const orderIdx = new Map<string, number>()
  order.forEach((t: string, i: number) => { const k = t.toLowerCase(); if (!orderIdx.has(k)) orderIdx.set(k, i) })
  const newTags = new Set(order.map((t: string) => t.toLowerCase()))
  // 각 필드: (1) FINAL에서 사라진 태그 제거 (FINAL에서 지우면 인물수 칸 등에 남던 버그 수정)
  //          (2) 남은 태그를 FINAL 순서로 재정렬 → FINAL에서 블록을 옮기면 해당 필드 내부 순서가 따라감.
  //   (필드 순서 자체는 구조상 고정이므로 필드 경계를 넘는 이동은 각 필드 영역 내 재정렬로만 반영됨)
  for (const key of ['char_count_input', 'character_input', 'copyright_input', 'artist_input',
                     'main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text']) {
    const cur = widgets[key] || ''
    const kept = cur.split(',').map((t: string) => t.trim()).filter((t: string) => t && newTags.has(t.toLowerCase()))
    kept.sort((a: string, b: string) => (orderIdx.get(a.toLowerCase()) ?? 0) - (orderIdx.get(b.toLowerCase()) ?? 0))
    const result = kept.join(', ')
    if (result !== cur.trim()) widgets[key] = result
  }
}

function excludeColorFn(text: string) {
  const t = text.trim()
  if (t.startsWith('~')) return 'bc-action'       // 예외 계열 (초록)
  if (t.startsWith('*')) return 'bc-expression'   // 완전 일치 (노랑)
  if (t.startsWith('_') && t.endsWith('_')) return 'bc-nsfw'
  if (t.startsWith('_')) return 'bc-body'         // 끝 매치 (주황)
  if (t.endsWith('_')) return 'bc-clothing'       // 시작 매치 (보라)
  return 'bc-nsfw'
}

function blockColorClass(text: string) {
  if (text.includes('__') && /__(.+?)__/.test(text)) return 'wc-block'
  let t = text.trim().toLowerCase().replace(/ /g, '_').replace(/^\(+/, '').replace(/[\):.\d]+$/, '').trim()
  if (countPattern.test(t)) return 'bc-count'
  return blockColorCache.value[t] ? 'bc-' + blockColorCache.value[t] : ''
}

// 태그 분류 요청
async function classifyVisibleTags() {
  const allTags = new Set<string>()
  for (const key of ['main_prompt_text', 'prefix_prompt_text', 'suffix_prompt_text', 'total_prompt_display']) {
    const text: string = widgets[key] || ''
    for (const t of text.split(',')) {
      let tag = t.trim().replace(/ /g, '_').replace(/^\(+/, '').replace(/[\):.\d]+$/, '').trim()
      if (tag && !countPattern.test(tag.toLowerCase()) && !blockColorCache.value[tag.toLowerCase()] && !/__(.+?)__/.test(tag)) allTags.add(tag)
    }
  }
  if (allTags.size === 0) return
  const backend: any = await getBackend()
  if (backend.classifyTags) {
    backend.classifyTags(JSON.stringify([...allTags]), (json: string) => {
      try {
        const r = JSON.parse(json)
        if (!r.error) {
          const m: Record<string, string> = { sexual:'nsfw', body_parts:'body', clothing:'clothing', pose:'action', expression:'expression', background:'bg', composition:'bg', effect:'effect', objects:'objects', color:'color', character_trait:'trait' }
          for (const [tag, cat] of Object.entries(r)) blockColorCache.value[tag.toLowerCase()] = m[cat as string] || ''
        }
      } catch {}
    })
  }
}
watch(tagBlockMode, v => { if (v) setTimeout(classifyVisibleTags, 200) })

// 딥 프롬프트 클리너
interface Conflict { group: string; tags: string[]; [k: string]: any }
interface OptPreview { before: string; after: string; removed: number; tagCount: number; conflicts: Conflict[]; [k: string]: any }
const optResult = ref('')
const promptConflicts = ref<Conflict[]>([])
const optPreview = ref<OptPreview | null>(null)   // {before, after, removed, tagCount, conflicts}
async function optimizePrompt() {
  const backend: any = await getBackend()
  if (!backend.deepCleanPrompt) return
  const before = widgets.total_prompt_display || ''
  backend.deepCleanPrompt(JSON.stringify({ prompt: before }), (json: string) => {
    try {
      const d = JSON.parse(json)
      if (d.error) { optResult.value = d.error; return }
      // 즉시 적용하지 않고 before/after 비교 후 [적용]으로 반영
      optPreview.value = {
        before,
        after: d.optimized || before,
        removed: d.removed || 0,
        tagCount: d.tag_count || 0,
        conflicts: d.conflicts || [],
      }
    } catch {}
  })
}
function applyOptimize() {
  const p = optPreview.value
  if (!p) return
  widgets.main_prompt_text = p.after
  promptConflicts.value = p.conflicts || []
  optResult.value = `${p.removed}개 중복 제거, ${p.tagCount}개 태그`
  optPreview.value = null
  nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
  setTimeout(() => { optResult.value = '' }, 5000)
}
function cancelOptimize() { optPreview.value = null }

// ⑤ 카테고리 분리 토글
const SEP_CATS = [
  { key: 'expression', label: '표정' },
  { key: 'location', label: '배경·장소' },
  { key: 'pose', label: '포즈·동작' },
  { key: 'object', label: '사물' },
  { key: 'meta', label: '메타' },
]
const showSeparate = ref(false)
const sepCats = reactive<Record<string, boolean>>({ expression: false, location: false, pose: false, object: false, meta: false })
const sepCounts = ref<Record<string, number>>({})
const sepResult = ref('')
async function refreshSepCounts() {
  const backend: any = await getBackend()
  if (!backend || !backend.separateTags) return
  const allKeys = SEP_CATS.map(c => c.key)
  backend.separateTags(widgets.main_prompt_text || '', JSON.stringify(allKeys), (json: string) => {
    try { const d = JSON.parse(json); if (!d.error) sepCounts.value = d.counts || {} } catch {}
  })
}
function toggleSeparate() {
  showSeparate.value = !showSeparate.value
  if (showSeparate.value) refreshSepCounts()
}
async function applySeparate(mode: string) {
  const selected = SEP_CATS.map(c => c.key).filter(k => sepCats[k])
  if (!selected.length) { requestAction('show_toast', { type: 'info', msg: '분류할 카테고리를 선택하세요' }); return }
  const backend: any = await getBackend()
  if (!backend || !backend.separateTags) return
  backend.separateTags(widgets.main_prompt_text || '', JSON.stringify(selected), (json: string) => {
    try {
      const d = JSON.parse(json)
      if (d.error) { requestAction('show_toast', { type: 'error', msg: '분류 실패: ' + d.error }); return }
      const groups = d.groups || {}
      const picked = selected.flatMap(k => groups[k] || [])
      if (mode === 'remove') {
        widgets.main_prompt_text = d.rest || ''
        sepResult.value = `${picked.length}개 제거`
      } else {
        widgets.main_prompt_text = picked.join(', ')
        sepResult.value = `${picked.length}개만 남김`
      }
      refreshSepCounts()
      nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
      setTimeout(() => { sepResult.value = '' }, 4000)
    } catch {}
  })
}

// ② color 페어링 결합
// (🎯 구체화 버튼 제거 — ADVANCED의 '프롬프트 집중' 토글로 대체됨)

// 캐릭터 인사이트
const charInsight = ref<{ tags: string[]; raw: string }>({ tags: [], raw: '' })
async function loadCharTags() {
  const char = widgets.character_input
  if (!char || char.length < 2) { charInsight.value = { tags: [], raw: '' }; return }
  const backend: any = await getBackend()
  if (backend.getCharacterInsight) {
    backend.getCharacterInsight(char, (json: string) => {
      try { const d = JSON.parse(json); charInsight.value = { tags: d.tags || [], raw: d.raw || '' } } catch { charInsight.value = { tags: [], raw: '' } }
    })
  }
}
function insertCharTag(tag: string) {
  const cur = widgets.main_prompt_text || ''
  if (!cur.toLowerCase().includes(tag.toLowerCase())) widgets.main_prompt_text = cur ? cur.replace(/,?\s*$/, '') + ', ' + tag + ', ' : tag + ', '
}
function applyOfficialTags() { if (charInsight.value.raw) { widgets.main_prompt_text = charInsight.value.raw; nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }) } }

// Ollama
const ollamaLoading = ref(false)
const ollamaMode = ref('expand')
const showNlInput = ref(false)
const nlPrompt = ref('')
// LLM 버튼 2개(태그 AI / 자연어 AI) 드롭다운
const aiMenu = ref('')           // '' | 'tag' | 'nl'
const pendingNlMode = ref('nl2tags')
const nlInputRef = ref<HTMLInputElement | null>(null)
function toggleAiMenu(which: string) { aiMenu.value = aiMenu.value === which ? '' : which }
function runAi(mode: string) { aiMenu.value = ''; ollamaMode.value = mode; runOllama() }
function openNlInput(mode: string) {
  aiMenu.value = ''
  pendingNlMode.value = mode
  showNlInput.value = true
  nextTick(() => { try { nlInputRef.value?.focus() } catch {} })
}
function runPendingNl() {
  if (ollamaLoading.value) return
  ollamaMode.value = pendingNlMode.value || 'nl2tags'
  runOllama()
}
const nlResult = ref('')
const nlRes = ref<{ w: string; h: string } | null>(null)   // 창의 모드 추천 해상도 {w, h}
let ollamaTimer: ReturnType<typeof setTimeout> | null = null
async function runOllama() {
  const mode = ollamaMode.value
  const main = widgets.main_prompt_text || ''
  let contentArg = main
  let extraPrompt = ''
  let creativeChar = ''
  if (mode === 'nl2tags') {
    if (!nlPrompt.value.trim()) { requestAction('show_toast', { type: 'info', msg: '자연어 설명을 입력하세요' }); return }
    extraPrompt = nlPrompt.value
  } else if (mode === 'nl_scene') {
    if (!nlPrompt.value.trim()) { requestAction('show_toast', { type: 'info', msg: '키워드를 입력하세요' }); return }
    contentArg = nlPrompt.value
  } else if (mode === 'creative') {
    // 캐릭터는 별도 전달(외견 DB 조회용), 메인 태그는 추가 힌트로. 완전 비어도 생성 허용.
    creativeChar = (widgets.character_input || '').trim()
    contentArg = main.trim()
  } else {
    if (!main.trim()) { requestAction('show_toast', { type: 'info', msg: '프롬프트를 먼저 입력하세요' }); return }
  }
  ollamaLoading.value = true
  // 타임아웃 안전장치
  if (ollamaTimer) clearTimeout(ollamaTimer)
  ollamaTimer = setTimeout(() => {
    if (ollamaLoading.value) {
      ollamaLoading.value = false
      requestAction('show_toast', { type: 'error', msg: 'AI 응답 시간 초과 — Ollama 서버 상태를 확인하세요' })
    }
  }, 65000)
  const backend: any = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; if (ollamaTimer) clearTimeout(ollamaTimer); return }
  const url = window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434'
  const model = window.localStorage.getItem('ollamaModel') || 'gemma3:4b'
  backend.ollamaEnhance(contentArg, mode, JSON.stringify({ prompt: extraPrompt, character: creativeChar, url, model }))
}

async function runSmartNegative() {
  const positivePrompt = widgets.total_prompt_display || widgets.main_prompt_text || ''
  if (!positivePrompt.trim()) {
    requestAction('show_toast', { type: 'info', msg: '포지티브 프롬프트를 먼저 입력하세요' })
    return
  }
  ollamaLoading.value = true
  if (ollamaTimer) clearTimeout(ollamaTimer)
  ollamaTimer = setTimeout(() => {
    if (ollamaLoading.value) {
      ollamaLoading.value = false
      requestAction('show_toast', { type: 'error', msg: 'AI 응답 시간 초과' })
    }
  }, 65000)
  const backend: any = await getBackend()
  if (!backend.ollamaEnhance) { ollamaLoading.value = false; if (ollamaTimer) clearTimeout(ollamaTimer); return }
  const url = window.localStorage.getItem('ollamaUrl') || 'http://localhost:11434'
  const model = window.localStorage.getItem('ollamaModel') || 'gemma3:4b'
  backend.ollamaEnhance(positivePrompt, 'negative', JSON.stringify({ url, model }))
}

function copyNlResult() {
  try { navigator.clipboard?.writeText(nlResult.value) } catch {}
  requestAction('show_toast', { type: 'info', msg: '복사됨' })
}
function useNlAsMain() {
  let add = nlResult.value.trim()
  add = add.replace(/^\s*Resolution:.*$/im, '').trim()   // 해상도 줄은 별도 버튼이라 제외
  const firstBlock = add.split(/\n\s*\n/)[0].trim()        // 다중 블록(창의)이면 첫 블록(태그)만
  if (firstBlock) add = firstBlock
  // 앞의 태그는 override하지 않고 맨 뒤에 추가.
  // 앞에 내용(태그)이 있으면 ', '로 구분해서 자연어를 이어붙임.
  // 예: "muscular" 뒤에 자연어 → "muscular, A muscular man ..."
  const cur = (widgets.main_prompt_text || '').trim().replace(/[,\s]+$/, '')
  widgets.main_prompt_text = cur ? (cur + ', ' + add) : add
  nlResult.value = ''
  nlRes.value = null
  nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) })
  requestAction('show_toast', { type: 'success', msg: '메인 프롬프트 끝에 추가' })
}

function applyNlRes() {
  if (!nlRes.value) return
  widgets.width_input = String(nlRes.value.w)
  widgets.height_input = String(nlRes.value.h)
  requestAction('show_toast', { type: 'success', msg: `해상도 ${nlRes.value.w}×${nlRes.value.h} 적용` })
}

// 자동완성
const acItems = ref<string[]>([])
const acIdx = ref(0)
const fieldAcTarget = ref('')
let acTimer: ReturnType<typeof setTimeout> | null = null

function onFieldInput(e: any, fieldId: string) {
  fieldAcTarget.value = fieldId
  const text = e.target.value; const lastComma = text.lastIndexOf(',')
  const prefix = (lastComma >= 0 ? text.substring(lastComma + 1) : text).trim()
  if (prefix.length < 2) { acItems.value = []; return }
  if (acTimer) clearTimeout(acTimer)
  acTimer = setTimeout(async () => {
    const backend: any = await getBackend()
    if (backend.getTagSuggestions) backend.getTagSuggestions(prefix, (json: string) => { try { acItems.value = JSON.parse(json).slice(0, 10); acIdx.value = 0 } catch { acItems.value = [] } })
  }, 300)
}
function onFieldKey(e: KeyboardEvent, fieldId: string) {
  if (fieldAcTarget.value !== fieldId || !acItems.value.length) return
  if (e.key === 'ArrowDown') { e.preventDefault(); acIdx.value = Math.min(acIdx.value + 1, acItems.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); acIdx.value = Math.max(0, acIdx.value - 1) }
  else if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); acceptFieldSuggestion(acItems.value[acIdx.value], fieldId) }
  else if (e.key === 'Escape') { acItems.value = []; fieldAcTarget.value = '' }
}
function acceptFieldSuggestion(tag: string, fieldId: string) {
  const text = widgets[fieldId] || ''; const lastComma = text.lastIndexOf(',')
  widgets[fieldId] = (lastComma >= 0 ? text.substring(0, lastComma + 1) + ' ' : '') + tag + ', '
  acItems.value = []; fieldAcTarget.value = ''
}
function onMainInput(e: any) { autoGrow(e.target); fieldAcTarget.value = 'main_prompt_text'; onFieldInput(e, 'main_prompt_text') }
function onAutoKey(e: KeyboardEvent) { onFieldKey(e, 'main_prompt_text') }
function acceptSuggestion(tag: string) { acceptFieldSuggestion(tag, 'main_prompt_text'); nextTick(() => { if (mainRef.value) { mainRef.value.focus(); autoGrow(mainRef.value) } }) }

function autoGrow(el: any) { if (!el) return; el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' }
function growAll() { nextTick(() => { ;[totalPromptRef, negRef, artistRef, prefixRef, mainRef, suffixRef].forEach(r => { if (r.value) autoGrow(r.value) }) }) }

onMounted(() => {
  setTimeout(growAll, 500); setTimeout(growAll, 1500)
  // UI prefs 로드 (재시작 시 블록 모드 복원)
  _backendUnsubs.push(onBackendEvent('uiPrefsLoaded', (json: string) => {
    try {
      const prefs = JSON.parse(json)
      if (typeof prefs.tagBlockMode === 'boolean') {
        window.localStorage.setItem('tagBlockMode', String(prefs.tagBlockMode))
        tagBlockMode.value = prefs.tagBlockMode
      }
      if (typeof prefs.galleryShowMetadata === 'boolean') window.localStorage.setItem('galleryShowMetadata', String(prefs.galleryShowMetadata))
    } catch {}
  }))
  _backendUnsubs.push(onBackendEvent('ollamaResult', (json: string) => {
    ollamaLoading.value = false
    if (ollamaTimer) clearTimeout(ollamaTimer)
    try {
      const d = JSON.parse(json)
      if (d.error) {
        const msg = d.error.includes('연결') ? 'Ollama 서버에 연결할 수 없습니다' :
                    d.error.includes('시간') || d.error.includes('Timeout') ? 'AI 응답 시간 초과' :
                    `AI 오류: ${d.error}`
        requestAction('show_toast', { type: 'error', msg })
        return
      }
      if (d.tags) {
        const NL = ['nl_caption', 'nl_scene', 'translate', 'creative']
        if (NL.includes(d.mode)) {
          nlResult.value = d.tags
          // 추천 해상도 파싱 (창의 모드)
          nlRes.value = null
          const rm = d.tags.match(/Resolution:\s*(\d{3,4})\s*[x×]\s*(\d{3,4})/i)
          if (rm) nlRes.value = { w: rm[1], h: rm[2] }
          const label = d.mode === 'translate' ? '번역' : d.mode === 'nl_caption' ? '캡션'
                      : d.mode === 'creative' ? '창의 생성' : '장면묘사'
          requestAction('show_toast', { type: 'success', msg: `AI ${label} 완료` })
        } else if (d.mode === 'negative') {
          const existing = (widgets.neg_prompt_text || '').trim()
          widgets.neg_prompt_text = existing ? existing.replace(/,?\s*$/, '') + ', ' + d.tags : d.tags
          requestAction('show_toast', { type: 'success', msg: 'AI 네거티브 생성 완료' })
        } else {
          widgets.main_prompt_text = d.tags
          showNlInput.value = false
          nlPrompt.value = ''
          requestAction('show_toast', { type: 'success', msg: `AI ${d.mode === 'nl2tags' ? '변환' : d.mode === 'suggest' ? '추천' : '확장'} 완료` })
        }
      }
    } catch {}
  }))
})

watch(() => widgets.total_prompt_display, () => nextTick(() => { if (totalPromptRef.value) autoGrow(totalPromptRef.value) }))
watch(() => widgets.neg_prompt_text, () => nextTick(() => { if (negRef.value) autoGrow(negRef.value) }))
watch(() => widgets.artist_input, () => nextTick(() => { if (artistRef.value) autoGrow(artistRef.value) }))
watch(() => widgets.main_prompt_text, () => { nextTick(() => { if (mainRef.value) autoGrow(mainRef.value) }); if (tagBlockMode.value) classifyVisibleTags() })
</script>

<style scoped>
.prompt-panel { display: flex; flex-direction: column; gap: 12px; }
.glass-card { background: rgba(20, 20, 20, 0.6); border: 1px solid var(--border); border-radius: var(--radius-card); padding: 14px; }
.glass-card.highlight { border-color: var(--accent-dim); background: rgba(250, 204, 21, 0.02); }
.glass-card:hover { border-color: #333; }
.card-header { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: 1.5px; margin-bottom: 12px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; }
summary { list-style: none; outline: none; }
summary::-webkit-details-marker { display: none; }
.input-group { margin-bottom: 10px; }
.row { display: flex; gap: 6px; }
.label-row { align-items: center; margin-bottom: 4px; }
.small-btn { padding: 0 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; white-space: nowrap; }
.lock-btn { background: none; border: none; cursor: pointer; font-size: 14px; padding: 0 4px; opacity: 0.5; }
.lock-btn.locked { opacity: 1; }
.total-prompt { min-height: 60px; font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.5; color: var(--accent); border-color: var(--accent-dim); }
.neg-section { margin-top: 8px; }
.neg-toggle { cursor: pointer; list-style: none; display: flex; align-items: center; justify-content: space-between; }
.neg-toggle::-webkit-details-marker { display: none; }
.neg-ai { font-size: 12px !important; padding: 2px 6px !important; opacity: 0.6; }
.neg-ai:hover { opacity: 1; }
.danger-label { color: #f87171; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
.neg-prompt { min-height: 30px; color: #f87171; border-color: rgba(248,113,113,0.2); }
.auto-grow { resize: none; overflow: hidden; min-height: 32px; }
.token-info { font-size: 9px; color: var(--text-muted); }
.prompt-actions { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.optimize-btn { padding: 3px 10px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary); font-size: 9px; font-weight: 700; cursor: pointer; }
.optimize-btn:hover { border-color: var(--accent); color: var(--accent); }
.opt-result { font-size: 9px; color: #4ade80; }
.opt-preview { margin-top: 6px; background: var(--bg-secondary); border: 1px solid var(--accent); border-radius: 8px; padding: 9px; }
.opt-prev-head { display: flex; justify-content: space-between; align-items: center; font-size: 10px; font-weight: 800; color: var(--accent); margin-bottom: 7px; }
.opt-prev-stat { font-size: 9px; font-weight: 700; color: var(--text-muted); }
.opt-prev-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.opt-prev-col label { display: block; font-size: 8px; font-weight: 800; color: var(--text-muted); margin-bottom: 3px; letter-spacing: 1px; }
.opt-prev-text { max-height: 110px; overflow-y: auto; background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 6px 8px; font-size: 10px; line-height: 1.4; color: var(--text-secondary); word-break: break-word; white-space: pre-wrap; }
.opt-prev-text.after { color: var(--text-primary); border-color: rgba(74,222,128,0.4); }
.opt-prev-conf { margin-top: 6px; font-size: 9px; color: #fbbf24; }
.opt-prev-btns { display: flex; gap: 6px; margin-top: 8px; }
.opt-apply { flex: 1; padding: 6px; background: var(--accent); color: #000; border: none; border-radius: 5px; font-size: 10px; font-weight: 800; cursor: pointer; }
.opt-apply:hover { background: var(--accent-hover); }
.opt-cancel { padding: 6px 12px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 5px; color: var(--text-secondary); font-size: 10px; font-weight: 700; cursor: pointer; }

/* ⑤ 카테고리 분리 패널 */
.separate-panel { margin-top: 6px; padding: 8px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; }
.sep-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.sep-chip { display: inline-flex; align-items: center; gap: 5px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 12px; color: var(--text-secondary); font-size: 10px; font-weight: 700; padding: 3px 11px; cursor: pointer; }
.sep-chip:hover { color: var(--text-primary); }
.sep-chip.on { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.sep-n { font-size: 8px; font-weight: 700; padding: 0 5px; border-radius: 7px; background: rgba(0,0,0,0.3); }
.sep-actions { display: flex; align-items: center; gap: 6px; margin-top: 7px; }
.sep-act { border: none; border-radius: 5px; font-size: 9px; font-weight: 700; padding: 4px 10px; cursor: pointer; }
.sep-act.remove { background: rgba(248,113,113,0.14); border: 1px solid #f87171; color: #f87171; }
.sep-act.extract { background: rgba(96,165,250,0.14); border: 1px solid #60a5fa; color: #60a5fa; }
.sep-hint { font-size: 9px; color: #4ade80; }
.conflicts { margin-top: 4px; }
.conflict-item { font-size: 9px; color: #fbbf24; padding: 2px 0; }
.char-insight { margin-top: 6px; background: rgba(45,212,191,0.03); border: 1px solid rgba(45,212,191,0.1); border-radius: 6px; padding: 8px; }
.insight-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.insight-label { font-size: 9px; font-weight: 800; color: #2dd4bf; }
.insight-apply { padding: 2px 8px; background: #2dd4bf; border: none; border-radius: 3px; color: #000; font-size: 9px; font-weight: 800; cursor: pointer; }
.insight-tags { display: flex; flex-wrap: wrap; gap: 3px; max-height: 80px; overflow-y: auto; }
.char-tag-chip { padding: 2px 8px; background: rgba(45,212,191,0.08); border: 1px solid rgba(45,212,191,0.2); border-radius: 4px; color: #2dd4bf; font-size: 9px; cursor: pointer; }
.char-tag-chip:hover { background: rgba(45,212,191,0.15); border-color: #2dd4bf; }
.ai-btns { display: flex; gap: 3px; }
.ai-btn { width: 26px; height: 22px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.ai-btn:hover { border-color: var(--accent); color: var(--accent); }
.ai-btn:disabled { opacity: 0.3; }
.ai-btn.go { width: auto; padding: 0 8px; background: var(--accent); color: #000; border: none; font-weight: 700; font-size: 10px; }
/* 2개 LLM 드롭다운 (태그 AI / 자연어 AI) */
.ai-menu-wrap { position: relative; display: inline-block; }
.ai-menu-btn { width: auto; padding: 0 9px; font-size: 10px; font-weight: 700; white-space: nowrap; }
.ai-menu { position: absolute; top: 100%; right: 0; margin-top: 4px; z-index: 60; min-width: 180px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 4px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 1px; }
.ai-menu button { width: 100%; height: auto; text-align: left; background: transparent; border: none; color: var(--text-secondary); font-size: 11px; font-weight: 600; padding: 7px 10px; border-radius: 5px; cursor: pointer; white-space: nowrap; display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.ai-menu button:hover { background: var(--bg-button); color: var(--accent); }
.ai-menu button em { font-style: normal; font-weight: 400; font-size: 9px; color: var(--text-muted); }
.ai-menu-backdrop { position: fixed; inset: 0; z-index: 55; }
.nl-input-row { display: flex; gap: 4px; margin-bottom: 6px; }
.nl-input { flex: 1; padding: 6px 10px; font-size: 11px; }
.ai-loading { font-size: 10px; color: var(--accent); margin-bottom: 4px; animation: pulse 1.5s infinite; }
.nl-result { margin: 4px 0; }
.nl-result-text { width: 100%; background: var(--bg-input); border: 1px solid var(--accent); border-radius: 6px; padding: 7px 9px; color: var(--text-primary); font-size: 12px; resize: vertical; line-height: 1.5; font-family: inherit; }
.nl-result-btns { display: flex; gap: 4px; margin-top: 4px; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.autocomplete-wrap { position: relative; }
.ac-popup { position: absolute; left: 0; right: 0; top: 100%; z-index: 100; background: #1A1A1A; border: 1px solid var(--border); border-radius: 6px; max-height: 200px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
.ac-item { padding: 6px 12px; font-size: 11px; color: var(--text-secondary); cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.03); }
.ac-item:hover, .ac-item.selected { background: var(--accent-dim); color: var(--accent); }
label.danger { color: #f87171; }
.exclude-section { margin-bottom: 0; }
.exclude-toggle { font-size: 10px; font-weight: 800; color: #f87171; letter-spacing: 1px; cursor: pointer; list-style: none; }
.excl-badge { display: inline-block; min-width: 14px; padding: 0 5px; border-radius: 7px; background: rgba(248,113,113,0.2); color: #f87171; font-size: 9px; font-weight: 800; text-align: center; }
.exclude-toggle::-webkit-details-marker { display: none; }
.exclude-help { display: flex; flex-direction: column; gap: 2px; margin: 6px 0; padding: 6px 8px; background: rgba(248,113,113,0.03); border: 1px solid rgba(248,113,113,0.1); border-radius: 4px; }
.exclude-help span { font-size: 9px; color: var(--text-muted); font-family: 'Consolas', monospace; }
.exclude-textarea { color: #f87171; border-color: rgba(248,113,113,0.2); font-size: 11px; }
.excl-mgr-btn { padding: 1px 8px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--text-muted); font-size: 8px; cursor: pointer; margin-left: 8px; }
.excl-mgr-btn:hover { border-color: #f87171; color: #f87171; }

/* Exclude Manager Modal */
.em-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 3000; display: flex; align-items: center; justify-content: center; }
.em-modal { width: min(94vw, 1080px); height: min(88vh, 760px); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.em-header { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.em-header h3 { font-size: 12px; letter-spacing: 2px; color: #f87171; }
.em-desc { font-size: 9px; color: var(--text-muted); flex: 1; }
.em-body { flex: 1; display: flex; overflow: hidden; }
.em-rules { width: 280px; overflow-y: auto; border-right: 1px solid var(--border); padding: 8px; }
.em-search { width: 100%; box-sizing: border-box; padding: 6px 10px; margin-bottom: 8px; font-size: 11px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; color: var(--text); position: sticky; top: -8px; z-index: 1; }
.em-search:focus { outline: none; border-color: #f87171; }
.em-rule-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; font-size: 11px; cursor: pointer; border-radius: 4px; margin-bottom: 2px; border: 1px solid transparent; }
.em-rule-item:hover { background: var(--bg-input); }
.em-rule-item.active { border-color: #f87171; background: rgba(248,113,113,0.05); }
.em-rule-text { font-family: 'Consolas', monospace; }
.em-match-count { font-size: 9px; color: var(--text-muted); background: var(--bg-button); padding: 1px 6px; border-radius: 8px; }
.em-matches { flex: 1; overflow-y: auto; padding: 12px; }
.em-match-header { font-size: 10px; color: var(--text-muted); margin-bottom: 8px; }
.em-match-list { display: flex; flex-wrap: wrap; gap: 4px; }
.em-tag { padding: 3px 10px; background: rgba(248,113,113,0.05); border: 1px solid rgba(248,113,113,0.2); border-radius: 4px; color: #f87171; font-size: 10px; cursor: pointer; transition: all 0.12s; }
.em-tag:hover { border-color: rgba(248,113,113,0.5); }
.em-tag.excepted { background: rgba(74,222,128,0.1); border-color: rgba(74,222,128,0.3); color: #4ade80; text-decoration: line-through; opacity: 0.6; }
.em-tag.excepted:hover { opacity: 1; }
.em-rule-rm { background: none; border: none; color: #f87171; cursor: pointer; font-size: 11px; flex-shrink: 0; }
.em-rule-edit { flex: 1; padding: 2px 6px; font-size: 11px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: 3px; color: var(--text-primary); font-family: 'Consolas', monospace; }
.em-rule-text { cursor: default; }
.em-add-row { display: flex; gap: 4px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.em-add-input { flex: 1; padding: 4px 8px; font-size: 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 3px; color: var(--text-primary); }
.em-add-btn { width: 28px; background: var(--bg-button); border: 1px solid var(--border); border-radius: 3px; color: var(--accent); font-weight: 800; cursor: pointer; }
.em-empty-sm { padding: 8px; text-align: center; color: var(--text-muted); font-size: 10px; }
.em-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 12px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
input[type="number"] { -moz-appearance: textfield; }
input::-webkit-outer-spin-button, input::-webkit-inner-spin-button { -webkit-appearance: none; }
/* neg block field */
.neg :deep(.tbf) { border-color: rgba(248,113,113,0.15); }
.neg :deep(.tbf-block) { border-color: rgba(248,113,113,0.2); color: #f87171; font-size: 10px; }
.hint { font-size: 10px; color: rgba(255,255,255,0.4); font-weight: normal; margin-left: 4px; }
.generation-family { padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.engine-hint { display: block; margin-top: 5px; font-size: 9px; color: var(--text-muted); }
.krea-engine-note {
  display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; padding: 10px;
  border: 1px solid rgba(167,139,250,0.35); border-radius: 7px;
  background: linear-gradient(135deg, rgba(124,58,237,0.12), rgba(45,212,191,0.05));
}
.krea-engine-note strong { font-size: 11px; letter-spacing: 1.4px; color: #c4b5fd; }
.krea-engine-note span { font-size: 9px; line-height: 1.45; color: var(--text-muted); }
.tk-badge {
  display: inline-block; padding: 1px 6px; margin-left: 6px; font-size: 9px;
  font-weight: bold; border-radius: 8px; vertical-align: middle;
  border: 1px solid transparent;
}
.tk-badge.tk-ok    { background: rgba(74,222,128,0.12); color: #4ade80; border-color: rgba(74,222,128,0.3); }
.tk-badge.tk-warn  { background: rgba(251,191,36,0.12); color: #fbbf24; border-color: rgba(251,191,36,0.4); }
.tk-badge.tk-over  { background: rgba(248,113,113,0.18); color: #f87171; border-color: rgba(248,113,113,0.5); }

/* Undo/Redo 버튼 */
.undo-btns { float: right; display: inline-flex; gap: 4px; margin-left: auto; }
.undo-btn {
  width: 24px; height: 22px; padding: 0; font-size: 13px; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px; color: var(--text-primary);
}
.undo-btn:hover:not(:disabled) { background: rgba(96,165,250,0.18); color: #93c5fd; border-color: #60a5fa; }
.undo-btn:disabled { opacity: 0.3; cursor: not-allowed; }
summary.card-header { display: flex; align-items: center; }
.te-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.te-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.15);
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  transition: all 0.15s;
}
.te-chip:hover { border-color: rgba(96,165,250,0.5); color: #fff; }
.te-chip.active {
  background: rgba(96,165,250,0.2);
  border-color: #60a5fa;
  color: #93c5fd;
}
.te-chip-x { margin-left: 4px; opacity: 0.6; }
.te-chip:hover .te-chip-x { opacity: 1; color: #f87171; }
</style>
