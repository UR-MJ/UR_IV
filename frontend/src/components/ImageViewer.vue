<template>
  <div class="viewer">
    <!-- 이미지 표시 영역 -->
    <div class="image-area">
      <template v-if="imageUrl">
        <img :src="'file:///' + imageUrl" alt="Generated" class="generated-image" />
      </template>
      <template v-else>
        <div class="placeholder">
          <div class="placeholder-icon">🖼️</div>
          <div class="placeholder-text">{{ status || '이미지를 생성하세요' }}</div>
          <div class="placeholder-sub">좌측에서 프롬프트를 입력하고 생성 버튼을 클릭하세요</div>
          <div class="placeholder-sub">이미지를 드래그하여 메타데이터를 불러올 수 있습니다</div>
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
defineProps({
  imageUrl: { type: String, default: '' },
  resolution: { type: String, default: '' },
  seed: { type: String, default: '' },
  status: { type: String, default: '' },
})
</script>

<style scoped>
.viewer {
  flex: 1;
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
</style>
