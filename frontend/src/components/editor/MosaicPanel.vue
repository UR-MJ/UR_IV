<template>
  <div class="mosaic-panel">
    <!-- Section 1: Selection Tools -->
    <div class="control-group">
      <label>Selection Tool</label>
      <div class="chip-grid">
        <button v-for="t in tools" :key="t.id"
          class="chip-btn" :class="{ active: selectedTool === t.id }"
          @click="selectTool(t.id)"
        >
          <span class="icon">{{ t.icon }}</span>
          <span class="label">{{ t.label }}</span>
        </button>
      </div>
    </div>

    <!-- Section 2: Visual Effects -->
    <div class="control-group">
      <label>Apply Effect</label>
      <div class="chip-grid-3">
        <button v-for="e in effects" :key="e.id"
          class="chip-btn" :class="{ active: selectedEffect === e.id }"
          @click="selectEffect(e.id)"
        >
          <span class="label">{{ e.label }}</span>
        </button>
      </div>
    </div>

    <!-- Section 3: Smart AI Censorship -->
    <div class="control-group glass-box">
      <div class="header-with-action">
        <label>AI CENSORSHIP</label>
        <span class="status-dot" :class="{ active: detectStatus }"></span>
      </div>
      <div class="model-info">{{ modelLabel }}</div>
      <div class="btn-row mt-8">
        <button class="ghost-btn" @click="$emit('add-model')">+ ADD .PT</button>
        <button class="ghost-btn" @click="$emit('clear-models')">RESET</button>
      </div>
      <div class="slider-box mt-12">
        <div class="slider-header">
          <span>Confidence</span>
          <span>{{ detectConf }}%</span>
        </div>
        <input type="range" min="1" max="100" v-model.number="detectConf" class="modern-slider" />
      </div>
      <div class="btn-row mt-12">
        <button class="action-btn primary" @click="$emit('auto-censor', { confidence: detectConf })">AUTO CENSOR</button>
        <button class="action-btn" @click="$emit('auto-detect', { confidence: detectConf })">MASK ONLY</button>
      </div>
    </div>

    <!-- Section: STAMP 간격 (STAMP 선택 시만) -->
    <div class="control-group" v-if="selectedTool === 4">
      <label>Stamp Spacing</label>
      <div class="slider-box">
        <div class="slider-header"><span>간격 (px)</span><span>{{ stampSpacing }}</span></div>
        <input type="range" min="5" max="200" v-model.number="stampSpacing" class="modern-slider" />
      </div>
    </div>

    <!-- Section: Eraser Mode (지우개 선택 시만 표시) -->
    <div class="control-group" v-if="selectedTool === 3">
      <label>Eraser Mode</label>
      <div class="chip-grid-3">
        <button class="chip-btn" :class="{ active: eraserMode === 'brush' }" @click="setEraserMode('brush')">BRUSH</button>
        <button class="chip-btn" :class="{ active: eraserMode === 'box' }" @click="setEraserMode('box')">RECT</button>
        <button class="chip-btn" :class="{ active: eraserMode === 'lasso' }" @click="setEraserMode('lasso')">LASSO</button>
      </div>
    </div>

    <!-- Section 4: Adjustments -->
    <div class="control-group">
      <label>Adjustments</label>
      <div class="slider-box">
        <div class="slider-header"><span>Size</span><span>{{ toolSize }}px</span></div>
        <input type="range" min="1" max="300" v-model.number="toolSize" class="modern-slider" />
      </div>
      <div class="slider-box mt-8">
        <div class="slider-header"><span>Strength</span><span>{{ strength }}</span></div>
        <input type="range" min="1" max="100" v-model.number="strength" class="modern-slider" />
      </div>
    </div>

    <!-- Section 5: Major Actions (Sticky Bottom feel) -->
    <div class="footer-actions mt-auto">
      <button class="main-apply-btn" @click="onApply">
        <span class="icon">✨</span> APPLY CHANGES (ENTER)
      </button>
      <button class="secondary-btn mt-8" @click="$emit('cancel-selection')">CANCEL SELECTION (ESC)</button>
    </div>

    <!-- Section 6: Transformations -->
    <div class="control-group mt-12">
      <label>Transform</label>
      <div class="btn-grid-4">
        <button class="mini-btn" @click="$emit('rotate', 'ccw')" title="Rotate CCW">↺</button>
        <button class="mini-btn" @click="$emit('rotate', 'cw')" title="Rotate CW">↻</button>
        <button class="mini-btn" @click="$emit('flip', 'horizontal')" title="Flip Horizontal">↔</button>
        <button class="mini-btn" @click="$emit('flip', 'vertical')" title="Flip Vertical">↕</button>
      </div>
      <div class="btn-row mt-8">
        <button class="action-btn" @click="$emit('crop')">CROP</button>
        <button class="action-btn" @click="$emit('resize')">RESIZE</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const emit = defineEmits(['tool-changed','effect-changed','effect-apply','cancel-selection','crop','resize','perspective','rotate','flip','remove-bg','add-model','clear-models','auto-censor','auto-detect','params-changed','eraser-mode-changed'])
