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

watch(route, (r) => {
  currentTab.value = r.name
})

const emit = defineEmits(['tab-changed'])

function switchTo(tab) {
  currentTab.value = tab.name
  router.push(tab.path)
  requestAction('vue_tab_switch', { tab: tab.name })
  emit('tab-changed', tab.name)
}
</script>

<style scoped>
.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 6px 12px;
  background: #0A0A0A;
  border-bottom: 1px solid #1A1A1A;
  justify-content: center;
  align-items: center;
}
.tab-btn {
  padding: 6px 14px;
  background: #181818;
  border: 1px solid #1A1A1A;
  border-radius: 6px;
  color: #585858;
  font-size: 11px;
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
</style>
