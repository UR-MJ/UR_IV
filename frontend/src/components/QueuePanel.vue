<template>
  <div class="queue-panel">
    <div class="queue-header">
      <span class="title">대기열 ({{ items.length }})</span>
      <div class="queue-actions">
        <button class="btn" @click="$emit('add-current')">+ 현재 추가</button>
        <button class="btn" @click="clearAll" v-if="items.length">전체 삭제</button>
      </div>
    </div>
    <div class="queue-list" v-if="items.length">
      <div v-for="(item, i) in items" :key="i" class="queue-item">
        <span class="q-idx">#{{ i + 1 }}</span>
        <span class="q-text">{{ item.prompt?.substring(0, 60) || '프롬프트 없음' }}...</span>
        <button class="q-rm" @click="items.splice(i, 1)">×</button>
      </div>
    </div>
    <div class="queue-empty" v-else>
      대기열이 비어있습니다
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineEmits(['add-current'])
const items = ref([])

function clearAll() { items.value = [] }

// TODO: Python에서 대기열 아이템 추가/제거 시 bridge로 동기화
defineExpose({ items })
</script>

<style scoped>
.queue-panel {
  background: #0D0D0D;
  /* border 제거 */
  max-height: 180px;
  display: flex;
  flex-direction: column;
}
.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid #111;
  flex-shrink: 0;
}
.title { color: #787878; font-size: 12px; font-weight: 600; }
.queue-actions { display: flex; gap: 6px; }
.btn {
  padding: 3px 10px;
  background: #181818;
  border: none;
  border-radius: 4px;
  color: #585858;
  font-size: 10px;
  cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.queue-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
}
.queue-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  font-size: 11px;
  border-bottom: 1px solid #111;
}
.q-idx { color: #E2B340; font-weight: 600; font-size: 10px; }
.q-text { color: #787878; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.q-rm { background: none; border: none; color: #E05252; cursor: pointer; font-size: 14px; padding: 0 4px; }
.queue-empty {
  padding: 12px;
  text-align: center;
  color: #383838;
  font-size: 11px;
}
</style>
