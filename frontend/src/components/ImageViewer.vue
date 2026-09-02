<template>
  <div class="viewer">
    <!-- 이미지 표시 영역 -->
    <div class="image-area">
      <template v-if="imageUrl">
        <img :key="imageSrc" :src="imageSrc" alt="Generated" class="generated-image" />
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
            <div class="placeholder-icon"><Icon name="image" /></div>
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
      <button class="explore-btn" @click="exploreSeed" v-if="seed"><Icon name="search" /> 시드 탐색</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { requestAction } from '../stores/widgetStore.js'
import { mediaUrl } from '../utils/media.js'

const props = withDefaults(defineProps<{
  imageUrl?: string
  resolution?: string
  seed?: string
  status?: string
}>(), {
  imageUrl: '',
  resolution: '',
  seed: '',
  status: '',
})

function exploreSeed() {
  requestAction('explore_seed', { seed: props.seed })
}

const imageNonce = ref(Date.now())
watch(() => props.imageUrl, () => {
  imageNonce.value = Date.now()
})

const imageSrc = computed(() => {
  if (!props.imageUrl) return ''
  const base = mediaUrl(props.imageUrl)
  return base + (base.includes('?') ? '&' : '?') + 't=' + imageNonce.value
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
  background: var(--bg-primary);
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
  color: var(--text-muted);
  font-weight: var(--fw-bold);
  margin-bottom: 8px;
}

.placeholder-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.info-bar {
  display: flex;
  justify-content: center;
  gap: 24px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--rule);
}

.info-item { font-size: 12px; color: var(--text-muted); }
.explore-btn {
  padding: 3px 12px; background: var(--bg-button); border: 1px solid var(--border);
  border-radius: 4px; color: var(--accent); font-size: var(--fs-label); font-weight: var(--fw-bold); cursor: pointer;
}
.explore-btn:hover { background: var(--accent-dim); border-color: var(--accent); }
.generating { text-align: center; }
.spinner {
  width: 40px; height: 40px; margin: 0 auto 12px;
  /* 진행 표시의 '빈 부분'은 구분선 역할이라 --rule (라이트에서도 보이는 값) */
  border: 3px solid var(--rule); border-top: 3px solid var(--accent);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.gen-text { color: var(--accent); font-size: 14px; font-weight: var(--fw-bold); }
.progress-bar {
  width: 200px; height: 4px; background: var(--rule); border-radius: 2px;
  margin: 12px auto 0; overflow: hidden;
}
.progress-fill {
  height: 100%; background: var(--accent); border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
