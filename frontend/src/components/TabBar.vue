<template>
  <nav class="tab-bar">
    <div class="tab-track">
      <button v-for="tab in tabs" :key="tab.name"
        class="tab-pill" :class="{ active: currentTab === tab.name }"
        @click="switchTo(tab)"
      >{{ tab.title }}</button>

      <div class="pill-sep" />

      <button v-for="ntab in nativeTabs" :key="ntab.id"
        class="tab-pill native" :class="{ active: currentTab === ntab.id }"
        @click="switchToNative(ntab.id)"
      >{{ ntab.title }}</button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { routes } from '../router.js'
import { requestAction } from '../stores/widgetStore.js'

interface Tab { name: string; title: string; path: string }

const router = useRouter()
const route = useRoute()
const currentTab = ref<string>(String(route.name || 't2i'))

const allTabs: Tab[] = routes.map((r: any) => ({
  name: r.name,
  title: r.meta?.title || r.name,
  path: r.path,
}))

// localStorage에서 탭 순서 로드
const tabs = ref<Tab[]>(sortTabs())
function sortTabs(): Tab[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0) {
      const byTitle: Record<string, Tab> = {}
      allTabs.forEach(t => { byTitle[t.title] = t })
      const ordered = saved.map((title: string) => byTitle[title]).filter(Boolean) as Tab[]
      // 저장 안 된 새 탭 추가
      allTabs.forEach(t => { if (!ordered.find(o => o.name === t.name)) ordered.push(t) })
      return ordered
    }
  } catch {}
  return [...allTabs]
}
// 순서 변경 감시 — storage 이벤트로 즉시 반영 (2초 폴링 대체)
// localStorage는 다른 탭/창의 변경만 'storage' 이벤트 발생시키므로,
// 같은 창에서의 변경도 감지하려면 SettingsView가 'tabOrderChanged' 커스텀 이벤트를 dispatch해야 함.
function _onTabOrderChange() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0 && JSON.stringify(saved) !== JSON.stringify(tabs.value.map(t => t.title))) {
      tabs.value = sortTabs()
    }
  } catch {}
}
function _onStorageEvent(e: StorageEvent) {
  if (e.key === 'tabOrder' || e.key === null /* clear */) _onTabOrderChange()
}
// Ctrl+Tab / Ctrl+Shift+Tab — 다음/이전 탭으로 이동
function _onTabNavigate(e: Event) {
  const direction = (e as CustomEvent).detail?.direction || 1
  const allTabsArr = tabs.value
  if (!allTabsArr.length) return
  const curIdx = allTabsArr.findIndex(t => t.name === currentTab.value)
  if (curIdx < 0) { switchTo(allTabsArr[0]); return }
  let nextIdx = curIdx + direction
  if (nextIdx < 0) nextIdx = allTabsArr.length - 1
  if (nextIdx >= allTabsArr.length) nextIdx = 0
  switchTo(allTabsArr[nextIdx])
}

onMounted(() => {
  window.addEventListener('storage', _onStorageEvent)
  window.addEventListener('tabOrderChanged', _onTabOrderChange)
  window.addEventListener('tabBarNavigate', _onTabNavigate)
})
onUnmounted(() => {
  window.removeEventListener('storage', _onStorageEvent)
  window.removeEventListener('tabOrderChanged', _onTabOrderChange)
  window.removeEventListener('tabBarNavigate', _onTabNavigate)
})

const nativeTabs = [
  { id: 'web', title: 'Web' },
  { id: 'backend', title: 'Backend' },
]

watch(route, (r) => { currentTab.value = String(r.name || '') })

const emit = defineEmits<{ 'tab-changed': [name: string] }>()

function switchTo(tab: Tab) {
  currentTab.value = tab.name
  router.push(tab.path)
  requestAction('vue_tab_switch', { tab: tab.name })
  emit('tab-changed', tab.name)
}

function switchToNative(id: string) {
  currentTab.value = id
  requestAction('native_tab_switch', { tab: id })
  emit('tab-changed', id)
}
</script>

<style scoped>
.tab-bar {
  width: 100%; display: flex; justify-content: center; align-items: center;
  padding: 8px 16px;
}
.tab-track {
  display: flex; gap: 3px; padding: 3px;
  background: #0A0A0A; border: 1px solid var(--border);
  border-radius: 28px;
}
.pill-sep { width: 1px; background: #2A2A2A; margin: 4px 2px; }
.tab-pill {
  padding: 7px 16px; background: transparent; border: none;
  border-radius: 22px; color: #585858; font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all 0.2s; white-space: nowrap;
}
.tab-pill:hover { color: #B0B0B0; background: rgba(255,255,255,0.03); }
.tab-pill.active {
  background: var(--accent); color: #000; font-weight: 800;
  box-shadow: 0 2px 8px rgba(250, 204, 21, 0.25);
}
.tab-pill.native { font-style: italic; opacity: 0.7; }
.tab-pill.native.active { opacity: 1; }
</style>
