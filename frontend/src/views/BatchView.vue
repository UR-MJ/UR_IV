<template>
  <div class="tab-view">
    <div class="batch-container">
      <div class="section-card">
        <div class="section-icon">&#x1F4E6;</div>
        <h3>배치 처리</h3>
        <p>여러 프롬프트를 순차적으로 실행하여<br/>대량의 이미지를 한 번에 생성합니다.</p>
        <button class="btn-action" @click="openBatch">배치 처리 열기</button>
      </div>

      <div class="divider"></div>

      <div class="section-card">
        <div class="section-icon">&#x1F50D;</div>
        <h3>업스케일</h3>
        <p>생성된 이미지를 고해상도로<br/>업스케일합니다.</p>
        <button class="btn-action" @click="openUpscale">업스케일 열기</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { requestAction } from '../stores/widgetStore.js'

function openBatch() {
  requestAction('open_batch')
}

function openUpscale() {
  requestAction('open_upscale')
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
.batch-container {
  display: flex;
  gap: 32px;
  align-items: center;
  padding: 32px;
}
.divider {
  width: 1px;
  height: 180px;
  background: #1A1A1A;
}
.section-card {
  text-align: center;
  max-width: 260px;
}
.section-icon {
  font-size: 32px;
  margin-bottom: 12px;
}
.section-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #E8E8E8;
}
.section-card p {
  font-size: 12px;
  color: #585858;
  line-height: 1.5;
  margin: 0 0 20px 0;
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
