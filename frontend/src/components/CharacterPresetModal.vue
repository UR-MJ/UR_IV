<template>
  <div class="cpm-overlay" @mousedown.self="close" @keydown.esc="close">
    <div class="cpm-modal">
      <!-- Header -->
      <div class="cpm-header">
        <div>
          <h3>캐릭터 특징 프리셋</h3>
          <span class="cpm-sub">캐릭터를 검색하고 특징 태그를 선택해 프롬프트에 삽입합니다</span>
        </div>
        <button class="cpm-close" @click="close">✕</button>
      </div>

      <!-- Search -->
      <div class="cpm-searchbar">
        <input ref="searchEl" v-model="query" class="cpm-search"
          placeholder="캐릭터 이름 검색 (예: hatsune miku, remilia scarlet)" @input="onQuery" />
        <button class="cpm-deck-btn" :class="{ active: deckOnly }" @click="toggleDeckOnly"
          title="현재 프롬프트 덱에 등장하는 캐릭터만 표시">🎴 덱 캐릭터만</button>
      </div>

      <!-- Body -->
      <div class="cpm-body">
        <!-- Left: result list -->
        <div class="cpm-left">
          <div class="cpm-left-label">{{ resultLabel }}</div>
          <div class="cpm-list">
            <div v-for="r in displayResults" :key="r.key" class="cpm-item"
              :class="{ active: selectedChar === r.key }" @click="selectChar(r.key)">
              <span class="cpm-item-name">{{ r.hasPreset ? '★ ' : '' }}{{ r.key }}</span>
              <span v-if="r.count" class="cpm-item-count">{{ r.count.toLocaleString() }}</span>
            </div>
            <div v-if="displayResults.length === 0" class="cpm-empty">{{ emptyMsg }}</div>
          </div>
        </div>

        <!-- Right: features -->
        <div class="cpm-right">
          <div v-if="!selectedChar" class="cpm-empty cpm-right-empty">← 캐릭터를 선택하세요</div>
          <template v-else>
            <div class="cpm-charhead">
              <span class="cpm-charname">{{ selectedChar }}</span>
              <span v-if="charCount" class="cpm-charcount">Danbooru {{ charCount.toLocaleString() }}개</span>
              <span v-if="presetStatus" class="cpm-pstatus">{{ presetStatus }}</span>
            </div>

            <!-- ③ copyright(시리즈) 자동 추가 토글 -->
            <div v-if="copyright" class="cpm-copyrow">
              <button class="cpm-copychip" :class="{ off: !addCopyright }" @click="addCopyright = !addCopyright"
                title="캐릭터 적용 시 copyright(시리즈) 태그를 함께 추가합니다">
                📚 {{ copyright }}<span class="cpm-copytag">{{ addCopyright ? '함께 추가' : '제외' }}</span>
              </button>
            </div>

            <!-- Select buttons -->
            <div class="cpm-selrow">
              <button class="cpm-sel" @click="selectAll">전체 선택</button>
              <button class="cpm-sel" @click="deselectAll">전체 해제</button>
              <button class="cpm-sel warn" @click="excludeCostume" title="glasses/bow/eyewear 등 복장 태그 선택 해제">복장 제외</button>
              <button class="cpm-sel db" @click="fetchDanbooru" :disabled="dbLoading" title="danbooru에서 실제 태그 가져오기 (로컬 DB가 틀리거나 없을 때)">{{ dbLoading ? '…' : '🌐 danbooru' }}</button>
            </div>

            <!-- Tag chips (scroll) -->
            <div class="cpm-tagscroll">
              <!-- 전역(모든 캐릭터) 설정 -->
              <div class="cpm-global" v-if="selectedChar">
                <div class="cpm-global-head">🌐 전역 — 모든 캐릭터에 적용</div>
                <div class="cpm-global-cats">
                  <span class="cpm-global-sub">카테고리</span>
                  <button v-for="c in CAT_LIST" :key="c.key" class="cpm-gcat" :class="{ off: !globalCatOn[c.key] }"
                    @click="toggleGlobalCat(c.key)" :title="'클릭하여 ' + (globalCatOn[c.key] ? 'OFF' : 'ON')">
                    {{ c.label }} {{ globalCatOn[c.key] ? 'ON' : 'OFF' }}
                  </button>
                </div>
                <div class="cpm-global-words">
                  <span class="cpm-global-sub">단어 OFF</span>
                  <input v-model="newGlobalWord" @keydown.enter="addGlobalWord" placeholder="전역 제외 단어 (Enter)" class="cpm-gword-in" />
                  <button class="cpm-gword-add" @click="addGlobalWord" title="추가">＋</button>
                  <button v-for="w in globalWordOff" :key="w" class="cpm-gword-chip" @click="removeGlobalWord(w)" title="클릭하여 해제">{{ w }} ✕</button>
                </div>
              </div>
              <div class="cpm-section-label core">핵심 특징 ({{ coreTags.length }})</div>
              <div class="cpm-chips">
                <button v-for="(t, i) in coreTags" :key="'c'+i" class="cpm-chip"
                  :class="chipClass(t)" :disabled="t.existing" @click="toggleChip(t)">
                  {{ t.tag }}<span v-if="t.existing" class="cpm-exist">(존재)</span>
                </button>
                <span v-if="coreTags.length === 0" class="cpm-none">없음</span>
              </div>

              <template v-if="auxTags.length">
                <div class="cpm-section-label aux">보조 특징 ({{ auxTags.length }}) <span class="cpm-etc-hint">헤어스타일·체형·피부 등</span></div>
                <div class="cpm-chips">
                  <button v-for="(t, i) in auxTags" :key="'a'+i" class="cpm-chip aux"
                    :class="chipClass(t)" :disabled="t.existing" @click="toggleChip(t)">
                    {{ t.tag }}<span v-if="t.existing" class="cpm-exist">(존재)</span>
                  </button>
                </div>
              </template>

              <template v-if="costumeTags.length">
                <div class="cpm-section-label costume">
                  의상 · 추가 특징 ({{ costumeTags.length }})
                  <button class="cpm-regiontoggle" @click="groupByRegion = !groupByRegion"
                    :title="groupByRegion ? '부위별 그룹 끄기' : '부위별 그룹 켜기'">{{ groupByRegion ? '👕 부위별' : '☰ 평면' }}</button>
                </div>
                <!-- 부위(region)별 그룹 -->
                <template v-if="groupByRegion">
                  <div v-for="grp in costumeByRegion" :key="grp.region" class="cpm-region-grp">
                    <div class="cpm-region-label">{{ grp.label }} <span class="cpm-region-n">{{ grp.tags.length }}</span></div>
                    <div class="cpm-chips">
                      <button v-for="(t, i) in grp.tags" :key="grp.region+i" class="cpm-chip costume"
                        :class="chipClass(t)" :disabled="t.existing" @click="toggleChip(t)">
                        {{ t.tag }}<span v-if="t.existing" class="cpm-exist">(존재)</span>
                      </button>
                    </div>
                  </div>
                </template>
                <!-- 평면 보기 -->
                <div v-else class="cpm-chips">
                  <button v-for="(t, i) in costumeTags" :key="'k'+i" class="cpm-chip costume"
                    :class="chipClass(t)" :disabled="t.existing" @click="toggleChip(t)">
                    {{ t.tag }}<span v-if="t.existing" class="cpm-exist">(존재)</span>
                  </button>
                </div>
              </template>

              <template v-if="etcTags.length">
                <div class="cpm-section-label etc">기타 ({{ etcTags.length }}) <span class="cpm-etc-hint">스타일·체형·포즈 등 — 기본 미선택</span></div>
                <div class="cpm-chips">
                  <button v-for="(t, i) in etcTags" :key="'e'+i" class="cpm-chip etc"
                    :class="chipClass(t)" :disabled="t.existing" @click="toggleChip(t)">
                    {{ t.tag }}<span v-if="t.existing" class="cpm-exist">(존재)</span>
                  </button>
                </div>
              </template>

              <div v-if="customTags.length" class="cpm-section-label custom">커스텀 ({{ customTags.length }})</div>
              <div v-if="customTags.length" class="cpm-chips">
                <button v-for="(t, i) in customTags" :key="'u'+i" class="cpm-chip cust"
                  :class="{ off: !t.checked }" @click="t.checked = !t.checked">{{ t.tag }}</button>
              </div>
            </div>

            <!-- Add custom -->
            <div class="cpm-addrow">
              <input v-model="newCustom" class="cpm-addinput" placeholder="프롬프트 추가 (쉼표로 여러 개)" @keydown.enter="addCustom" />
              <button class="cpm-add" @click="addCustom">+ 추가</button>
            </div>

            <!-- Preset save/delete -->
            <div class="cpm-presetrow">
              <button class="cpm-psave" @click="savePreset">💾 프리셋 저장</button>
              <button class="cpm-pdel" @click="deletePreset">🗑 프리셋 삭제</button>
            </div>

            <!-- Conditional rules (collapsible) -->
            <details class="cpm-cond">
              <summary>캐릭터 조건부 프롬프트 ({{ condRules.length }})</summary>
              <div class="cpm-condbody">
                <div v-for="(rule, i) in condRules" :key="i" class="cpm-rule">
                  <input v-model="rule.condition" class="cpm-r-cond" placeholder="조건 태그" />
                  <select v-model="rule.exists" class="cpm-r-sel">
                    <option :value="true">있으면</option>
                    <option :value="false">없으면</option>
                  </select>
                  <select v-model="rule.action" class="cpm-r-sel">
                    <option value="add">추가</option>
                    <option value="remove">제거</option>
                    <option value="replace">교체</option>
                  </select>
                  <select v-model="rule.location" class="cpm-r-sel">
                    <option value="main">main</option>
                    <option value="prefix">선행</option>
                    <option value="suffix">후행</option>
                    <option value="neg">네거</option>
                  </select>
                  <input :value="rule.tags.join(', ')" class="cpm-r-tags" placeholder="대상 태그 (쉼표)"
                    @input="rule.tags = ($event.target as HTMLInputElement).value.split(',').map((s: string) => s.trim()).filter(Boolean)" />
                  <button class="cpm-r-del" @click="condRules.splice(i, 1)">✕</button>
                </div>
                <button class="cpm-r-add" @click="addRule">+ 규칙 추가</button>
              </div>
            </details>
          </template>
        </div>
      </div>

      <!-- Footer -->
      <div class="cpm-footer">
        <span class="cpm-foot-status">{{ status }}</span>
        <div class="cpm-foot-spacer"></div>
        <button class="cpm-apply both" :disabled="!selectedChar" @click="apply(true)">캐릭터 + 특징 적용</button>
        <button class="cpm-apply feat" :disabled="!selectedChar" @click="apply(false)">특징만 적용</button>
        <button class="cpm-apply close" @click="close">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { getBackend } from '../bridge.js'
