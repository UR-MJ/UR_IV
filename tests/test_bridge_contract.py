"""브리지 계약 정합성 테스트 — 프론트(Vue) ↔ 백엔드(PyQt) 이름 불일치 회귀 방지.

'브리지 계약 불일치 = 버그 주원인' (CLAUDE.md). 예전 실제 버그:
  - 프론트가 requestAction('X')/action('X')를 부르는데 Python에 핸들러(action=='X')가 없음
  - 프론트가 onBackendEvent('Y')를 듣는데 Python에 pyqtSignal Y가 없음
  - 페이로드 키 불일치 (조건식 target vs tags) 등
이 테스트는 소스를 정적 분석해 위 '이름' 불일치를 컴파일 타임처럼 잡는다.
(Qt 비의존 — 순수 텍스트 파싱.)
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONT = os.path.join(ROOT, 'frontend', 'src')
UI = os.path.join(ROOT, 'ui')

# 프론트가 부르지만 Python 핸들러가 없어도 되는 예외(동적/특수). 비어 있으면 전부 매칭 요구.
ACTION_ALLOWLIST: set = set()
# 프론트가 듣지만 pyqtSignal이 없어도 되는 예외.
EVENT_ALLOWLIST: set = set()

_RQ = re.compile(r"requestAction\(\s*['\"]([a-zA-Z_]\w*)['\"]")
# action('X') 래퍼 — 'requestAction'(대문자 A)/'foo.action'(메서드)은 제외
_AW = re.compile(r"(?<![A-Za-z_.])action\(\s*['\"]([a-zA-Z_]\w*)['\"]")
_EV = re.compile(r"onBackendEvent\(\s*['\"]([a-zA-Z_]\w*)['\"]")
_EQ = re.compile(r"action\s*==\s*['\"]([a-zA-Z_]\w*)['\"]")
_IN = re.compile(r"action\s+in\s*\(([^)]*)\)")
_LIT = re.compile(r"['\"]([a-zA-Z_]\w*)['\"]")
_SIG = re.compile(r"^\s*([a-zA-Z_]\w*)\s*=\s*pyqtSignal", re.M)


def _read_all(folder, exts):
    out = []
    for dirpath, _dirs, files in os.walk(folder):
        for fn in files:
            if fn.endswith(exts):
                try:
                    with open(os.path.join(dirpath, fn), encoding='utf-8') as f:
                        out.append(f.read())
                except OSError:
                    pass
    return out


def _frontend_actions(texts):
    names = set()
    for t in texts:
        names.update(_RQ.findall(t))
        names.update(_AW.findall(t))
    return names


def _frontend_events(texts):
    names = set()
    for t in texts:
        names.update(_EV.findall(t))
    return names


def _python_actions(texts):
    names = set()
    for t in texts:
        names.update(_EQ.findall(t))
        for grp in _IN.findall(t):
            names.update(_LIT.findall(grp))
    return names


class TestBridgeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.front = _read_all(FRONT, ('.vue', '.js'))
        cls.ui = _read_all(UI, ('.py',))
        with open(os.path.join(UI, 'vue_bridge.py'), encoding='utf-8') as f:
            cls.signals = _SIG.findall(f.read())

    def test_extraction_not_empty(self):
        # 안전장치 — 추출 0건이면 경로/정규식이 깨진 것(거짓 통과 방지)
        self.assertGreater(len(_frontend_actions(self.front)), 20)
        self.assertGreater(len(_python_actions(self.ui)), 20)
        self.assertGreater(len(self.signals), 20)
        self.assertGreater(len(_frontend_events(self.front)), 20)

    def test_every_frontend_action_has_python_handler(self):
        emitted = _frontend_actions(self.front)
        handled = _python_actions(self.ui)
        missing = emitted - handled - ACTION_ALLOWLIST
        self.assertEqual(
            missing, set(),
            f"프론트가 호출하지만 Python 핸들러(action=='X' / in (...))가 없는 액션: {sorted(missing)}")

    def test_every_frontend_event_has_signal(self):
        listened = _frontend_events(self.front)
        signals = set(self.signals)
        missing = listened - signals - EVENT_ALLOWLIST
        self.assertEqual(
            missing, set(),
            f"프론트가 onBackendEvent로 듣지만 pyqtSignal이 없는 이벤트: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
