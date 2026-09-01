<template>
  <div class="cp-overlay" @mousedown.self="close">
    <div class="cp-modal">
      <div class="cp-header">
        <div>
          <h3>조건부 프롬프트</h3>
          <span class="cp-sub">태그 조건에 따라 프롬프트를 자동으로 추가/제거/대체합니다</span>
        </div>
        <div class="cp-master" :class="{ on: condEnabled }">
          <ToggleSwitch v-model="condEnabled" />
          <span>{{ condEnabled ? 'ON' : 'OFF' }}</span>
        </div>
        <button class="cp-close" @click="close"><Icon name="close" /></button>
      </div>

      <div class="cp-optbar">
        <label class="cp-opt">
          <ToggleSwitch :model-value="preventDupe" size="sm" @update:modelValue="emit('update:preventDupe', $event)" />
          <span>중복 방지 <em>이미 있는 태그는 다시 추가하지 않음</em></span>
        </label>
      </div>

      <div class="cp-body" :class="{ disabled: !condEnabled }">
        <div class="cp-grid">
          <!-- POSITIVE -->
          <div class="cp-card">
            <div class="cp-card-title positive">CONDITIONAL POSITIVE</div>
            <p class="cp-desc">조건 태그가 있으면/없으면 본문 프롬프트에 추가·제거·대체</p>
            <div v-for="(rule, ri) in condPositive" :key="'p'+ri" class="cp-rule">
              <div class="cp-row">
                <ToggleSwitch v-model="rule.enabled" size="sm" />
                <span class="cp-kw">IF</span>
                <input v-model="rule.condition" placeholder="조건 태그 (쉼표=모두 AND)" class="cp-input" />
                <select v-model="rule.exists" class="cp-sel"><option :value="true">있으면</option><option :value="false">없으면</option></select>
                <button class="cp-rm" @click="removeCondRule('pos', ri)"><Icon name="close" /></button>
              </div>
              <div class="cp-row">
                <span class="cp-kw">→</span>
                <input v-model="rule.target" placeholder="대상 태그" class="cp-input" />
                <select v-model="rule.action" class="cp-sel"><option value="add">추가</option><option value="remove">제거</option><option value="replace">대체</option></select>
                <select v-model="rule.location" class="cp-sel" title="삽입 위치"><option value="main">본문</option><option value="prefix">선행</option><option value="suffix">후행</option><option value="after_condition">바로 뒤</option></select>
              </div>
            </div>
            <button class="cp-add" @click="addCondRule('pos')">+ 규칙 추가</button>
          </div>

          <!-- NEGATIVE -->
          <div class="cp-card neg">
            <div class="cp-card-title negative">CONDITIONAL NEGATIVE</div>
            <p class="cp-desc">조건 태그가 있으면/없으면 네거티브 프롬프트에 추가·제거</p>
            <div v-for="(rule, ri) in condNegative" :key="'n'+ri" class="cp-rule">
              <div class="cp-row">
                <ToggleSwitch v-model="rule.enabled" size="sm" />
                <span class="cp-kw">IF</span>
                <input v-model="rule.condition" placeholder="조건 태그 (쉼표=모두 AND)" class="cp-input" />
                <select v-model="rule.exists" class="cp-sel"><option :value="true">있으면</option><option :value="false">없으면</option></select>
                <button class="cp-rm" @click="removeCondRule('neg', ri)"><Icon name="close" /></button>
              </div>
              <div class="cp-row">
                <span class="cp-kw">→</span>
                <input v-model="rule.target" placeholder="네거티브 태그" class="cp-input neg" />
                <select v-model="rule.action" class="cp-sel"><option value="add">추가</option><option value="remove">제거</option></select>
                <select v-model="rule.location" class="cp-sel" title="삽입 위치"><option value="main">본문</option><option value="prefix">선행</option><option value="suffix">후행</option></select>
              </div>
            </div>
            <button class="cp-add" @click="addCondRule('neg')">+ 규칙 추가</button>
          </div>
        </div>
      </div>

      <div class="cp-footer">
        <span class="cp-autosave"><Icon name="save" /> 자동 저장됨</span>
        <div class="cp-spacer"></div>
        <button class="cp-save" @click="saveCondRules">즉시 저장</button>
        <button class="cp-done" @click="close">닫기</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { condPositive, condNegative, condEnabled, addCondRule, removeCondRule, saveCondRules, loadCondRules } from '../composables/condRules.js'