import { requestAction } from '../stores/widgetStore.js'

interface SearchResult { key: string; count: number; hasPreset: boolean; [k: string]: any }
interface TagItem { tag: string; existing?: boolean; costume?: boolean; checked?: boolean; region?: string; regionLabel?: string; [k: string]: any }
interface CustomTagItem { tag: string; checked: boolean }
interface CondRule { condition: string; exists: boolean; tags: string[]; location: string; action: string; enabled: boolean }
interface CatItem { key: string; label: string }
interface RegionGroup { region: string; label: string; tags: TagItem[] }

const emit = defineEmits<{ close: [] }>()

const query = ref('')
const results = ref<SearchResult[]>([])          // [{key, count, hasPreset}]
const selectedChar = ref('')
const charCount = ref(0)
const coreTags = ref<TagItem[]>([])         // [{tag, existing, costume, checked}]
const costumeTags = ref<TagItem[]>([])
const etcTags = ref<TagItem[]>([])          // 기타(포즈·표정·동작 등 목록 밖) — 기본 미선택
const auxTags = ref<TagItem[]>([])          // 보조 특징(characteristic_list.txt) — 기본 선택
// ── 전역(모든 캐릭터 공통) 설정 ──
const CAT_LIST: CatItem[] = [{ key: 'core', label: '핵심' }, { key: 'aux', label: '보조' }, { key: 'costume', label: '의상' }, { key: 'etc', label: '기타' }]
const globalCatOn = reactive<Record<string, boolean>>({ core: true, aux: true, costume: true, etc: false })
const globalWordOff = ref<string[]>([])    // 모든 캐릭터에서 항상 OFF인 단어(normalized)
const newGlobalWord = ref('')
const customTags = ref<CustomTagItem[]>([])       // [{tag, checked}]
const condRules = ref<CondRule[]>([])        // [{condition, exists, tags:[], location, action, enabled}]
const presetStatus = ref('')
const newCustom = ref('')
const status = ref('')
const copyright = ref('')         // ③ 캐릭터→copyright(시리즈)
const addCopyright = ref(true)    // copyright 함께 추가 여부
const groupByRegion = ref(true)   // ④ 의상 부위별 그룹 보기
const dbLoading = ref(false)
const deckOnly = ref(false)
const deckChars = ref<string[] | null>(null)      // array of normalized names | null
const searchEl = ref<HTMLInputElement | null>(null)

