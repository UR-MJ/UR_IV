<template>
  <nav class="nav-rail" :class="{ collapsed }" aria-label="탭 내비게이션">
    <!-- 브랜드 행 — 레일의 '여기가 위' 표시. 접히면 도장만 남는다. -->
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <span v-if="!collapsed" class="brand-name">AI STUDIO PRO</span>
    </div>

    <div class="rail-scroll">
      <template v-for="group in groups" :key="group.id">
        <!-- 접히면 묶음 라벨을 읽을 자리가 없다 — 대신 선으로 경계만 남긴다.
             묶음이 통째로 사라지면 아이콘 15개가 한 덩어리로 보인다. -->
        <div v-if="collapsed" class="grp-rule" aria-hidden="true"></div>
        <div v-else class="grp">{{ group.label }}</div>

        <template v-for="tab in group.tabs" :key="tab.name">
          <button
            type="button"
            class="nav"
            :class="{ on: currentTab === tab.name }"
            :aria-current="currentTab === tab.name ? 'page' : undefined"
            :aria-label="tab.title"
            @click="switchTo(tab)"
            @pointerenter="showTip(tab.title, $event)"
            @pointerleave="hideTip"
            @focus="showTip(tab.title, $event)"
            @blur="hideTip"
          >
            <span class="ico"><Icon :name="tab.icon" size="17" /></span>
            <span v-if="!collapsed" class="t">{{ tab.title }}</span>
          </button>

          <!-- 서랍: **활성 탭만** 자기 하위 항목을 펼친다.
               전부 펼치면 목록이 두 배가 되고, 그러면 세로 레일을 쓸 이유가 없다. -->
          <template v-if="!collapsed && currentTab === tab.name">
            <button
              v-for="section in sections"
              :key="section.id"
              type="button"
              class="sub"
              :class="{ open: openSection === section.id }"
              @click="goSection(section)"
            >
              <span class="t">{{ section.label }}</span>
              <span v-if="badgeText(section)" class="n">{{ badgeText(section) }}</span>
            </button>
          </template>
        </template>
      </template>
    </div>

    <div class="rail-foot">
      <button
        type="button"
        class="rail-toggle"
        :aria-label="collapsed ? '레일 펼치기' : '레일 접기'"
        :aria-expanded="!collapsed"
        @click="toggleCollapsed"
        @pointerenter="showTip(collapsed ? '레일 펼치기' : '레일 접기', $event)"
        @pointerleave="hideTip"
      >
        <Icon :name="collapsed ? 'chevron-right' : 'chevron-left'" size="16" />
      </button>
    </div>
  </nav>

  <!-- 접힌 상태의 이름표. 레일은 세로 스크롤을 하므로 안에 두면 잘린다
       (overflow-y: auto 는 x 를 visible 로 둘 수 없다) — EditorToolbar 와 같은 방식. -->
  <Teleport to="body">
    <div v-if="tip" class="nr-tip" :style="{ top: tip.top + 'px', left: tip.left + 'px' }">{{ tip.label }}</div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 왼쪽 세로 탭 레일.
 *
 * 왜 가로 바가 아니라 세로냐: 탭이 15개다. 가로로 늘어놓으면 1280px 창에서 줄이
 * 바뀌거나 잘리고, 무엇보다 **묶음 라벨을 읽을 자리가 없다**. 세로는 위에서
 * 아래로 읽히니 묶음이 공짜로 성립하고, 상단 60px 헤더가 통째로 사라져 무대가
 * 그만큼 커진다.
 *
 * 대신 가로 196px 을 먹으므로 접을 수 있어야 한다(196 ↔ 52). 접힌 상태의 이름은
 * 호버 이름표가 책임진다.
 *
 * 묶음은 '하는 일'로 **고정**하고, 묶음 안의 순서는 사용자가 Settings 에서 정한
 * 순서를 따른다. 안 그러면 탭 순서 설정 기능과 싸운다. (가로 바 시절의 규칙을
 * 그대로 이어받았다.)
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { routes } from '../router.js'
import { requestAction, state } from '../stores/widgetStore.js'
import { sectionsFor, type NavSection } from '../utils/navSections'

interface RailTab {
  /** route name, 또는 네이티브 탭 id */
  name: string
  title: string
  /** 네이티브 탭은 라우트가 없다 */
  path?: string
  native?: boolean
  icon: string
}

/**
 * 아이콘 이름은 `icons/index.ts` 에 **있는 것만** 쓴다.
 * 없는 이름은 예외 없이 빈 <svg> 로 렌더돼 버튼이 통째로 비어 보인다.
 * (tests/test_nav_rail_contract.py 가 정적으로 잡는다.)
 */
