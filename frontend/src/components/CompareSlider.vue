<template>
  <div class="compare-container" ref="container"
    @mousedown="startDrag" @mousemove="onDrag" @mouseup="endDrag"
    @touchstart.prevent="startDrag" @touchmove.prevent="onDrag" @touchend="endDrag"
  >
    <img class="compare-img before" :src="beforeSrc" @load="onImgLoad" />
    <img class="compare-img after" :src="afterSrc" :style="{ clipPath: clipStyle }" />
    <div class="slider-line" :style="{ left: position + '%' }">
      <div class="slider-handle">◀▶</div>
    </div>
    <div class="compare-label before-label">BEFORE</div>
    <div class="compare-label after-label">AFTER</div>
    <div class="compare-info" v-if="imgSize">{{ imgSize }}</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  beforeSrc: { type: String, default: '' },
  afterSrc: { type: String, default: '' },
})

const container = ref(null)
const position = ref(50)
const dragging = ref(false)
const imgSize = ref('')

const clipStyle = computed(() => `inset(0 ${100 - position.value}% 0 0)`)

function onImgLoad(e) {
  imgSize.value = `${e.target.naturalWidth} × ${e.target.naturalHeight}`
}

function getPos(e) {
  if (!container.value) return 50
  const rect = container.value.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  return Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
}

function startDrag(e) { dragging.value = true; position.value = getPos(e) }
function onDrag(e) { if (dragging.value) position.value = getPos(e) }
function endDrag() { dragging.value = false }
</script>

<style scoped>
.compare-container {
  position: relative; width: 100%; height: 100%;
  overflow: hidden; cursor: col-resize; background: #000;
  display: flex; align-items: center; justify-content: center;
}
.compare-img {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  object-fit: contain; user-select: none; pointer-events: none;
}
.slider-line {
  position: absolute; top: 0; bottom: 0; width: 3px;
  background: var(--accent); z-index: 10;
  transform: translateX(-50%);
}
.slider-handle {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: 36px; height: 36px; background: var(--accent); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #000; font-size: 10px; font-weight: 900;
  box-shadow: 0 2px 8px rgba(0,0,0,0.5);
}
.compare-label {
  position: absolute; top: 12px; font-size: 10px; font-weight: 800;
  color: rgba(255,255,255,0.6); background: rgba(0,0,0,0.5);
  padding: 3px 10px; border-radius: 4px; letter-spacing: 1px;
}
.before-label { left: 12px; }
.after-label { right: 12px; }
.compare-info {
  position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
  font-size: 10px; color: var(--text-muted); background: rgba(0,0,0,0.6);
  padding: 2px 10px; border-radius: 4px;
}
</style>