let _searchTimer: ReturnType<typeof setTimeout> | null = null

function callBk(method: string, ...args: any[]): Promise<any> {
  return new Promise(async (resolve) => {
    const bk: any = await getBackend()
    if (!bk || !bk[method]) { resolve(null); return }
    try {
      bk[method](...args, (json: string) => {
        try { resolve(JSON.parse(json)) } catch { resolve(null) }
      })
    } catch (e) { resolve(null) }
  })
}

function norm(s: string): string { return (s || '').trim().toLowerCase().replace(/_/g, ' ') }

// ④ 의상 부위(region) 표시 순서 (머리→발→전신→스타일)
const REGION_ORDER = ['HEAD_NECK_FACE', 'UPPER_BODY', 'WAIST_HIP', 'ARMS_HANDS', 'LEGS_FEET', 'FULL_BODY', 'STYLE', 'UNASSIGNED']
const costumeByRegion = computed<RegionGroup[]>(() => {
  const buckets: Record<string, RegionGroup> = {}
  for (const t of costumeTags.value) {
    const r = t.region || 'UNASSIGNED'
    if (!buckets[r]) buckets[r] = { region: r, label: t.regionLabel || r, tags: [] }
    buckets[r].tags.push(t)
  }
  const order = REGION_ORDER.filter(r => buckets[r])
  for (const r in buckets) if (!order.includes(r)) order.push(r)
  return order.map(r => buckets[r])
})