const ICON_BY_TAB: Record<string, string> = {
  t2i: 'type', i2i: 'image', inpaint: 'brush', event: 'sparkles',
  search: 'search', xyz: 'grid', creator: 'cards',
  editor: 'pencil', batch: 'layers',
  gallery: 'folder', fav: 'star', png: 'info',
  settings: 'settings', web: 'globe', backend: 'cpu',
}
/** 목록에 없는 탭이 생겨도 빈 칸이 되지 않게 하는 기본값. */
const FALLBACK_ICON = 'square'

/** 라우트가 아니라 PyQt 쪽 화면. 전환은 `native_tab_switch` 액션이 한다. */
const NATIVE_TABS: RailTab[] = [
  { name: 'web', title: 'Web', native: true, icon: ICON_BY_TAB.web },
  { name: 'backend', title: 'Backend', native: true, icon: ICON_BY_TAB.backend },
]

/**
 * 묶음과 순서 — 승인된 디자인 캔버스 원문.
 * `names` 는 사용자가 순서를 안 건드렸을 때의 **기본 순서**이기도 하다.
 */
const GROUPS: { id: string; label: string; names: string[] }[] = [
  { id: 'make', label: '생성', names: ['t2i', 'i2i', 'inpaint', 'event', 'search', 'xyz', 'creator'] },
  { id: 'edit', label: '편집', names: ['editor', 'batch'] },
  { id: 'lib', label: '라이브러리', names: ['gallery', 'fav', 'png'] },
  { id: 'sys', label: '시스템', names: ['settings', 'web', 'backend'] },
]
const GROUPED_NAMES = new Set(GROUPS.flatMap((g) => g.names))

const router = useRouter()
const route = useRoute()

const allTabs: RailTab[] = [
  ...routes.map((r: any) => ({
    name: r.name as string,
    title: (r.meta?.title || r.name) as string,
    path: r.path as string,
    icon: ICON_BY_TAB[r.name] || FALLBACK_ICON,
  })),
  ...NATIVE_TABS,
]

const currentTab = ref<string>(String(route.name || 't2i'))
watch(route, (r) => { currentTab.value = String(r.name || '') })

// ── 사용자 지정 탭 순서 ────────────────────────────────────────────────
// Settings 는 탭 **제목** 배열을 localStorage['tabOrder'] 에 넣는다.
// 'storage' 이벤트는 다른 창의 변경만 알려주므로, 같은 창의 변경은
// SettingsView 가 쏘는 'tabOrderChanged' 커스텀 이벤트로 받는다.
const userOrder = ref<string[]>(readUserOrder())
function readUserOrder(): string[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    return Array.isArray(saved) ? saved : []
  } catch { return [] }
}
function _onTabOrderChange() {
  const next = readUserOrder()
  if (JSON.stringify(next) !== JSON.stringify(userOrder.value)) userOrder.value = next
}
function _onStorageEvent(e: StorageEvent) {
  if (e.key === 'tabOrder' || e.key === null /* clear */) _onTabOrderChange()
}

const groups = computed(() => {
  const byName: Record<string, RailTab> = {}
  allTabs.forEach((t) => { byName[t.name] = t })

  return GROUPS.map((g) => {
    const names = [...g.names]
    // 어느 묶음에도 안 적힌 탭(나중에 추가된 라우트)은 조용히 사라지면 안 된다.
    // 마지막 묶음 끝에 붙여 최소한 눈에는 띄게 한다.
    if (g.id === 'sys') names.push(...allTabs.filter((t) => !GROUPED_NAMES.has(t.name)).map((t) => t.name))

    const tabs = names.map((n) => byName[n]).filter(Boolean)
    // 사용자가 정한 순서가 있으면 그것이 이긴다. 저장 안 된 탭은 캔버스 순서를 유지한 채 뒤로.
    const rank = new Map(tabs.map((t, i) => {
      const saved = userOrder.value.indexOf(t.title)
      return [t.name, saved >= 0 ? saved : 1000 + i] as const
    }))
    tabs.sort((a, b) => (rank.get(a.name) ?? 0) - (rank.get(b.name) ?? 0))
    return { ...g, tabs }
  }).filter((g) => g.tabs.length > 0)
})

// ── 전환 ───────────────────────────────────────────────────────────────
const emit = defineEmits<{
  'tab-changed': [name: string]
  'go-section': [section: NavSection]
}>()

function switchTo(tab: RailTab) {
  currentTab.value = tab.name
  openSection.value = ''
  if (tab.native) {
    requestAction('native_tab_switch', { tab: tab.name })
  } else {
    router.push(tab.path as string)
    requestAction('vue_tab_switch', { tab: tab.name })
  }
  emit('tab-changed', tab.name)
}

