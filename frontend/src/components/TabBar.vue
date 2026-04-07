<template>
  <div class="tab-bar">
    <!-- Vue 탭 -->
    <button v-for="tab in tabs" :key="tab.name"
      class="tab-btn" :class="{ active: currentTab === tab.name }"
      @click="switchTo(tab)"
    >{{ tab.title }}</button>

    <div class="sep" />

    <!-- 네이티브 탭 (PyQt) -->
    <button v-for="ntab in nativeTabs" :key="ntab.id"
      class="tab-btn native" :class="{ active: currentTab === ntab.id }"
      @click="switchToNative(ntab.id)"
    >{{ ntab.title }}</button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { routes } from '../router.js'
import { requestAction } from '../stores/widgetStore.js'

const router = useRouter()
const route = useRoute()
const currentTab = ref(route.name || 't2i')

const tabs = routes.map(r => ({
  name: r.name,
  title: r.meta?.title || r.name,
  path: r.path,
}))

const nativeTabs = [
  { id: 'editor', title: 'Editor' },
  { id: 'web', title: 'Web' },
  { id: 'backend', title: 'Backend UI' },
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
  display: flex; flex-wrap: wrap; gap: 5px; padding: 6px 12px;
  background: #0A0A0A; justify-content: center; align-items: center;
  flex-shrink: 0;
}
.sep { width: 1px; height: 20px; background: #2A2A2A; margin: 0 4px; }
.tab-btn {
  padding: 6px 14px; background: #181818; border: 1px solid #1A1A1A;
  border-radius: 6px; color: #585858; font-size: 11px; font-weight: 700;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.tab-btn:hover { background: #222; color: #E8E8E8; }
.tab-btn.active { background: #1A1A1A; color: #E8E8E8; border-color: #E2B340; }
.tab-btn.native { border-style: dashed; }
</style>