const displayResults = computed(() => {
  if (deckOnly.value) {
    const set = new Set(deckChars.value || [])
    let base: SearchResult[] = (deckChars.value || []).map(n => ({ key: n, count: 0, hasPreset: false }))
    // 검색 결과 중 덱에 있는 것은 count/hasPreset 정보로 보강
    const byNorm: Record<string, SearchResult> = {}
    for (const r of results.value) byNorm[norm(r.key)] = r
    base = base.map(b => byNorm[norm(b.key)] ? byNorm[norm(b.key)] : b)
    const q = norm(query.value)
    return q ? base.filter(b => norm(b.key).includes(q)) : base
  }
  return results.value
})

const resultLabel = computed(() => {
  if (deckOnly.value) return `덱 캐릭터 (${displayResults.value.length})`
  return query.value.trim().length >= 2 ? `검색 결과 (${results.value.length})` : '검색 결과'
})
const emptyMsg = computed(() => {
  if (deckOnly.value) return deckChars.value && deckChars.value.length ? '일치하는 덱 캐릭터 없음' : '현재 덱이 비어있습니다'
  return query.value.trim().length < 2 ? '2글자 이상 입력하세요' : '결과 없음'
})

function onQuery() {
  if (_searchTimer) clearTimeout(_searchTimer)
  _searchTimer = setTimeout(doSearch, 250)
}

async function doSearch() {
  const q = query.value.trim()
  if (q.length < 2) { results.value = []; return }
  const res = await callBk('searchCharacters', q)
  results.value = Array.isArray(res) ? res : []
}

async function toggleDeckOnly() {
  deckOnly.value = !deckOnly.value
  if (deckOnly.value && deckChars.value === null) {
    const dc = await callBk('getDeckCharacters')
    deckChars.value = Array.isArray(dc) ? dc : []
  }
}

// ── per-캐릭터 작업 상태(체크 ON/OFF + 커스텀) 영속 ──
// 닫아도 유지: 사용자가 ON 한 칩은 직접 OFF 하기 전까지 ON으로 고정(반대도 동일).
const CPM_STATE_KEY = 'cpmCharState'
let _loadingChar = false
function _loadCharState(key: string): any {
  try { return (JSON.parse(window.localStorage.getItem(CPM_STATE_KEY) || '{}'))[key] || null } catch { return null }
}
function _saveCharState() {
  if (_loadingChar || !selectedChar.value) return
  try {
    const m = JSON.parse(window.localStorage.getItem(CPM_STATE_KEY) || '{}')
    const checked: Record<string, boolean> = {}
    for (const arr of [coreTags, auxTags, costumeTags, etcTags])
      for (const t of arr.value) checked[norm(t.tag)] = !!t.checked
    m[selectedChar.value] = { checked, custom: customTags.value.map(t => ({ tag: t.tag, checked: !!t.checked })) }
    window.localStorage.setItem(CPM_STATE_KEY, JSON.stringify(m))
  } catch {}
}
function _applyCharState(key: string) {
  const saved = _loadCharState(key)
  if (!saved) return
  const ck = saved.checked || {}
  // 저장된 ON/OFF가 기본값(_defChecked)을 덮어씀 — existing(이미 프롬프트에 있음)은 건드리지 않음
  for (const arr of [coreTags, auxTags, costumeTags, etcTags])
    for (const t of arr.value) { const n = norm(t.tag); if (!t.existing && n in ck) t.checked = !!ck[n] }
  if (Array.isArray(saved.custom)) {
    for (const c of saved.custom) {
      const found = customTags.value.find(t => norm(t.tag) === norm(c.tag))
      if (found) found.checked = c.checked !== false
      else customTags.value.push({ tag: c.tag, checked: c.checked !== false })
    }
  }
}
// 체크/커스텀 변경 시 자동 저장 (로드 중엔 무시)
watch([coreTags, auxTags, costumeTags, etcTags, customTags], () => {
  if (_loadingChar || !selectedChar.value) return
  _saveCharState()
}, { deep: true })

