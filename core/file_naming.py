# core/file_naming.py
"""사용자 입력 → 안전한 파일명 정규화 공용 유틸. UI/Qt 의존 없음(테스트 가능).

프리셋/와일드카드/파일 이름변경 등 사용자가 입력한 이름이 그대로
os.path.join에 합쳐지면 '../' 나 절대경로로 다른 설정 파일을 덮어쓰거나
지울 수 있다(예: 프리셋 이름 "../config/ui_prefs"). 구분자·예약 문자를
제거해 '해당 디렉토리 안의 단일 파일명'만 되도록 강제한다.

(core/workflow_profiles.py의 _sanitize_name을 공용 승격 + Windows 예약어 처리)
"""
import re

# Windows 예약 장치 이름 — 확장자가 붙어도 예약됨 (con.json 등)
_RESERVED = {
    'con', 'prn', 'aux', 'nul',
    *(f'com{i}' for i in range(1, 10)),
    *(f'lpt{i}' for i in range(1, 10)),
}


def sanitize_filename(name: str, fallback: str = "untitled", max_len: int = 64) -> str:
    """파일명 안전 — 구분자/예약 문자 제거, 예약어 회피, 길이 제한.

    슬래시·백슬래시·콜론을 제거하므로 '..'만 남아도 구분자가 없어
    경로 탈출이 불가능하다. 빈 결과는 fallback.
    """
    s = (name or "").strip()
    # 위험 문자 제거 (백슬래시, 슬래시, 콜론, 와일드카드, 따옴표, 리다이렉트, 파이프)
    s = re.sub(r'[\\/:*?"<>|]', '', s)
    # 제어 문자 제거
    s = re.sub(r'[\x00-\x1f]', '', s)
    # 윈도우는 끝의 점/공백을 무시 → 잘라서 의도와 실제 파일명 불일치 방지
    s = s.rstrip('. ')
    if s.split('.')[0].lower() in _RESERVED:
        s = '_' + s
    return s[:max_len] or fallback
