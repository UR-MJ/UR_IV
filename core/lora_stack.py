"""LoRA 스택 → 생성용 텍스트 변환 (순수 함수, Qt 비의존, 테스트 용이).

config/ui_prefs.json 의 loraStack 단일 소스 엔트리
    {name: str, weight: int(%), enabled: bool, triggerWords: list}
를 App.vue(doGenerate)와 동일한 ``<lora:name:weight>`` 텍스트로 만든다.

App.vue 기준(weight는 정수 퍼센트로 저장 → 생성 시 /100, 소수 2자리):
    activeLoras.map(l => `<lora:${l.name}:${(l.weight/100).toFixed(2)}>`).join(', ')
"""
from typing import Iterable


def build_lora_text(entries: Iterable) -> str:
    """enabled LoRA 엔트리들을 ``<lora:name:weight>, ...`` 문자열로.
    name 없으면/enabled=False면 제외. weight는 정수%→소수(0.00). 빈 입력→''."""
    parts = []
    for l in entries or []:
        if not isinstance(l, dict) or l.get("enabled", True) is False:
            continue
        name = str(l.get("name", "")).strip()
        if not name:
            continue
        try:
            w = float(l.get("weight", 100)) / 100.0
        except (TypeError, ValueError):
            w = 1.0
        parts.append(f"<lora:{name}:{w:.2f}>")
    return ", ".join(parts)