/** Ctrl+Tab / Ctrl+Shift+Tab — 보이는 순서(묶음 포함) 그대로 다음/이전 탭. */
function _onNavigate(e: Event) {
  const direction = (e as CustomEvent).detail?.direction || 1
  const flat = groups.value.flatMap((g) => g.tabs)
  if (!flat.length) return
  const cur = flat.findIndex((t) => t.name === currentTab.value)
  if (cur < 0) { switchTo(flat[0]); return }
  let next = cur + direction
  if (next < 0) next = flat.length - 1
  if (next >= flat.length) next = 0
  switchTo(flat[next])
}

// ── 서랍 ───────────────────────────────────────────────────────────────
const sections = computed(() => sectionsFor(currentTab.value))
/** 지금 열려 있는(= 방금 찾아간) 섹션. 탭이 바뀌면 초기화된다. */
const openSection = ref('')
watch(currentTab, () => { openSection.value = '' })

function goSection(section: NavSection) {
  openSection.value = section.id
  emit('go-section', section)
}

/**
 * 오른쪽 숫자.
 *
 * `approxTokens` 는 `PromptPanel.vue` 의 같은 이름 함수와 **규칙이 같아야 한다** —
 * 레일 숫자와 카드 숫자가 다르면 어느 쪽을 믿어야 할지 알 수 없다. 그 쪽은 아직
 * 로컬 함수라 가져다 쓸 수 없어 규칙만 옮겨 적었고, 둘이 갈라지는지는
 * tests/test_nav_rail_contract.py 가 본다.
 */
function approxTokens(text: unknown): number {
  const raw = String(text ?? '')
  if (!raw.trim()) return 0
  const chunks = raw.split(',').map((s) => s.trim()).filter(Boolean)
  let total = 0
  for (const c of chunks) total += c.split(/\s+/).filter(Boolean).length
  return total + Math.max(0, chunks.length - 1)
}

function badgeText(section: NavSection): string {
  if (section.badge === 'tokens') {
    const n = approxTokens(state.values.total_prompt_display)
    return n ? String(n) : ''
  }
  if (section.badge === 'steps-cfg') {
    const steps = String(state.values.steps_input ?? '').trim()
    const cfg = String(state.values.cfg_input ?? '').trim()
    if (!steps && !cfg) return ''
    return `${steps || '–'} · ${cfg || '–'}`
  }
  return ''
}

