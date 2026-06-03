"""
Standard Hooks — 시작 시 PromptPipeline에 표준 훅을 일괄 등록.

기존 generator_prompts.py / generator_generation.py를 비파괴적으로 보강.
파이프라인은 기존 처리 *뒤*에 호출되므로 회귀 위험 없음.

등록 훅 (priority 낮을수록 먼저):
- AFTER_WILDCARD (50)   : ``$$name$$`` 인스턴트 와일드카드 확장
                          (instant_wildcards 모듈이 게으른 초기화 시 자동 등록)
- FINAL          (90)   : 메인 태그 중복 제거 + prefix/postfix 충돌 제거

향후 확장 예:
- RFP 압축, 빈도 제한 (사용자 설정 시)
- 조건부 명령 (사용자가 명령 텍스트 입력 시)
"""
from __future__ import annotations

from utils.app_logger import get_logger

_logger = get_logger("std_hooks")
_registered = False


def register_standard_hooks() -> int:
    """표준 훅 일괄 등록. 멱등 — 여러 번 호출돼도 한 번만 등록.

    :return: 새로 등록된 훅 개수
    """
    global _registered
    if _registered:
        return 0
    _registered = True

    from core.prompt_pipeline import get_pipeline, HookPoint
    from core.rfp_engine import make_dedupe_hook

    pl = get_pipeline()
    n = 0

    # FINAL — 중복 제거 + prefix/postfix 충돌 제거
    pl.register(
        HookPoint.FINAL,
        make_dedupe_hook(),
        priority=90,
        name="standard_dedupe",
    )
    n += 1

    # InstantWildcards 훅은 instant_wildcards.py가 게으르게 등록함
    # (사용자가 매니저 열거나 첫 액션 호출 시)

    _logger.info(f"표준 훅 {n}개 등록")
    return n


def run_pipeline_on_text(text: str, settings: dict | None = None) -> str:
    """문자열 프롬프트를 PromptContext로 감싸 파이프라인 실행 후 다시 문자열.

    생성 흐름의 컨버전스 포인트에서 호출 — 기존 처리 결과를 받아 추가 가공.

    빈 입력은 그대로 반환. 예외 시 원본 반환 (보수적).
    """
    if not text or not text.strip():
        return text
    try:
        from core.prompt_pipeline import get_pipeline, HookPoint, PromptContext
        ctx = PromptContext(
            main_tags=[t.strip() for t in text.split(",") if t.strip()],
            settings=settings or {},
        )
        pl = get_pipeline()
        # PRE/FIT_RESOLUTION/POST는 사용자가 직접 훅 추가 시에만 동작
        pl.execute(HookPoint.PRE_PROCESSING, ctx)
        pl.execute(HookPoint.FIT_RESOLUTION, ctx)
        pl.execute(HookPoint.POST_PROCESSING, ctx)
        pl.execute(HookPoint.AFTER_WILDCARD, ctx)
        pl.execute(HookPoint.FINAL, ctx)
        return ", ".join(ctx.main_tags)
    except Exception:
        _logger.exception("pipeline 실행 실패 — 원본 반환")
        return text
