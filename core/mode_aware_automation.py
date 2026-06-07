"""
ModeAwareAutomationSettings — 자동화 설정을 백엔드 모드별로 영속.

ModeAwareMixin 어댑터. 호스트(보통 GeneratorMainUI)의
``_vue_automation_settings`` dict와 Vue UI 사이를 매개.

저장 파일:
- ``save/automation_settings_webui.json``
- ``save/automation_settings_comfyui.json``

흐름:
1. 시작 시 현재 모드 설정 로드 → 호스트 dict 갱신 → Vue 시그널 발행
2. Vue가 사용자 입력 시 set_automation_settings 액션 호출
   → 호스트가 dict 갱신 → ``save_mode_settings()`` 호출
3. 백엔드 모드 전환 (BACKEND_CHANGED 이벤트):
   → 이전 모드 저장
   → 새 모드 로드 → 호스트 dict 갱신 → Vue 시그널 발행
"""
from __future__ import annotations

import json
from typing import Any, Optional

from core.mode_aware_mixin import ModeAwareMixin
from utils.app_logger import get_logger

_logger = get_logger("mode_aware_auto")


# 기본값 — 디스크에 파일 없을 때
_DEFAULT_AUTOMATION_SETTINGS: dict[str, Any] = {
    "mode": "count",
    "limit": 10,
    "repeat": 1,
    "delay": 1.0,
    "allowDupes": False,
    "autoResetDeck": False,
    "maxRetries": 2,
}


class ModeAwareAutomationSettings(ModeAwareMixin):
    """``_vue_automation_settings`` 어댑터.

    호스트 객체에 ``_vue_automation_settings`` (dict)와 ``vue_bridge``
    (automationSettingsLoaded 시그널 보유) 속성이 있어야 한다.
    """

    settings_base_filename = "automation_settings"

    def __init__(self, host: Any):
        self.host = host

    # ─────────────────────────────────────────
    # ModeAwareMixin 구현
    # ─────────────────────────────────────────

    def collect_current_settings(self) -> dict:
        """호스트의 ``_vue_automation_settings``에서 직렬화 가능한 값만 반환."""
        raw = getattr(self.host, "_vue_automation_settings", None) or {}
        return {
            "mode": str(raw.get("mode", "count")),
            "limit": float(raw.get("limit", 10)),
            "repeat": int(raw.get("repeat", 1)),
            "delay": float(raw.get("delay", 1.0)),
            "allowDupes": bool(raw.get("allowDupes", False)),
            "autoResetDeck": bool(raw.get("autoResetDeck", False)),
            "maxRetries": int(raw.get("maxRetries", 2)),
        }

    def apply_settings(self, settings: dict) -> None:
        """디스크에서 로드된 설정 → 호스트 dict 갱신 + Vue로 전파."""
        if not isinstance(settings, dict):
            return
        merged = dict(_DEFAULT_AUTOMATION_SETTINGS)
        for k in merged:
            if k in settings:
                merged[k] = settings[k]
        # 타입 정규화
        merged["mode"] = str(merged["mode"])
        try:
            merged["limit"] = float(merged["limit"])
        except (TypeError, ValueError):
            merged["limit"] = 10.0
        try:
            merged["repeat"] = int(merged["repeat"])
        except (TypeError, ValueError):
            merged["repeat"] = 1
        try:
            merged["delay"] = float(merged["delay"])
        except (TypeError, ValueError):
            merged["delay"] = 1.0
        try:
            merged["maxRetries"] = int(merged["maxRetries"])
        except (TypeError, ValueError):
            merged["maxRetries"] = 2
        merged["allowDupes"] = bool(merged["allowDupes"])

        # 호스트 dict 교체
        self.host._vue_automation_settings = merged

        # Vue로 전파 (시그널 있을 때만 — 단위 테스트나 초기화 미완료 환경 보호)
        bridge = getattr(self.host, "vue_bridge", None)
        if bridge is not None and hasattr(bridge, "automationSettingsLoaded"):
            try:
                bridge.automationSettingsLoaded.emit(json.dumps(merged))
            except Exception:
                _logger.exception("automationSettingsLoaded emit 실패")

    # ─────────────────────────────────────────
    # 편의 메서드
    # ─────────────────────────────────────────

    def initialize(self) -> None:
        """앱 시작 시 1회 호출 — 현재 모드 설정 로드 + 자동 전환 구독.

        파일이 없으면 (첫 실행) 기본값 유지 + 즉시 저장해 안내.
        """
        loaded = self.load_mode_settings()
        if not loaded:
            # 디스크에 없으면 기본값을 저장해 다음 실행부터 일관
            self.save_mode_settings()
            # Vue에도 기본값 1회 푸시 (자동화 패널을 펼치면 보이도록)
            self.apply_settings(_DEFAULT_AUTOMATION_SETTINGS)

        # 백엔드 전환 자동화 (이전 모드 저장 + 새 모드 로드)
        self.auto_subscribe_to_mode_change()
