<template>
  <div class="tab-bar">
    <button
      v-for="tab in tabs"
      :key="tab.name"
      class="tab-btn"
      :class="{ active: currentTab === tab.name }"
      @click="switchTo(tab)"
    >
      {{ tab.title }}
    </button>
    <!-- 네이티브 PyQt 탭 (클릭 시 Python에 요청) -->
    <button
      v-for="ntab in nativeTabs"
      :key="ntab.id"
      class="tab-btn native"
      :class="{ active: currentTab === ntab.id }"
      @click="switchToNative(ntab.id)"
    >
      {{ ntab.title }}
    </button>
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

watch(route, (r) => {
  currentTab.value = r.name
})

function switchTo(tab) {
  currentTab.value = tab.name
  router.push(tab.path)
  // Python에 알림 (left_stack 전환용)
  requestAction('vue_tab_switch', { tab: tab.name })
}

function switchToNative(id) {
  currentTab.value = id
  requestAction('native_tab_switch', { tab: id })
}
</script>

<style scoped>
.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  background: #0A0A0A;
  border-bottom: 1px solid #1A1A1A;
  justify-content: center;
}

.tab-btn {
  padding: 8px 16px;
  background: #181818;
  border: 1px solid #1A1A1A;
  border-radius: 8px;
  color: #585858;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tab-btn:hover {
  background: #222;
  color: #E8E8E8;
}
.tab-btn.active {
  background: #1A1A1A;
  color: #E8E8E8;
  border-color: #E2B340;
}
.tab-btn.native {
  border-style: dashed;
}
</style>