async function selectChar(key: string) {
  // 비동기 로드 전에 이전 캐릭터 상태를 먼저 비운다 (로드 실패 시 이전 태그 잔존 방지)
  _loadingChar = true
  selectedChar.value = key
  presetStatus.value = ''
  status.value = ''
  charCount.value = 0
  coreTags.value = []
  costumeTags.value = []
  etcTags.value = []
  auxTags.value = []
  customTags.value = []
  condRules.value = []
  copyright.value = ''
  const data = await callBk('getCharacterFeatures', key)
  if (!data || data.error) { status.value = '특징 조회 실패'; _loadingChar = false; return }
  charCount.value = data.count || 0
  copyright.value = data.copyright || ''
  addCopyright.value = data.autoAddCopyright !== false
  coreTags.value = (data.core || []).map((t: TagItem) => ({ ...t, checked: _defChecked('core', t) }))
  costumeTags.value = (data.costume || []).map((t: TagItem) => ({ ...t, checked: _defChecked('costume', t) }))
  etcTags.value = (data.etc || []).map((t: TagItem) => ({ ...t, checked: _defChecked('etc', t) }))
  auxTags.value = (data.aux || []).map((t: TagItem) => ({ ...t, checked: _defChecked('aux', t) }))
  customTags.value = (data.custom || []).map((tag: string) => ({ tag, checked: true }))
  // 조건부 규칙 파싱
  condRules.value = []
  if (data.condRulesJson) {
    try {
      const arr = JSON.parse(data.condRulesJson)
      condRules.value = arr.map((r: any) => ({
        condition: r.condition || '', exists: r.exists !== false,
        tags: Array.isArray(r.tags) ? r.tags : [], location: r.location || 'main',
        action: r.action || 'add', enabled: r.enabled !== false,
      }))
    } catch {}
  }
  if (data.hasPreset) presetStatus.value = '★ 저장된 프리셋'
  _applyCharState(key)    // 저장된 작업 상태(ON/OFF + 커스텀) 복원 — 기본값 위에 덮어씀
  _loadingChar = false
}

function chipClass(t: TagItem) { return { off: !t.checked, existing: t.existing } }
function toggleChip(t: TagItem) { if (!t.existing) t.checked = !t.checked }

// ── 전역(모든 캐릭터) 설정: 로드/저장/적용 ──
async function loadGlobals() {
  const p = await callBk('getCharGlobalPrefs')
  const off = new Set((p && p.categoryOff) || ['etc'])
  globalCatOn.core = !off.has('core'); globalCatOn.aux = !off.has('aux')
  globalCatOn.costume = !off.has('costume'); globalCatOn.etc = !off.has('etc')
  globalWordOff.value = (p && Array.isArray(p.wordOff)) ? p.wordOff : []
}
function saveGlobals() {
  const categoryOff = CAT_LIST.map(c => c.key).filter(k => !globalCatOn[k])
  callBk('saveCharGlobalPrefs', JSON.stringify({ categoryOff, wordOff: globalWordOff.value }))
}
function _defChecked(cat: string, t: TagItem): boolean {
  if (t.existing) return false
  if (!globalCatOn[cat]) return false
  if (globalWordOff.value.includes(norm(t.tag))) return false
  return true
}
const _catArr: Record<string, typeof coreTags> = { core: coreTags, aux: auxTags, costume: costumeTags, etc: etcTags }
function toggleGlobalCat(cat: string) {
  globalCatOn[cat] = !globalCatOn[cat]
  const arr = _catArr[cat]
  if (arr) for (const t of arr.value) if (!t.existing) t.checked = _defChecked(cat, t)
  saveGlobals()
}
function addGlobalWord() {
  const w = norm(newGlobalWord.value); newGlobalWord.value = ''
  if (!w || globalWordOff.value.includes(w)) return
  globalWordOff.value.push(w)
  for (const cat of Object.keys(_catArr))
    for (const t of _catArr[cat].value) if (norm(t.tag) === w && !t.existing) t.checked = false
  saveGlobals()
}
function removeGlobalWord(w: string) {
  globalWordOff.value = globalWordOff.value.filter(x => x !== w)
  saveGlobals()
}

function selectAll() {
  for (const t of coreTags.value) if (!t.existing) t.checked = true
  for (const t of auxTags.value) if (!t.existing) t.checked = true
  for (const t of costumeTags.value) if (!t.existing) t.checked = true
  for (const t of etcTags.value) if (!t.existing) t.checked = true
  for (const t of customTags.value) t.checked = true
}
function deselectAll() {
  for (const t of coreTags.value) if (!t.existing) t.checked = false
  for (const t of auxTags.value) if (!t.existing) t.checked = false
  for (const t of costumeTags.value) if (!t.existing) t.checked = false
  for (const t of etcTags.value) if (!t.existing) t.checked = false
  for (const t of customTags.value) t.checked = false
}
function excludeCostume() {
  // 복장(의상 섹션) 태그를 전부 선택 해제 — 눈/머리 등 핵심은 유지
  for (const t of costumeTags.value) t.checked = false
}

async function fetchDanbooru() {
  if (!selectedChar.value) return
  dbLoading.value = true
  const res = await callBk('fetchCharacterTagsOnline', selectedChar.value)
  dbLoading.value = false
  if (!res || res.error || !Array.isArray(res.tags) || !res.tags.length) {
    requestAction('show_toast', { type: 'error', msg: 'danbooru 조회 실패: ' + ((res && res.error) || '결과 없음') })
    return
  }
  // 기존(틀릴 수 있는) 핵심/의상 칩을 danbooru 실제 태그로 교체. 이미 프롬프트에 있는 태그는 제외.
  const already = new Set([...coreTags.value, ...costumeTags.value].filter(t => t.existing).map(t => t.tag.toLowerCase()))
  const fresh = res.tags.filter((t: string) => !already.has(t.toLowerCase()))
  coreTags.value = fresh.map((t: string) => ({ tag: t, existing: false, costume: false, checked: true }))
  costumeTags.value = []
  etcTags.value = []
  auxTags.value = []
  presetStatus.value = `🌐 danbooru ${res.sampled}건 집계`
  requestAction('show_toast', { type: 'success', msg: `danbooru ${fresh.length}개 태그 로드 — 검토 후 '프리셋 저장'` })
}