// ── 접기 ───────────────────────────────────────────────────────────────
const COLLAPSE_KEY = 'navRailCollapsed'
const collapsed = ref(readCollapsed())
function readCollapsed(): boolean {
  try { return window.localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false }
}
function toggleCollapsed() {
  collapsed.value = !collapsed.value
  hideTip()
  try { window.localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0') } catch {}
}

// ── 이름표 ─────────────────────────────────────────────────────────────
const tip = ref<{ label: string; top: number; left: number } | null>(null)
function showTip(label: string, event: Event) {
  // 펼쳐져 있으면 이름이 이미 보인다 — 이름표는 접혔을 때만 뜻이 있다.
  if (!collapsed.value) return
  const el = event.currentTarget as HTMLElement | null
  if (!el) return
  const rect = el.getBoundingClientRect()
  tip.value = { label, top: Math.round(rect.top + rect.height / 2), left: Math.round(rect.right + 8) }
}
function hideTip() { tip.value = null }

onMounted(() => {
  window.addEventListener('storage', _onStorageEvent)
  window.addEventListener('tabOrderChanged', _onTabOrderChange)
  window.addEventListener('navRailNavigate', _onNavigate)
})
onUnmounted(() => {
  window.removeEventListener('storage', _onStorageEvent)
  window.removeEventListener('tabOrderChanged', _onTabOrderChange)
  window.removeEventListener('navRailNavigate', _onNavigate)
})
</script>

<style scoped>
.nav-rail {
  width: 196px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  border-right: 1px solid var(--rule);
  z-index: 100;
  transition: width 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.nav-rail.collapsed { width: 52px; }

/* ── 브랜드 ── */
.brand {
  display: flex; align-items: center; gap: 10px;
  height: 52px; padding: 0 var(--sp-4);
  flex-shrink: 0;
}
.nav-rail.collapsed .brand { padding: 0; justify-content: center; }
.brand-mark {
  width: 20px; height: 20px; border-radius: 6px;
  background: var(--accent);
  flex-shrink: 0;
}
.brand-name {
  font-size: var(--fs-body);
  font-weight: var(--fw-bold);
  color: var(--text-primary);
  /* 화면 이름만 영문 대문자다 — 대문자는 글자 사이가 좁아 보여 트래킹이 필요하다.
     CreatorStudioView 의 .eyebrow 와 같은 값. (자간은 px 이 아니라 em 으로 준다 —
     글자 크기가 바뀌어도 비율이 유지되고, tests/test_ui_copy_contract.py 가 이를 본다.) */
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.rail-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  /* 하단 고정 VRAM 바(22px)에 마지막 줄이 가리지 않도록 */
  padding-bottom: var(--sp-6);
}

/* ── 묶음 라벨 ── */
.grp {
  font-size: var(--fs-label);
  font-weight: var(--fw-medium);
  color: var(--text-muted);
  /* 캔버스는 0.4px 였지만 이 라벨은 한글(생성·편집·라이브러리·시스템)이다.
     한글은 글자 자체에 여백이 있어 자간을 벌리면 흐트러진다 — 트래킹은 대문자
     영문 이름 자리에만 준다(tests/test_ui_copy_contract.py). */
  letter-spacing: 0;
  padding: 0 var(--sp-4);
  margin: var(--sp-4) 0 var(--sp-1);
  white-space: nowrap;
}
.grp-rule {
  height: 1px; background: var(--rule);
  margin: var(--sp-3) 11px var(--sp-2);
}

/* ── 탭 행 ── */
.nav {
  display: flex; align-items: center; gap: var(--sp-3);
  height: 30px; padding: 0 var(--sp-3);
  margin: 0 var(--sp-2);
  width: calc(100% - var(--sp-4));
  border: none; border-radius: var(--radius-base);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--fs-body);
  text-align: left; white-space: nowrap; overflow: hidden;
  cursor: pointer;
}
/* 활성 행이 '한 단 올라온 면'을 독점한다 — 호버는 글자 밝기만 올린다.
   둘 다 면을 쓰면 지나가는 손이 활성 탭처럼 보인다. */
.nav:hover { color: var(--text-primary); }
.nav:hover .ico { color: var(--text-secondary); }
.nav.on {
  background: var(--bg-button);
  color: var(--text-primary);
  font-weight: var(--fw-bold);
}
.nav.on:hover { background: var(--bg-button-hover); }
.nav .ico { display: flex; color: var(--text-muted); }
.nav.on .ico { color: var(--text-secondary); }
.nav .t { flex: 1; overflow: hidden; text-overflow: ellipsis; }

.nav-rail.collapsed .nav {
  width: 30px; height: 30px;
  margin: 0 11px; padding: 0;
  justify-content: center;
}

/* ── 하위 행(서랍) ── */
.sub {
  position: relative;
  display: flex; align-items: center; gap: var(--sp-3);
  height: 26px; padding: 0 var(--sp-3) 0 40px;
  margin: 0 var(--sp-2);
  width: calc(100% - var(--sp-4));
  border: none; border-radius: var(--radius-base);
  background: transparent;
  color: var(--text-muted);
  font-size: var(--fs-meta);
  text-align: left; white-space: nowrap;
  cursor: pointer;
}
.sub:hover { color: var(--text-secondary); }
.sub.open { background: var(--accent-dim); color: var(--text-primary); }
/* 지금 보고 있는 섹션임을 왼쪽 막대로 — 배경만으로는 '선택'과 '호버'가 헷갈린다 */
.sub.open::before {
  content: '';
  position: absolute; left: 24px; top: 6px; bottom: 6px;
  width: 2px; border-radius: 1px;
  background: var(--accent);
}
.sub .t { flex: 1; overflow: hidden; text-overflow: ellipsis; }

/* 오른쪽 정렬 숫자 — 토큰 수 · 스텝·CFG 처럼 '지금 값'을 보여준다 */
.nav .n, .sub .n {
  margin-left: auto;
  font-size: var(--fs-label);
  color: var(--text-muted);
}

/* ── 접기 버튼 ── */
.rail-foot {
  flex-shrink: 0;
  display: flex; justify-content: flex-end;
  padding: var(--sp-1) 0;
  border-top: 1px solid var(--rule);
}
.nav-rail.collapsed .rail-foot { justify-content: center; }
.rail-toggle {
  width: 30px; height: 30px;
  margin: 0 11px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: var(--radius-base);
  color: var(--text-muted);
  cursor: pointer;
}
.rail-toggle:hover { background: var(--bg-button); color: var(--text-primary); }
</style>

<style>
/* Teleport 로 body 에 붙으므로 scoped 가 아니다 — 이름을 nr- 로 좁게 유지한다. */
.nr-tip {
  position: fixed;
  transform: translateY(-50%);
  padding: var(--sp-1) var(--sp-2);
  background: var(--bg-card);
  border: 1px solid var(--edge);
  border-radius: var(--radius-base);
  color: var(--text-primary);
  font-size: var(--fs-body);
  font-weight: var(--fw-medium);
  white-space: nowrap;
  pointer-events: none;
  z-index: 3000;
}
</style>
