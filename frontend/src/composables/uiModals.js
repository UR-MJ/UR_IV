// 컴포넌트 간 공유 모달 상태 (PromptPanel/SettingsPanel/App 어디서든 열기)
import { reactive } from 'vue'

export const uiModals = reactive({
  charPreset: false,   // 캐릭터 특징 프리셋 모달
  abTest: false,       // A/B 테스트 모달
  charOverride: false, // auto-remove override 모달
})

export function openCharPresetModal() { uiModals.charPreset = true }
export function closeCharPresetModal() { uiModals.charPreset = false }
export function openAbTestModal() { uiModals.abTest = true }
export function closeAbTestModal() { uiModals.abTest = false }
export function openCharOverrideModal() { uiModals.charOverride = true }
export function closeCharOverrideModal() { uiModals.charOverride = false }
