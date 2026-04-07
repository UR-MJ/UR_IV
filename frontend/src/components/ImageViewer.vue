<template>
  <div class="viewer">
    <!-- 이미지 표시 영역 -->
    <div class="image-area">
      <template v-if="imageUrl">
        <img :src="'file:///' + imageUrl" alt="Generated" class="generated-image" />
      </template>
      <template v-else>
        <div class="placeholder">
          <div v-if="status && status.includes('생성 중')" class="generating">
            <div class="spinner" />
            <div class="gen-text">{{ status }}</div>
            <div class="progress-bar" v-if="status.includes('/')">
              <div class="progress-fill" :style="{ width: progressPct + '%' }" />
            </div>
          </div>
          <template v-else>
            <div class="placeholder-icon">🖼️</div>
            <div class="placeholder-text">{{ status || '이미지를 생성하세요' }}</div>
            <div class="placeholder-sub">좌측에서 프롬프트를 입력하고 생성 버튼을 클릭하세요</div>
          </template>
        </div>
      </template>
    </div>

    <!-- 하단 정보 바 -->
    <div class="info-bar" v-if="imageUrl">
      <span class="info-item">해상도 {{ resolution }}</span>
      <span class="info-item">시드 {{ seed }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  imageUrl: { type: String, default: '' },
  resolution: { type: String, default: '' },
  seed: { type: String, default: '' },
  status: { type: String, default: '' },
})

const progressPct = computed(() => {
  const m = props.status?.match(/(\d+)\/(\d+)/)
  if (m) return Math.round(parseInt(m[1]) / parseInt(m[2]) * 100)
  return 0
})
</script>

<style scoped>
.viewer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0A0A0A;
}

.image-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 16px;
}

.generated-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
}

.placeholder {
  text-align: center;
  user-select: none;
}

.placeholder-icon {
  font-size: 64px;
  opacity: 0.15;
  margin-bottom: 16px;
}

.placeholder-text {
  font-size: 18px;
  color: #787878;
  font-weight: 600;
  margin-bottom: 8px;
}

.placeholder-sub {
  font-size: 13px;
  color: #484848;
  margin-bottom: 4px;
}

.info-bar {
  display: flex;
  justify-content: center;
  gap: 24px;
  padding: 8px 16px;
  background: #111111;
  border-top: 1px solid #1A1A1A;
}

.info-item {
  font-size: 12px;
  color: #787878;
}
.generating { text-align: center; }
.spinner {
  width: 40px; height: 40px; margin: 0 auto 12px;
  border: 3px solid #1A1A1A; border-top: 3px solid #E2B340;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.gen-text { color: #E2B340; font-size: 14px; font-weight: 600; }
.progress-bar {
  width: 200px; height: 4px; background: #1A1A1A; border-radius: 2px;
  margin: 12px auto 0; overflow: hidden;
}
.progress-fill {
  height: 100%; background: #E2B340; border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
