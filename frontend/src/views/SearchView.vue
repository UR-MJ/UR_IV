<template>
  <div class="tab-view">
    <div class="delegate-panel">
      <div class="icon-circle">&#x1F50D;</div>
      <h2>Danbooru 검색</h2>
      <p class="desc">검색은 Python 검색 탭에서 실행됩니다</p>
      <p class="sub-desc">Danbooru 데이터셋 검색은 pandas/parquet 기반으로<br/>Python 네이티브 환경에서 처리됩니다.</p>
      <button class="btn-action" @click="openNativeSearch">
        Python 검색 탭 열기
      </button>
    </div>
  </div>
</template>

<script setup>
import { requestAction } from '../stores/widgetStore.js'

function openNativeSearch() {
  requestAction('open_native_search')
}
</script>

<style scoped>
.tab-view {
  width: 100%;
  height: 100%;
  background: #0A0A0A;
  color: #E8E8E8;
  display: flex;
  align-items: center;
  justify-content: center;
}
.delegate-panel {
  text-align: center;
  max-width: 400px;
  padding: 32px;
}
.icon-circle {
  font-size: 36px;
  margin-bottom: 16px;
}
.delegate-panel h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 10px 0;
  color: #E8E8E8;
}
.desc {
  font-size: 14px;
  color: #E8E8E8;
  margin: 0 0 8px 0;
}
.sub-desc {
  font-size: 12px;
  color: #585858;
  margin: 0 0 24px 0;
  line-height: 1.5;
}
.btn-action {
  background: transparent;
  border: 1px solid #E2B340;
  color: #E2B340;
  padding: 10px 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s;
}
.btn-action:hover {
  background: rgba(226, 179, 64, 0.1);
}
</style>
