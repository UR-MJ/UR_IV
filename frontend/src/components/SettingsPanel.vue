<template>
  <div class="settings-panel">
    <!-- 캐릭터 옵션 -->
    <label class="chk-row">
      <input type="checkbox"
        :checked="get('chk_auto_char_features') === 'true'"
        @change="set('chk_auto_char_features', $event.target.checked ? 'true' : 'false')"
      />
      <span>특징 자동 추가</span>
    </label>

    <label class="s-label">특징 모드</label>
    <CustomSelect :modelValue="featureModeLabel" @update:modelValue="v => set('combo_char_feature_mode', v === '핵심+의상' ? '1' : '0')"
      :options="['핵심만', '핵심+의상']" placeholder="모드" />

    <button class="s-btn" @click="openCharPresetModal()">특징 프리셋</button>

    <!-- 모델 -->
    <label class="s-label">모델</label>
    <CustomSelect :modelValue="get('model_combo')" @update:modelValue="v => set('model_combo', v)"
      :options="getItems('model_combo')" placeholder="모델 선택..." />

    <!-- VAE (ANIMA 등 외부 VAE) -->
    <label class="s-label">VAE</label>
    <CustomSelect :modelValue="get('vae_main_combo')" @update:modelValue="v => set('vae_main_combo', v)"
      :options="getItems('vae_main_combo')" placeholder="(체크포인트 기본 사용)" />

    <!-- Text Encoder (Forge forge_additional_modules) -->
    <label class="s-label">Text Encoder</label>
    <input class="input-field"
      :value="get('te_main_input') || ''"
      @input="set('te_main_input', $event.target.value)"
      placeholder="예: clip_l.safetensors, t5xxl_fp16.safetensors"
    />

    <!-- 샘플러 -->
    <label class="s-label">샘플러</label>
    <CustomSelect :modelValue="get('sampler_combo')" @update:modelValue="v => set('sampler_combo', v)"
      :options="getItems('sampler_combo')" placeholder="샘플러..." />

    <!-- 스케줄러 -->
    <label class="s-label">스케줄러</label>
    <CustomSelect :modelValue="get('scheduler_combo')" @update:modelValue="v => set('scheduler_combo', v)"
      :options="getItems('scheduler_combo')" placeholder="스케줄러..." />

    <!-- Steps -->
    <label class="s-label">Steps</label>
    <div class="slider-row">
      <input type="range" min="1" max="100" step="1"
        :value="get('steps_input') || 25"
        @input="set('steps_input', $event.target.value)"
      />
      <span class="slider-val">{{ get('steps_input') || '25' }}</span>
    </div>

    <!-- CFG -->
    <label class="s-label">CFG Scale</label>
    <div class="slider-row">
      <input type="range" min="1" max="20" step="0.5"
        :value="get('cfg_input') || 7"
        @input="set('cfg_input', $event.target.value)"
      />
      <span class="slider-val">{{ get('cfg_input') || '7' }}</span>
    </div>

    <!-- Seed -->
    <label class="s-label">Seed</label>
    <div class="seed-row">
      <input class="input-field"
        :value="get('seed_input') || '-1'"
        @input="set('seed_input', $event.target.value)"
      />
      <button class="s-btn-sm" @click="set('seed_input', '-1')">🎲</button>
    </div>

    <!-- 해상도 -->
    <label class="s-label">해상도</label>
    <div class="res-row">
      <input class="input-field res-input"
        :value="get('width_input') || '1024'"
        @input="set('width_input', $event.target.value)"
        placeholder="W"
      />
      <span class="res-x">×</span>
      <input class="input-field res-input"
        :value="get('height_input') || '1024'"
        @input="set('height_input', $event.target.value)"
        placeholder="H"
      />
      <button class="s-btn-sm" @click="action('swap_resolution')">&lt;-&gt;</button>
    </div>

    <!-- 퀵 프리셋 -->
    <label class="s-label">퀵 프리셋</label>
    <div class="preset-grid">
      <button v-for="p in resPresets" :key="p.label" class="preset-btn"
        @click="set('width_input', String(p.w)); set('height_input', String(p.h))"
      >{{ p.label }}</button>
    </div>

    <!-- Hires.fix -->
    <label class="chk-row">
      <input type="checkbox"
        :checked="get('hires_options_group') === 'true'"
        @change="set('hires_options_group', $event.target.checked ? 'true' : 'false')"
      />
      <span>Hires.fix</span>
    </label>

    <!-- ADetailer -->
    <label class="chk-row">
      <input type="checkbox"
        :checked="get('adetailer_group') === 'true'"
        @change="set('adetailer_group', $event.target.checked ? 'true' : 'false')"
      />
      <span>ADetailer</span>
    </label>

    <!-- NegPiP -->
    <label class="chk-row">
      <input type="checkbox"
        :checked="get('negpip_group') === 'true'"
        @change="set('negpip_group', $event.target.checked ? 'true' : 'false')"
      />
      <span>NegPiP 확장</span>
    </label>

    <!-- 제거 옵션 -->
    <label class="s-label" style="margin-top: 8px;">태그 제거 옵션</label>
    <div class="remove-grid">
      <label class="chk-row" v-for="opt in removeOptions" :key="opt.id">
        <input type="checkbox"
          :checked="get(opt.id) === 'true'"
          @change="set(opt.id, $event.target.checked ? 'true' : 'false')"
        />
        <span>{{ opt.label }}</span>
      </label>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { state, getValue, setValue, requestAction, getProperty } from '../stores/widgetStore.js'