const props = defineProps({ modelLabel: { type: String, default: 'No Model Loaded' }, detectStatus: { type: String, default: '' } })

const tools = [
  { id: 0, label: 'RECT', icon: '⬚' },
  { id: 1, label: 'LASSO', icon: '➰' },
  { id: 2, label: 'BRUSH', icon: '🖌' },
  { id: 3, label: 'ERASER', icon: '⌫' },
  { id: 4, label: 'STAMP', icon: '⬡' },
]
const effects = [
  { id: 0, label: 'MOSAIC' },
  { id: 1, label: 'BLACK BAR' },
  { id: 2, label: 'BLUR' },
]

const selectedTool = ref(0)
const selectedEffect = ref(0)
const toolSize = ref(20)
const strength = ref(15)
const detectConf = ref(25)
const eraserMode = ref('brush')
const stampSpacing = ref(30)

function selectTool(id) { selectedTool.value = id; emit('tool-changed', { tool: id, size: toolSize.value }) }
function selectEffect(id) { selectedEffect.value = id; emit('effect-changed', { effect: id }) }
function setEraserMode(mode) { eraserMode.value = mode; emit('eraser-mode-changed', mode) }
function onApply() { emit('effect-apply', { tool: selectedTool.value, effect: selectedEffect.value, toolSize: toolSize.value, strength: strength.value }) }

watch([toolSize, strength, stampSpacing], () => { emit('params-changed', { toolSize: toolSize.value, strength: strength.value, stampSpacing: stampSpacing.value }) })
</script>

<style scoped>
.mosaic-panel {
  display: flex; flex-direction: column; height: 100%;
  padding: 16px; background: var(--bg-secondary); gap: 20px;
}

.control-group { display: flex; flex-direction: column; }
.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }
.mt-auto { margin-top: auto; }

.chip-grid, .chip-grid-3 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.chip-grid-3 { grid-template-columns: repeat(3, 1fr); }

.chip-btn {
  height: 38px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: var(--radius-base); color: var(--text-secondary);
  font-size: 10px; font-weight: 800; cursor: pointer; transition: var(--transition);
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.chip-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }
.chip-btn.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

.glass-box {
  background: rgba(255,255,255,0.02); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 12px;
}

.header-with-action { display: flex; justify-content: space-between; align-items: center; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: #333; }
.status-dot.active { background: var(--accent); box-shadow: 0 0 8px var(--accent); }

.model-info { font-size: 11px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ghost-btn {
  flex: 1; height: 28px; background: transparent; border: 1px dashed var(--border);
  border-radius: 4px; color: var(--text-secondary); font-size: 9px; font-weight: 700; cursor: pointer;
}
.ghost-btn:hover { border-color: var(--text-muted); color: var(--text-primary); }

.btn-row { display: flex; gap: 6px; }

.action-btn {
  flex: 1; height: 34px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: 10px; font-weight: 800; cursor: pointer;
}
.action-btn.primary { background: var(--accent); color: #000; border: none; }

.slider-box { display: flex; flex-direction: column; gap: 4px; }
.slider-header { display: flex; justify-content: space-between; font-size: 10px; font-weight: 700; color: var(--text-secondary); }

.modern-slider {
  appearance: none; width: 100%; height: 4px; background: var(--bg-input);
  border-radius: 2px; outline: none; accent-color: var(--accent);
}

.main-apply-btn {
  width: 100%; height: 46px; background: var(--accent); border: none;
  border-radius: var(--radius-pill); color: #000; font-weight: 900;
  font-size: 12px; letter-spacing: 1px; cursor: pointer; transition: var(--transition);
}
.main-apply-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(250, 204, 21, 0.3); }

.secondary-btn {
  width: 100%; height: 36px; background: transparent; border: 1px solid var(--border);
  border-radius: var(--radius-pill); color: var(--text-muted); font-size: 10px; font-weight: 700; cursor: pointer;
}

.btn-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.mini-btn {
  height: 30px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-secondary); cursor: pointer;
}
</style>