function addCustom() {
  const txt = newCustom.value.trim()
  if (!txt) return
  const feats = [...coreTags.value, ...auxTags.value, ...costumeTags.value, ...etcTags.value]
  let added = 0, activated = 0, dup = 0
  for (const part of txt.split(',')) {
    const tag = part.trim()
    if (!tag) continue
    const n = norm(tag)
    if (customTags.value.some(t => norm(t.tag) === n)) { dup++; continue }
    const f = feats.find(t => norm(t.tag) === n)
    if (f) {
      // 이미 캐릭터 특징에 있는 태그 → 새로 추가 대신 그 특징을 활성화(체크)
      if (!f.existing && !f.checked) { f.checked = true; activated++ }
      else dup++
      continue
    }
    customTags.value.push({ tag, checked: true }); added++
  }
  newCustom.value = ''
  // 조용한 실패 방지 — 항상 결과를 토스트로 알림
  const parts: string[] = []
  if (added) parts.push(`추가 ${added}`)
  if (activated) parts.push(`특징 활성화 ${activated}`)
  if (dup) parts.push(`이미 있음 ${dup}`)
  requestAction('show_toast', {
    type: (added || activated) ? 'success' : 'info',
    msg: '커스텀 태그 ' + (parts.join(' · ') || '변경 없음'),
  })
}

function checkedTags(): string[] {
  const out: string[] = []
  for (const t of coreTags.value) if (!t.existing && t.checked) out.push(t.tag)
  for (const t of auxTags.value) if (!t.existing && t.checked) out.push(t.tag)
  for (const t of costumeTags.value) if (!t.existing && t.checked) out.push(t.tag)
  for (const t of etcTags.value) if (!t.existing && t.checked) out.push(t.tag)
  for (const t of customTags.value) if (t.checked) out.push(t.tag)
  return out
}

function condRulesJson() {
  const arr = condRules.value
    .filter(r => r.condition.trim() && r.tags.length)
    .map(r => ({
      condition: r.condition.trim(), exists: r.exists, tags: r.tags,
      location: r.location, action: r.action, enabled: r.enabled !== false,
    }))
  return arr.length ? JSON.stringify(arr) : ''
}

function addRule() {
  condRules.value.push({ condition: '', exists: true, tags: [], location: 'main', action: 'add', enabled: true })
}

async function savePreset() {
  if (!selectedChar.value) return
  const r = await callBk('saveCharacterPreset', selectedChar.value, JSON.stringify(checkedTags()), condRulesJson())
  if (r && r.ok) {
    presetStatus.value = '★ 저장 완료'
    // 검색 결과 목록의 ★ 갱신
    const hit = results.value.find(x => x.key === selectedChar.value)
    if (hit) hit.hasPreset = true
    requestAction('show_toast', { type: 'success', msg: `프리셋 저장: ${selectedChar.value}` })
  } else {
    requestAction('show_toast', { type: 'error', msg: '프리셋 저장 실패' })
  }
}

async function deletePreset() {
  if (!selectedChar.value) return
  const r = await callBk('deleteCharacterPreset', selectedChar.value)
  if (r && r.ok) {
    presetStatus.value = '프리셋 삭제됨'
    const hit = results.value.find(x => x.key === selectedChar.value)
    if (hit) hit.hasPreset = false
    requestAction('show_toast', { type: 'info', msg: '프리셋 삭제됨' })
  } else {
    requestAction('show_toast', { type: 'info', msg: (r && r.reason) || '프리셋 없음' })
  }
}

async function apply(includeName: boolean) {
  const tags = checkedTags()
  if (!tags.length && !includeName) {
    requestAction('show_toast', { type: 'info', msg: '선택된 특징이 없습니다' })
    return
  }
  const res = await callBk('applyCharacterPreset', JSON.stringify({
    character: includeName ? selectedChar.value : '',
    tags,
    addCopyright: addCopyright.value,
  }))
  if (res && res.error) {
    requestAction('show_toast', { type: 'error', msg: '적용 실패: ' + res.error })
    return
  }
  requestAction('show_toast', { type: 'success', msg: includeName ? '캐릭터+특징 적용' : '특징 적용' })
  close()
}

function close() { emit('close') }

function onKey(e: KeyboardEvent) { if (e.key === 'Escape') { e.stopPropagation(); close() } }

