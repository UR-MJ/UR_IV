<template>
  <div class="settings-view">
    <div class="sub-tab-bar">
      <button v-for="tab in subTabs" :key="tab.id"
        class="sub-tab" :class="{ active: currentTab === tab.id }"
        @click="currentTab = tab.id"
      >{{ tab.label }}</button>
    </div>
    <div class="settings-scroll">
      <!-- 일반 -->
      <div v-show="currentTab === 'general'" class="tab-content">
        <h4 class="section">일반</h4>
        <div class="row"><span>버전</span><span class="val">AI Studio Pro</span></div>
        <div class="row"><span>백엔드 관리</span><button class="btn" @click="act('show_api_manager')">연결 설정</button></div>
      </div>

      <!-- API -->
      <div v-show="currentTab === 'api'" class="tab-content">
        <h4 class="section">API 설정</h4>
        <div class="row"><span>WebUI URL</span><input class="inp" v-model="webuiUrl" placeholder="http://127.0.0.1:7860" /></div>
        <div class="row"><span>ComfyUI URL</span><input class="inp" v-model="comfyUrl" placeholder="http://127.0.0.1:8188" /></div>
        <div class="row"><span>연결 테스트</span><button class="btn" @click="act('show_api_manager')">테스트</button></div>
      </div>

      <!-- 프롬프트 -->
      <div v-show="currentTab === 'prompt'" class="tab-content">
        <h4 class="section">프롬프트 관리</h4>
        <div class="row"><span>설정 저장</span><button class="btn" @click="act('save_settings')">저장</button></div>
        <div class="row"><span>프리셋 저장</span><button class="btn" @click="act('save_preset')">저장</button></div>
        <div class="row"><span>프리셋 불러오기</span><button class="btn" @click="act('load_preset')">불러오기</button></div>
        <div class="row"><span>프롬프트 히스토리</span><button class="btn" @click="act('show_prompt_history')">열기</button></div>
        <h4 class="section">정리 옵션</h4>
        <label class="chk"><input type="checkbox" v-model="cleanDuplicates" /> 중복 태그 자동 제거</label>
        <label class="chk"><input type="checkbox" v-model="cleanSpaces" /> 공백/쉼표 자동 정리</label>
        <label class="chk"><input type="checkbox" v-model="cleanUnderscore" /> 언더스코어 → 공백 변환</label>
      </div>

      <!-- 탭 순서 -->
      <div v-show="currentTab === 'tabs'" class="tab-content">
        <h4 class="section">탭 순서</h4>
        <p class="hint">드래그하여 순서를 변경하세요</p>
        <div class="tab-order-list">
          <div v-for="(tab, i) in tabOrder" :key="tab"
            class="tab-order-item"
            draggable="true"
            @dragstart="dragStart(i)" @dragover.prevent @drop="dragDrop(i)"
          >
            <span class="drag-handle">⠿</span>
            <span>{{ tab }}</span>
          </div>
        </div>
        <button class="btn" @click="applyTabOrder">적용</button>
        <button class="btn" @click="resetTabOrder">초기화</button>
      </div>

      <!-- 저장 -->
      <div v-show="currentTab === 'save'" class="tab-content">
        <h4 class="section">저장 설정</h4>
        <div class="row"><span>출력 폴더</span><span class="val">generated_images/</span></div>
        <div class="row"><span>파일명 형식</span><span class="val">generated_timestamp_random.png</span></div>
      </div>

      <!-- 단축키 -->
      <div v-show="currentTab === 'shortcuts'" class="tab-content">
        <h4 class="section">단축키</h4>
        <div class="row"><span>Undo</span><span class="val">Ctrl+Z</span></div>
        <div class="row"><span>Redo</span><span class="val">Ctrl+Y</span></div>
        <div class="row"><span>저장</span><span class="val">Ctrl+S</span></div>
        <div class="row"><span>선택 해제</span><span class="val">Esc</span></div>
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
  { id: 'tabs', label: '탭 순서' },
  { id: 'save', label: '저장' },
  { id: 'shortcuts', label: '단축키' },
]
const currentTab = ref('general')
const webuiUrl = ref('http://127.0.0.1:7860')
const comfyUrl = ref('http://127.0.0.1:8188')
const cleanDuplicates = ref(true)
const cleanSpaces = ref(true)
const cleanUnderscore = ref(true)

// 탭 순서
const defaultOrder = ['T2I','I2I','Inpaint','Event Gen','Search','Batch / Upscale','Gallery','XYZ Plot','PNG Info','Favorites','Settings']
const tabOrder = ref([...defaultOrder])
let dragIdx = -1

function dragStart(i) { dragIdx = i }
function dragDrop(i) {
  if (dragIdx < 0) return
  const item = tabOrder.value.splice(dragIdx, 1)[0]
  tabOrder.value.splice(i, 0, item)
  dragIdx = -1
}
function applyTabOrder() { requestAction('set_tab_order', { order: tabOrder.value }) }
function resetTabOrder() { tabOrder.value = [...defaultOrder] }

function act(name) { requestAction(name) }
</script>

<style scoped>
.settings-view { width: 100%; height: 100%; display: flex; flex-direction: column; }
.sub-tab-bar {
  display: flex; gap: 0; padding: 0 16px; flex-shrink: 0;
}
.sub-tab {
  padding: 10px 18px; background: none; border: none;
  color: #585858; font-size: 12px; font-weight: 600; cursor: pointer;
  border-bottom: 2px solid transparent; transition: all 0.15s;
}
.sub-tab:hover { color: #E8E8E8; }
.sub-tab.active { color: #E2B340; border-bottom-color: #E2B340; }
.settings-scroll { flex: 1; overflow-y: auto; }
.tab-content { max-width: 600px; margin: 0 auto; padding: 20px; }
.section {
  color: #E2B340; font-size: 12px; font-weight: 700; margin: 20px 0 8px;
  text-transform: uppercase; letter-spacing: 0.5px;
  padding-bottom: 4px; border-bottom: 1px solid #1A1A1A;
}
.section:first-child { margin-top: 0; }
.row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; border-bottom: 1px solid #111;
}
.row span { color: #B0B0B0; font-size: 13px; }
.val { color: #585858; font-size: 13px; }
.btn {
  padding: 6px 14px; background: #181818; border: none; border-radius: 6px;
  color: #787878; font-size: 12px; cursor: pointer;
}
.btn:hover { background: #222; color: #E8E8E8; }
.inp {
  background: #131313; border: none; border-radius: 4px; padding: 6px 10px;
  color: #E8E8E8; font-size: 12px; outline: none; width: 250px;
}
.chk {
  display: flex; align-items: center; gap: 8px;
  color: #B0B0B0; font-size: 12px; padding: 6px 0; cursor: pointer;
}
.chk input { accent-color: #E2B340; }
.hint { color: #484848; font-size: 11px; margin-bottom: 8px; }
.tab-order-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.tab-order-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #131313; border-radius: 4px; cursor: grab; font-size: 12px; color: #B0B0B0;
}
.tab-order-item:active { cursor: grabbing; background: #1A1A1A; }
.drag-handle { color: #484848; }
</style>
