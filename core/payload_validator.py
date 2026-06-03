# core/payload_validator.py
"""생성 payload의 공통 검증.

UI 위젯을 통과한 값은 대체로 안전하지만, EXIF 재생성·프리셋 로드·자동화 등
다양한 경로로 들어온 payload는 한 번 중앙에서 검증하면 API 호출 전에
예측 가능한 오류를 조기 차단할 수 있다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# SD 해상도 기본 제약
MIN_DIMENSION = 64
MAX_DIMENSION = 4096
DIMENSION_MULTIPLE = 8

MIN_STEPS = 1
MAX_STEPS = 150
MIN_CFG = 1.0
MAX_CFG = 30.0

SEED_MIN = -1
SEED_MAX = 2 ** 32 - 1

# 경고 기준 (에러 아님)
PROMPT_TOKEN_WARN = 77 * 4  # SDXL는 225 토큰까지 허용 — 러프 문자 기준


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


class PayloadValidator:
    """txt2img / img2img payload 공통 검증."""

    @staticmethod
    def validate_dimension(value, name: str, result: ValidationResult) -> int | None:
        try:
            v = int(value)
        except (TypeError, ValueError):
            result.add_error(f"{name}이(가) 정수가 아닙니다: {value!r}")
            return None
        if not (MIN_DIMENSION <= v <= MAX_DIMENSION):
            result.add_error(f"{name}은(는) {MIN_DIMENSION}~{MAX_DIMENSION} 범위여야 합니다 (받은 값: {v})")
            return None
        if v % DIMENSION_MULTIPLE != 0:
            result.add_warning(f"{name}={v}이 {DIMENSION_MULTIPLE}의 배수가 아닙니다 — 자동 반올림될 수 있음")
        return v

    @staticmethod
    def validate_steps(value, result: ValidationResult) -> int | None:
        try:
            v = int(value)
        except (TypeError, ValueError):
            result.add_error(f"스텝이 정수가 아닙니다: {value!r}")
            return None
        if not (MIN_STEPS <= v <= MAX_STEPS):
            result.add_error(f"스텝은 {MIN_STEPS}~{MAX_STEPS} 범위여야 합니다 (받은 값: {v})")
            return None
        return v

    @staticmethod
    def validate_cfg(value, result: ValidationResult) -> float | None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            result.add_error(f"CFG가 숫자가 아닙니다: {value!r}")
            return None
        if not (MIN_CFG <= v <= MAX_CFG):
            result.add_error(f"CFG는 {MIN_CFG}~{MAX_CFG} 범위여야 합니다 (받은 값: {v})")
            return None
        return v

    @staticmethod
    def validate_seed(value, result: ValidationResult) -> int | None:
        try:
            v = int(value)
        except (TypeError, ValueError):
            result.add_error(f"시드가 정수가 아닙니다: {value!r}")
            return None
        if not (SEED_MIN <= v <= SEED_MAX):
            result.add_error(f"시드는 {SEED_MIN}~{SEED_MAX} 범위여야 합니다 (받은 값: {v})")
            return None
        return v

    @staticmethod
    def validate_prompt(text: str, name: str, result: ValidationResult) -> str:
        if text is None:
            return ""
        s = str(text)
        if len(s) > PROMPT_TOKEN_WARN:
            result.add_warning(f"{name} 길이가 깁니다 ({len(s)}자) — 토큰 한계 초과 가능")
        return s

    @classmethod
    def validate(cls, payload: dict) -> ValidationResult:
        """payload 전체 일괄 검증. 값은 변경하지 않고 보고만 한다."""
        r = ValidationResult()
        cls.validate_dimension(payload.get('width'), '가로(width)', r)
        cls.validate_dimension(payload.get('height'), '세로(height)', r)
        cls.validate_steps(payload.get('steps'), r)
        cls.validate_cfg(payload.get('cfg_scale'), r)
        if 'seed' in payload:
            cls.validate_seed(payload.get('seed'), r)
        cls.validate_prompt(payload.get('prompt', ''), '프롬프트', r)
        cls.validate_prompt(payload.get('negative_prompt', ''), '네거티브', r)
        return r
