# utils/atomic_json.py
"""원자적 JSON 파일 쓰기 공용 유틸.

직접 open(path,'w') + json.dump 는 쓰는 도중 강제 종료/디스크 오류 시
파일이 절단되어 JSON 전체가 손상된다. tmp 파일에 완전히 쓴 뒤
os.replace(동일 볼륨에서 원자적)로 교체하면 '이전 버전 그대로' 또는
'새 버전 완성본' 둘 중 하나만 존재한다.

읽기 측: load_json_safe 는 손상 파일을 만나면 .corrupt 백업으로 옮겨
사용자가 복구할 수 있게 한다 — 조용히 빈 컨테이너를 돌려준 뒤 다음
저장이 빈 데이터로 덮어써 영구 소실되는 패턴을 방지.
"""
import os
import json


def atomic_write_json(path: str, data, *, indent=2, ensure_ascii=False):
    """data를 path에 원자적으로 기록. 실패 시 예외 전파(호출자가 처리)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
    os.replace(tmp, path)


def load_json_safe(path: str, default, *, backup_corrupt: bool = True):
    """JSON 로드. 없으면 default, 손상이면 .corrupt로 백업 후 default.

    default 타입(list/dict)과 다른 루트 타입이 로드되면 default 반환.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if default is not None and not isinstance(data, type(default)):
            return default
        return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        if backup_corrupt:
            try:
                corrupt = path + '.corrupt'
                if os.path.exists(corrupt):
                    os.remove(corrupt)
                os.replace(path, corrupt)
            except OSError:
                pass
        return default
    except OSError:
        return default
