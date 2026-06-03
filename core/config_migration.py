# core/config_migration.py
"""JSON 설정 파일의 스키마 버전 관리 + 마이그레이션.

앞으로 설정 필드가 추가/제거/이름변경될 때, 기존 사용자 파일을 조용히
현재 스키마로 올려주기 위한 공용 로더. 기존 파일이 schema_version을
포함하지 않으면 0으로 간주한다.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Callable

logger = logging.getLogger(__name__)

# 각 설정 파일별 마이그레이션 맵을 이 모듈에 중앙화.
# 키: 파일의 논리 이름 — 값: {from_version: migrator(dict) -> dict}
_UI_PREFS_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    # 향후 추가 예시:
    # 0: lambda d: {**d, 'new_field': False},
    # 1: lambda d: {...},
}
UI_PREFS_CURRENT_VERSION = 1


def load_and_migrate(
    path: str,
    migrations: dict[int, Callable[[dict], dict]],
    current_version: int,
) -> dict:
    """설정을 읽고 필요한 마이그레이션을 적용 후 반환.

    - 파일이 없으면 {} 반환
    - schema_version 누락 시 0으로 시작
    - 각 단계 실패 시 .bak 백업 생성 후 빈 dict로 fallback
    """
    if not os.path.exists(path):
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("config load failed (%s): %s", path, e)
        return {}

    if not isinstance(data, dict):
        return {}

    version = int(data.get('schema_version', 0) or 0)
    if version == current_version:
        return data

    if version > current_version:
        logger.warning(
            "config %s has newer schema_version %d > %d; using as-is",
            path, version, current_version,
        )
        return data

    # 단계별 마이그레이션
    bak = path + '.bak'
    try:
        shutil.copy2(path, bak)
    except OSError:
        # 백업 실패는 치명적이지 않음 — 진행은 계속
        logger.warning("backup failed for %s", path)

    while version < current_version:
        migrator = migrations.get(version)
        if migrator is None:
            logger.warning("no migrator from v%d — stopping", version)
            break
        try:
            data = migrator(data)
        except Exception as e:
            logger.exception("migration v%d → v%d failed for %s: %s",
                             version, version + 1, path, e)
            break
        version += 1
        data['schema_version'] = version
    return data


def save_with_version(path: str, data: dict, schema_version: int) -> None:
    """schema_version 필드를 주입하고 저장."""
    out = dict(data)
    out['schema_version'] = schema_version
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_ui_prefs(path: str) -> dict:
    return load_and_migrate(path, _UI_PREFS_MIGRATIONS, UI_PREFS_CURRENT_VERSION)


def save_ui_prefs(path: str, data: dict) -> None:
    save_with_version(path, data, UI_PREFS_CURRENT_VERSION)
