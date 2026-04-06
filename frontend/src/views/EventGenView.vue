<template>
  <div class="tab-view">
    <div class="delegate-panel">
      <div class="icon-circle">&#x1F3B2;</div>
      <h2>이벤트 생성</h2>
      <p class="desc">캐릭터 조합 기반 이벤트 이미지를 자동 생성합니다</p>
      <ul class="feature-list">
        <li>Danbooru 캐릭터 데이터셋 기반 자동 태그 조합</li>
        <li>다수의 캐릭터를 무작위로 조합하여 프롬프트 생성</li>
        <li>배치 방식으로 연속 생성 가능</li>
      </ul>
      <button class="btn-action" @click="openEventGen">
        이벤트 생성 시작
      </button>
    </div>
  </div>
</template>

<script setup>
import { requestAction } from '../stores/widgetStore.js'

function openEventGen() {
  requestAction('open_event_gen')
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
  max-width: 440px;
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
  margin: 0 0 16px 0;
}
.feature-list {
  text-align: left;
  list-style: none;
  padding: 0;
  margin: 0 0 24px 0;
}
.feature-list li {
  font-size: 12px;
  color: #585858;
  padding: 4px 0;
  line-height: 1.5;
}
.feature-list li::before {
  content: '\2022';
  color: #E2B340;
  margin-right: 8px;
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
