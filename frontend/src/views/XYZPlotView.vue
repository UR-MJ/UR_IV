<template>
  <div class="tab-view">
    <div class="delegate-panel">
      <div class="icon-circle">&#x1F4CA;</div>
      <h2>XYZ Plot</h2>
      <p class="desc">파라미터 조합을 그리드로 비교 생성합니다</p>
      <p class="sub-desc">X, Y, Z 축에 서로 다른 파라미터(모델, 샘플러, CFG 등)를 지정하여<br/>조합별 결과를 한눈에 비교할 수 있습니다.</p>
      <button class="btn-action" @click="openXYZPlot">
        XYZ Plot 열기
      </button>
    </div>
  </div>
</template>

<script setup>
import { requestAction } from '../stores/widgetStore.js'

function openXYZPlot() {
  requestAction('open_xyz_plot')
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
  max-width: 420px;
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
