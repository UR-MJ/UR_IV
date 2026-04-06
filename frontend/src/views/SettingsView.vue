<template>
  <div class="settings-view">
    <!-- 서브 탭 바 -->
    <div class="sub-tab-bar">
      <button v-for="tab in subTabs" :key="tab.id"
        class="sub-tab" :class="{ active: currentTab === tab.id }"
        @click="currentTab = tab.id"
      >{{ tab.label }}</button>
    </div>

    <div class="settings-scroll">
      <!-- 일반 -->
      <div v-show="currentTab === 'general'" class="tab-content">
        <div class="setting-row">
          <span class="label">테마</span>
          <span class="value">모던</span>
        </div>
        <div class="setting-row">
          <span class="label">버전</span>
          <span class="value">AI Studio Pro</span>
        </div>
      </div>

      <!-- API -->
      <div v-show="currentTab === 'api'" class="tab-content">
        <div class="setting-row">
          <span class="label">백엔드 관리</span>
          <button class="btn" @click="action('show_api_manager')">연결 설정</button>
        </div>
      </div>

      <!-- 프롬프트 -->
      <div v-show="currentTab === 'prompt'" class="tab-content">
        <div class="setting-row">
          <span class="label">설정 저장</span>
          <button class="btn" @click="action('save_settings')">저장</button>
        </div>
        <div class="setting-row">
          <span class="label">프리셋 저장</span>
          <button class="btn" @click="action('save_preset')">저장</button>
        </div>
        <div class="setting-row">
          <span class="label">프리셋 불러오기</span>
          <button class="btn" @click="action('load_preset')">불러오기</button>
        </div>
        <div class="setting-row">
          <span class="label">프롬프트 히스토리</span>
          <button class="btn" @click="action('show_prompt_history')">열기</button>
        </div>
      </div>

      <!-- 도구 -->
      <div v-show="currentTab === 'tools'" class="tab-content">
        <div class="setting-row">
          <span class="label">LoRA 관리</span>
          <button class="btn" @click="action('open_lora_manager')">열기</button>
        </div>
        <div class="setting-row">
          <span class="label">가중치 편집</span>
          <button class="btn" @click="action('open_tag_weight_editor')">열기</button>
        </div>
        <div class="setting-row">
          <span class="label">태그 셔플</span>
          <button class="btn" @click="action('shuffle')">실행</button>
        </div>
        <div class="setting-row">
          <span class="label">A/B 비교</span>
          <button class="btn" @click="action('ab_test')">열기</button>
        </div>
      </div>

      <!-- 저장 -->
      <div v-show="currentTab === 'save'" class="tab-content">
        <div class="setting-row">
          <span class="label">출력 폴더</span>
          <span class="value">generated_images/</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { requestAction } from '../stores/widgetStore.js'

const subTabs = [
  { id: 'general', label: '일반' },
  { id: 'api', label: 'API' },
  { id: 'prompt', label: '프롬프트' },
  { id: 'tools', label: '도구' },
  { id: 'save', label: '저장' },
]
const currentTab = ref('general')

function action(name) { requestAction(name) }
</script>

<style scoped>
.settings-view { height: 100%; display: flex; flex-direction: column; }
.sub-tab-bar {
  display: flex; gap: 0; border-bottom: 1px solid #1A1A1A;
  padding: 0 16px;
}
.sub-tab {
  padding: 10px 20px; background: none; border: none;
  color: #585858; font-size: 12px; font-weight: 600; cursor: pointer;
  border-bottom: 2px solid transparent; transition: all 0.15s;
}
.sub-tab:hover { color: #E8E8E8; }
.sub-tab.active { color: #E2B340; border-bottom-color: #E2B340; }
.settings-scroll { flex: 1; overflow-y: auto; }
.tab-content { max-width: 600px; margin: 0 auto; padding: 20px; }
.setting-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid #111;
}
.label { color: #B0B0B0; font-size: 13px; }
.value { color: #585858; font-size: 13px; }
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
</style>