onMounted(async () => {
  window.addEventListener('keydown', onKey, true)
  await loadGlobals()   // 전역(모든 캐릭터) 설정 로드 — 캐릭터 load 전에 적용되도록
  // 현재 프롬프트의 캐릭터로 검색 프리필
  const bk: any = await getBackend()
  if (bk && bk.getWidgetValue) {
    bk.getWidgetValue('character_input', (val: string) => {
      const first = (val || '').split(',')[0].trim().replace(/\\([()])/g, '$1')
      if (first) { query.value = first; doSearch() }
      if (searchEl.value) searchEl.value.focus()
    })
  } else if (searchEl.value) {
    searchEl.value.focus()
  }
})
onUnmounted(() => { _saveCharState(); window.removeEventListener('keydown', onKey, true) })
</script>

<style scoped>
.cpm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 2200; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.cpm-modal { width: min(1180px, 94vw); height: min(840px, 92vh); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-card); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }

.cpm-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.cpm-header h3 { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.cpm-sub { font-size: 11px; color: var(--text-muted); }
.cpm-close { width: 30px; height: 30px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; font-size: 13px; }
.cpm-close:hover { color: var(--text-primary); border-color: var(--accent); }

.cpm-searchbar { display: flex; gap: 8px; padding: 12px 20px; }
.cpm-search { flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-base); padding: 9px 12px; color: var(--text-primary); font-size: 13px; }
.cpm-search:focus { outline: none; border-color: var(--accent); }
.cpm-deck-btn { background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 11px; font-weight: 700; padding: 0 14px; cursor: pointer; white-space: nowrap; }
.cpm-deck-btn.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