import ToggleSwitch from './ToggleSwitch.vue'

withDefaults(defineProps<{ preventDupe?: boolean }>(), { preventDupe: true })
const emit = defineEmits<{ close: []; 'update:preventDupe': [value: boolean] }>()
function close() { emit('close') }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') { e.stopPropagation(); close() } }
onMounted(() => { loadCondRules(); window.addEventListener('keydown', onKey, true) })
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
</script>

<style scoped>
.cp-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 2200; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.cp-modal { width: min(1450px, 97vw); height: min(920px, 94vh); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-card); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.6); }
.cp-header { display: flex; align-items: center; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.cp-header h3 { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.cp-sub { font-size: 11px; color: var(--text-muted); }
.cp-master { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 800; color: var(--text-muted); background: var(--bg-button); border: 1px solid var(--border); border-radius: 14px; padding: 4px 12px; cursor: pointer; }
.cp-master.on { color: #4ade80; border-color: #4ade80; }
.cp-close { width: 30px; height: 30px; background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); cursor: pointer; }
.cp-close:hover { color: var(--text-primary); border-color: var(--accent); }
.cp-optbar { padding: 8px 20px; border-bottom: 1px solid var(--border); }
.cp-opt { display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700; color: var(--text-secondary); cursor: pointer; }
.cp-opt em { font-style: normal; font-weight: 400; color: var(--text-muted); margin-left: 4px; }
.cp-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.cp-body.disabled { opacity: 0.45; pointer-events: none; }
.cp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.cp-card { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.cp-card.neg { border-color: rgba(248,113,113,0.25); }
.cp-card-title { font-size: 12px; font-weight: 800; letter-spacing: 1px; }
.cp-card-title.positive { color: var(--accent); }
.cp-card-title.negative { color: #f87171; }
.cp-desc { font-size: var(--fs-label); color: var(--text-muted); margin: 4px 0 10px; }
.cp-rule { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 11px; margin-bottom: 9px; display: flex; flex-direction: column; gap: 8px; }
.cp-row { display: flex; align-items: center; gap: 7px; }
.cp-kw { font-size: 12px; font-weight: 800; color: var(--text-muted); min-width: 16px; text-align: center; }
.cp-input { flex: 1 1 auto; min-width: 180px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 9px 11px; color: var(--text-primary); font-size: 13px; }
.cp-input.neg { color: #fca5a5; }
.cp-input:focus { outline: none; border-color: var(--accent); }
.cp-sel { flex: 0 0 auto; width: 72px; min-width: 0; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 9px 4px; color: var(--text-primary); font-size: 12px; }
.cp-rm { background: transparent; border: none; color: #f87171; cursor: pointer; font-size: 12px; }
.cp-add { width: 100%; padding: 6px; background: var(--bg-button); border: 1px dashed var(--border); border-radius: 6px; color: var(--text-secondary); font-size: var(--fs-label); font-weight: 700; cursor: pointer; }
.cp-footer { display: flex; align-items: center; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
.cp-autosave { font-size: var(--fs-label); color: #4ade80; }
.cp-spacer { flex: 1; }
.cp-save { background: var(--accent-dim); border: 1px solid var(--accent); border-radius: var(--radius-base); color: var(--accent); font-size: 11px; font-weight: 700; padding: 8px 14px; cursor: pointer; }
.cp-done { background: var(--bg-button); border: 1px solid var(--border); border-radius: var(--radius-base); color: var(--text-secondary); font-size: 12px; font-weight: 700; padding: 8px 14px; cursor: pointer; }
.cp-done:hover { color: var(--text-primary); border-color: var(--accent); }
</style>
