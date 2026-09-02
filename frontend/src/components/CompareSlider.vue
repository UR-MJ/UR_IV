<template>
  <div class="compare-container" ref="container"
    @mousedown="startDrag" @mousemove="onDrag" @mouseup="endDrag"
    @touchstart.prevent="startDrag" @touchmove.prevent="onDrag" @touchend="endDrag"
  >
    <img class="compare-img before" :src="beforeSrc" @load="onImgLoad" />
    <img class="compare-img after" :src="afterSrc" :style="{ clipPath: clipStyle }" />
    <div class="slider-line" :style="{ left: position + '%' }">
      <div class="slider-handle"><Icon name="arrows-horizontal" size="14" /></div>
    </div>
    <div class="compare-label before-label">이전</div>
    <div class="compare-label after-label">이후</div>
    <div class="compare-info" v-if="imgSize">{{ imgSize }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

withDefaults(defineProps<{
  beforeSrc?: string
  afterSrc?: string
}>(), {
  beforeSrc: '',
  afterSrc: '',
})

const container = ref<HTMLElement | null>(null)
const position = ref(50)
const dragging = ref(false)
const imgSize = ref('')

const clipStyle = computed(() => `inset(0 ${100 - position.value}% 0 0)`)

function onImgLoad(e: Event) {
  const img = e.target as HTMLImageElement
  imgSize.value = `${img.naturalWidth} × ${img.naturalHeight}`
}

function getPos(e: MouseEvent | TouchEvent): number {
  if (!container.value) return 50
  const rect = container.value.getBoundingClientRect()
  const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
  return Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
}

function startDrag(e: MouseEvent | TouchEvent) { dragging.value = true; position.value = getPos(e) }
function onDrag(e: MouseEvent | TouchEvent) { if (dragging.value) position.value = getPos(e) }
function endDrag() { dragging.value = false }
</script>

<style scoped>
.compare-container {
  position: relative; width: 100%; height: 100%;
  /* 이미지 레터박스 받침이라 UI 크롬이 아니다. 위에 얹힌 라벨이 '흰 글자/검은 판'
     고정이라 여길 테마색으로 바꾸면 그 라벨이 먼저 깨진다. */
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
  /* 아이콘을 얹는 면이라 --accent 가 아니라 --accent-fill (사용자가 어떤 강조색을
     골라도 --on-accent 아이콘이 읽히도록 명도를 민 값) */
  width: 36px; height: 36px; background: var(--accent-fill); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: var(--on-accent); font-size: var(--fs-label); font-weight: var(--fw-bold);
  box-shadow: 0 2px 8px rgba(0,0,0,0.5);
}
.compare-label {
  position: absolute; top: 12px; font-size: var(--fs-label); font-weight: var(--fw-bold);
  color: rgba(255,255,255,0.6); background: rgba(0,0,0,0.5);
  padding: 3px 10px; border-radius: 4px; letter-spacing: 0;
}
.before-label { left: 12px; }
.after-label { right: 12px; }
.compare-info {
  position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
  font-size: var(--fs-label); color: var(--text-muted); background: rgba(0,0,0,0.6);
  padding: 2px 10px; border-radius: 4px;
}
</style>