.cpm-body { flex: 1; display: flex; gap: 12px; padding: 0 20px; min-height: 0; }
.cpm-left { width: 320px; display: flex; flex-direction: column; min-height: 0; }
.cpm-left-label { font-size: 11px; font-weight: 700; color: var(--text-secondary); padding: 4px 2px; }
.cpm-list { flex: 1; overflow-y: auto; background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius-base); padding: 4px; }
.cpm-item { display: flex; align-items: center; justify-content: space-between; padding: 7px 9px; border-radius: 6px; cursor: pointer; font-size: 12px; color: var(--text-primary); }
.cpm-item:hover { background: var(--bg-button); }
.cpm-item.active { background: var(--accent); color: #000; font-weight: 700; }
.cpm-item-count { font-size: 10px; color: var(--text-muted); }
.cpm-item.active .cpm-item-count { color: rgba(0,0,0,0.6); }
.cpm-empty { padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px; }

.cpm-right { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.cpm-right-empty { margin: auto; }
.cpm-charhead { display: flex; align-items: baseline; gap: 10px; padding: 4px 0 8px; flex-wrap: wrap; }
.cpm-charname { font-size: 15px; font-weight: 800; color: var(--accent); }
.cpm-charcount { font-size: 11px; color: var(--text-muted); }
.cpm-pstatus { font-size: 11px; color: var(--accent); }

.cpm-copyrow { padding-bottom: 8px; }
.cpm-copychip { background: rgba(139,92,246,0.16); border: 1px solid #8b5cf6; border-radius: 12px; color: #a78bfa; font-size: 11px; font-weight: 700; padding: 4px 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.cpm-copychip:hover { background: rgba(139,92,246,0.28); }
.cpm-copychip.off { background: var(--bg-button); border-color: var(--border); color: var(--text-muted); text-decoration: line-through; }
.cpm-copytag { font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 8px; background: rgba(0,0,0,0.25); text-decoration: none; }

.cpm-selrow { display: flex; gap: 6px; padding-bottom: 8px; flex-wrap: wrap; }
.cpm-sel.db { color: #60a5fa; border-color: #60a5fa; }
.cpm-sel.db:hover { color: #93c5fd; }
.cpm-sel:disabled { opacity: 0.5; cursor: wait; }
.cpm-sel { background: var(--bg-button); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 11px; padding: 5px 12px; cursor: pointer; }
.cpm-sel:hover { color: var(--text-primary); }
.cpm-sel.warn:hover { color: #f87171; border-color: #f87171; }

.cpm-tagscroll { flex: 1; overflow-y: auto; min-height: 80px; border: 1px solid var(--border); border-radius: var(--radius-base); padding: 10px; background: var(--bg-primary); }
.cpm-section-label { font-size: 11px; font-weight: 700; padding: 6px 0 4px; }
.cpm-section-label.core { color: var(--accent); }
.cpm-section-label.costume { color: #fb923c; }
.cpm-section-label.etc { color: #94a3b8; }
.cpm-section-label.aux { color: #38bdf8; }
.cpm-etc-hint { font-size: 9px; font-weight: 400; color: var(--text-muted); margin-left: 4px; }
.cpm-section-label.custom { color: #f59e0b; }
.cpm-regiontoggle { float: right; background: var(--bg-button); border: 1px solid var(--border); border-radius: 8px; color: var(--text-secondary); font-size: 9px; font-weight: 700; padding: 2px 8px; cursor: pointer; }
.cpm-regiontoggle:hover { color: #fb923c; border-color: #fb923c; }
.cpm-region-grp { margin: 2px 0 6px; }
.cpm-region-label { font-size: 10px; font-weight: 700; color: #fb923c; opacity: 0.85; padding: 4px 0 3px; border-top: 1px dashed rgba(251,146,60,0.25); }
.cpm-region-n { color: var(--text-muted); font-weight: 600; }
.cpm-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.cpm-none { font-size: 11px; color: var(--text-muted); }
.cpm-chip { background: var(--accent); color: #000; border: none; border-radius: 12px; padding: 4px 11px; font-size: 11px; font-weight: 700; cursor: pointer; }
.cpm-chip.off { background: var(--bg-button); color: var(--text-muted); text-decoration: line-through; }
.cpm-chip.costume:not(.off) { background: #fb923c; }
.cpm-chip.etc:not(.off) { background: #64748b; }
.cpm-chip.aux:not(.off) { background: #38bdf8; color: #03263a; }

/* 전역(모든 캐릭터) 설정 바 */
.cpm-global { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; }
.cpm-global-head { font-size: 10px; font-weight: 800; color: var(--accent); letter-spacing: 0.5px; margin-bottom: 7px; }
.cpm-global-cats { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 7px; }
.cpm-global-words { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.cpm-global-sub { font-size: 9px; font-weight: 800; color: var(--text-muted); letter-spacing: 0.5px; margin-right: 2px; }
.cpm-gcat { padding: 4px 10px; border-radius: 12px; border: 1px solid #4ade80; background: rgba(74,222,128,0.18); color: #4ade80; font-size: 10px; font-weight: 800; cursor: pointer; }
.cpm-gcat.off { border-color: var(--border); background: var(--bg-button); color: var(--text-muted); }
.cpm-gword-in { flex: 0 1 170px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 5px; padding: 4px 8px; color: var(--text-primary); font-size: 11px; }
.cpm-gword-add { width: 26px; height: 26px; border-radius: 5px; border: 1px solid var(--border); background: var(--bg-button); color: var(--accent); font-weight: 900; cursor: pointer; flex-shrink: 0; }
.cpm-gword-chip { padding: 4px 8px; border-radius: 12px; border: 1px solid #f87171; background: rgba(248,113,113,0.15); color: #fca5a5; font-size: 10px; font-weight: 700; cursor: pointer; }
.cpm-gword-chip:hover { background: rgba(248,113,113,0.3); }
.cpm-chip.cust:not(.off) { background: #f59e0b; color: #000; }
.cpm-chip.existing { background: var(--bg-button); color: var(--text-muted); border: 1px dashed var(--border); cursor: default; text-decoration: none; }
.cpm-exist { margin-left: 4px; opacity: 0.7; }

.cpm-addrow { display: flex; gap: 6px; padding-top: 8px; }
.cpm-addinput { flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 7px 10px; color: var(--text-primary); font-size: 12px; }
.cpm-addinput:focus { outline: none; border-color: var(--accent); }
.cpm-add { background: #fb923c; color: #000; border: none; border-radius: 6px; font-weight: 700; font-size: 11px; padding: 0 14px; cursor: pointer; }

.cpm-presetrow { display: flex; gap: 6px; padding-top: 8px; }
.cpm-psave { background: var(--accent-dim); border: 1px solid var(--accent); border-radius: 6px; color: var(--accent); font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; }
.cpm-pdel { background: rgba(248,113,113,0.1); border: 1px solid #f87171; border-radius: 6px; color: #f87171; font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; }

.cpm-cond { margin-top: 8px; border: 1px solid var(--border); border-radius: var(--radius-base); }
.cpm-cond > summary { padding: 8px 12px; font-size: 11px; font-weight: 700; color: #fbbf24; cursor: pointer; }
.cpm-condbody { padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.cpm-rule { display: flex; gap: 4px; align-items: center; }
.cpm-r-cond { width: 110px; }
.cpm-r-tags { flex: 1; }
.cpm-rule input { background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 5px 7px; color: var(--text-primary); font-size: 11px; }
.cpm-rule input:focus { outline: none; border-color: var(--accent); }
.cpm-r-sel { background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px; padding: 5px 4px; color: var(--text-primary); font-size: 11px; }
.cpm-r-del { background: transparent; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.cpm-r-add { align-self: flex-start; background: var(--bg-button); border: 1px solid var(--border); border-radius: 5px; color: var(--text-secondary); font-size: 11px; padding: 5px 12px; cursor: pointer; }

.cpm-footer { display: flex; align-items: center; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
.cpm-foot-status { font-size: 11px; color: var(--text-muted); }
.cpm-foot-spacer { flex: 1; }
.cpm-apply { border: none; border-radius: var(--radius-base); font-weight: 700; font-size: 12px; padding: 9px 16px; cursor: pointer; }
.cpm-apply.both { background: var(--accent); color: #000; }
.cpm-apply.feat { background: #22c55e; color: #000; }
.cpm-apply.close { background: var(--bg-button); border: 1px solid var(--border); color: var(--text-secondary); }
.cpm-apply:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
