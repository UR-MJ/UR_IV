<template>
  <div class="settings-view">
    <div class="settings-scroll">
      <h3 class="section-title">일반</h3>
      <div class="setting-row">
        <span class="label">테마</span>
        <span class="value">모던</span>
      </div>

      <h3 class="section-title">API</h3>
      <div class="setting-row">
        <span class="label">백엔드 관리</span>
        <button class="btn" @click="action('show_api_manager')">연결 설정</button>
      </div>

      <h3 class="section-title">생성 설정</h3>
      <div class="setting-row">
        <span class="label">설정 저장</span>
        <button class="btn" @click="action('save_settings')">저장</button>
      </div>
      <div class="setting-row">
        <span class="label">프리셋</span>
        <div class="btn-group">
          <button class="btn" @click="action('save_preset')">프리셋 저장</button>
          <button class="btn" @click="action('load_preset')">프리셋 로드</button>
        </div>
      </div>

      <h3 class="section-title">프롬프트</h3>
      <div class="setting-row">
        <span class="label">프롬프트 히스토리</span>
        <button class="btn" @click="action('show_prompt_history')">열기</button>
      </div>

      <h3 class="section-title">도구</h3>
      <div class="setting-row">
        <span class="label">LoRA 관리</span>
        <button class="btn" @click="action('open_lora_manager')">열기</button>
      </div>
      <div class="setting-row">
        <span class="label">가중치 편집</span>
        <button class="btn" @click="action('open_tag_weight_editor')">열기</button>
      </div>

      <h3 class="section-title">앱 정보</h3>
      <div class="setting-row">
        <span class="label">버전</span>
        <span class="value">AI Studio Pro</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { requestAction } from '../stores/widgetStore.js'
function action(name) { requestAction(name) }
</script>

<style scoped>
.settings-view { height: 100%; overflow-y: auto; }
.settings-scroll { max-width: 600px; margin: 0 auto; padding: 24px; }
.section-title {
  color: #E2B340; font-size: 13px; font-weight: 700; margin: 24px 0 8px;
  text-transform: uppercase; letter-spacing: 1px;
  padding-bottom: 6px; border-bottom: 1px solid #1A1A1A;
}
.section-title:first-child { margin-top: 0; }
.setting-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; border-bottom: 1px solid #111;
}
.label { color: #B0B0B0; font-size: 13px; }
.value { color: #585858; font-size: 13px; }
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.btn-group { display: flex; gap: 6px; }
</style>
