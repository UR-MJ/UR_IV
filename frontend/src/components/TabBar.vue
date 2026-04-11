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

<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { routes } from '../router.js'
import { requestAction } from '../stores/widgetStore.js'

const router = useRouter()
const route = useRoute()
const currentTab = ref(route.name || 't2i')

const allTabs = routes.map(r => ({
  name: r.name,
  title: r.meta?.title || r.name,
  path: r.path,
}))

// localStorage에서 탭 순서 로드
const tabs = ref(sortTabs())
function sortTabs() {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0) {
      const byTitle = {}
      allTabs.forEach(t => { byTitle[t.title] = t })
      const ordered = saved.map(title => byTitle[title]).filter(Boolean)
      // 저장 안 된 새 탭 추가
      allTabs.forEach(t => { if (!ordered.find(o => o.name === t.name)) ordered.push(t) })
      return ordered
    }
  } catch {}
  return [...allTabs]
}
// 순서 변경 감시
setInterval(() => {
  try {
    const saved = JSON.parse(window.localStorage.getItem('tabOrder') || '[]')
    if (saved.length > 0 && JSON.stringify(saved) !== JSON.stringify(tabs.value.map(t => t.title))) {
      tabs.value = sortTabs()
    }
  } catch {}
}, 2000)

const nativeTabs = [
  { id: 'web', title: 'Web' },
  { id: 'backend', title: 'Backend' },
]

watch(route, (r) => { currentTab.value = r.name })

const emit = defineEmits(['tab-changed'])

function switchTo(tab) {
  currentTab.value = tab.name
  router.push(tab.path)
  requestAction('vue_tab_switch', { tab: tab.name })
  emit('tab-changed', tab.name)
}

function switchToNative(id) {
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