import { openCharPresetModal } from '../composables/uiModals.js'
import CustomSelect from './CustomSelect.vue'

const resPresets = [
  { label: '512 × 512', w: 512, h: 512 },
  { label: '512 × 768', w: 512, h: 768 },
  { label: '768 × 512', w: 768, h: 512 },
  { label: '1024 × 1024', w: 1024, h: 1024 },
  { label: '832 × 1216', w: 832, h: 1216 },
  { label: '1216 × 832', w: 1216, h: 832 },
]

const removeOptions = [
  { id: 'chk_remove_artist', label: '작가명 제거' },
  { id: 'chk_remove_copyright', label: '작품명 제거' },
  { id: 'chk_remove_character', label: '캐릭터 제거' },
  { id: 'chk_remove_meta', label: '메타 제거' },
  { id: 'chk_remove_censorship', label: '검열 제거' },
  { id: 'chk_remove_text', label: '텍스트 제거' },
]

const featureModeLabel = computed(() => get('combo_char_feature_mode') === '1' ? '핵심+의상' : '핵심만')
function get(id) { return state.values[id] ?? '' }
function set(id, value) { setValue(id, value) }
function action(name) { requestAction(name) }
function getItems(id) { return state.properties[id]?.items ?? [] }
</script>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
}

.s-label {
  font-size: 11px;
  color: #585858;
  font-weight: 600;
  margin-top: 6px;
}

.s-select {
  width: 100%;
  background: var(--bg-input);
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  appearance: auto;
}
.s-select:focus { background: var(--bg-input-focus, #1A1A1A); }

.s-btn {
  width: 100%;
  padding: 8px;
  background: var(--bg-button);
  border: none;
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.s-btn:hover { background: var(--bg-button-hover, #222); }

.s-btn-sm {
  padding: 6px 10px;
  background: var(--bg-button);
  border: none;
  border-radius: 6px;
  color: var(--text-primary);
  cursor: pointer;
  flex-shrink: 0;
}
.s-btn-sm:hover { background: var(--bg-button-hover, #222); }

.input-field {
  width: 100%;
  background: var(--bg-input);
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.input-field:focus { background: var(--bg-input-focus, #1A1A1A); }

.slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.slider-row input[type="range"] {
  flex: 1;
  accent-color: var(--accent);
  height: 4px;
}
.slider-val {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 40px;
  text-align: right;
}

.seed-row {
  display: flex;
  gap: 6px;
}

.res-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.res-input { text-align: center; }
.res-x {
  color: var(--text-disabled, #484848);
  font-size: 14px;
  flex-shrink: 0;
}

.preset-grid {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.preset-btn {
  width: 100%;
  padding: 6px;
  background: var(--bg-button);
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.preset-btn:hover {
  background: var(--bg-button-hover, #222);
  color: var(--text-primary);
}

.chk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 0;
  cursor: pointer;
}
.chk-row input[type="checkbox"] {
  accent-color: var(--accent);
}

.remove-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
}
</style>
