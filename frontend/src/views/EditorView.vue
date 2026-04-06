<template>
  <div class="editor-view">
    <div class="editor-placeholder">
      <h2>Image Editor</h2>
      <p>이미지 편집기</p>
      <div class="features">
        <div class="feature">🎨 드로잉</div>
        <div class="feature">✂️ 크롭</div>
        <div class="feature">🔲 모자이크</div>
        <div class="feature">📝 텍스트 오버레이</div>
        <div class="feature">🖌️ 색상 보정</div>
        <div class="feature">📐 원근 변환</div>
      </div>
      <p class="note">편집기는 OpenCV 기반으로 Python에서 실행됩니다.<br/>이미지를 드래그앤드롭하여 편집을 시작하세요.</p>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.editor-view {
  height: 100%; display: flex; align-items: center; justify-content: center;
}
.editor-placeholder { text-align: center; max-width: 400px; }
.editor-placeholder h2 { color: #E8E8E8; font-size: 20px; margin-bottom: 8px; }
.editor-placeholder p { color: #585858; font-size: 13px; margin-bottom: 16px; }
.features {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px;
}
.feature {
  padding: 10px; background: #131313; border-radius: 6px;
  color: #787878; font-size: 12px;
}
.note { color: #484848; font-size: 11px; line-height: 1.6; }
</style>
