"""Event Gen generation requests, independent from any UI implementation.

The Vue view owns event/step selection.  This module is the seam where its
request becomes a validated queue plan; callers never need to know about the
legacy PyQt EventGenTab state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


MAX_EVENT_SCENARIOS = 10_000


class EventGenerationPlanError(ValueError):
    """Raised when an Event Gen request cannot safely become queue work."""


@dataclass(frozen=True)
class EventGenerationPlan:
    """Validated scenario envelopes in their queue-compatible shape."""

    scenarios: tuple[dict[str, Any], ...]

    @property
    def count(self) -> int:
        return len(self.scenarios)


def plan_event_generation(request: object) -> EventGenerationPlan:
    """Validate and detach a Vue Event Gen request from caller-owned state.

    The accepted interface is ``{"scenarios": [{"payload": {...}}, ...]}``.
    A scenario payload must contain a non-empty string ``prompt``.  Values must
    be JSON-compatible because the same contract crosses QWebChannel.
    """

    if not isinstance(request, Mapping):
        raise EventGenerationPlanError("이벤트 생성 요청 형식이 올바르지 않습니다")

    raw_scenarios = request.get("scenarios")
    if not isinstance(raw_scenarios, list):
        raise EventGenerationPlanError("이벤트 시나리오 목록이 필요합니다")
    if not raw_scenarios:
        raise EventGenerationPlanError("선택된 이벤트 스텝이 없습니다")
    if len(raw_scenarios) > MAX_EVENT_SCENARIOS:
        raise EventGenerationPlanError(
            f"이벤트 시나리오는 최대 {MAX_EVENT_SCENARIOS:,}개까지 처리할 수 있습니다"
        )

    scenarios: list[dict[str, Any]] = []
    for index, raw_scenario in enumerate(raw_scenarios):
        if not isinstance(raw_scenario, Mapping):
            raise EventGenerationPlanError(
                f"이벤트 시나리오 {index + 1}의 형식이 올바르지 않습니다"
            )

        raw_payload = raw_scenario.get("payload")
        if not isinstance(raw_payload, Mapping):
            raise EventGenerationPlanError(
                f"이벤트 시나리오 {index + 1}에 생성 설정이 없습니다"
            )

        scenario = _clone_mapping(raw_scenario, f"scenarios[{index}]")
        payload = scenario["payload"]
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise EventGenerationPlanError(
                f"이벤트 시나리오 {index + 1}에 프롬프트가 없습니다"
            )

        payload["prompt"] = prompt.strip()
        negative_prompt = payload.get("negative_prompt", "")
        if not isinstance(negative_prompt, str):
            raise EventGenerationPlanError(
                f"이벤트 시나리오 {index + 1}의 네거티브 프롬프트 형식이 올바르지 않습니다"
            )
        payload["negative_prompt"] = negative_prompt
        scenarios.append(scenario)

    return EventGenerationPlan(tuple(scenarios))


def _clone_mapping(value: Mapping[object, object], location: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise EventGenerationPlanError(f"{location}의 키는 문자열이어야 합니다")
        result[key] = _clone_json_value(item, f"{location}.{key}")
    return result


def _clone_json_value(value: object, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EventGenerationPlanError(f"{location}에 유효하지 않은 숫자가 있습니다")
        return value
    if isinstance(value, Mapping):
        return _clone_mapping(value, location)
    if isinstance(value, (list, tuple)):
        return [
            _clone_json_value(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise EventGenerationPlanError(f"{location}에 지원하지 않는 값이 있습니다")
