"""생성 중 자동화 토글 — 되돌림이 자기 자신을 다시 부르지 않고, 알림은 한 번만."""
from __future__ import annotations

import sys
import unittest

from ui.generator_actions import ActionsMixin
from ui.widget_proxies import ButtonProxy


class _FakeBridge:
    def __init__(self):
        self.pushed = []
        self.notes = []

        class _Sig:
            def __init__(inner, sink):
                inner._sink = sink

            def emit(inner, *args):
                inner._sink.append(args)

        self.showNotification = _Sig(self.notes)

    def _register_proxy(self, widget_id, proxy):
        pass

    def pushWidgetProperty(self, widget_id, prop, value):
        self.pushed.append((widget_id, prop, value))

    def pushWidgetValue(self, widget_id, value):
        self.pushed.append((widget_id, 'value', value))


class _RunningWorker:
    def isRunning(self):
        return True


class _Subject(ActionsMixin):
    """GeneratorMainUI 의 조각 — 토글 버튼·생성 워커·브리지만."""

    def __init__(self, generating: bool):
        self.vue_bridge = _FakeBridge()
        self.btn_auto_toggle = ButtonProxy(self.vue_bridge, 'btn_auto_toggle')
        self.btn_auto_toggle.setCheckable(True)
        self.btn_auto_toggle.toggled.connect(self.toggle_automation_ui)
        self.gen_worker = _RunningWorker() if generating else None
        self.is_automating = False
        self.btn_generate = ButtonProxy(self.vue_bridge, 'btn_generate')


class AutomationToggleGuardTests(unittest.TestCase):
    def test_toggle_during_generation_reverts_once_without_recursion(self):
        subject = _Subject(generating=True)
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(400)   # 예전 코드는 여기서 RecursionError 가 났다
        try:
            subject.btn_auto_toggle.setChecked(True)   # Vue 의 toggle_automation 액션이 하는 일
        finally:
            sys.setrecursionlimit(limit)
        self.assertFalse(subject.btn_auto_toggle.isChecked(), "생성 중엔 켜지지 않는다")
        self.assertEqual(len(subject.vue_bridge.notes), 1, "알림은 한 번")
        self.assertEqual(subject.vue_bridge.notes[0][0], 'warning')
        # 되돌린 값은 Vue 로 나갔다(잠시 켜졌다 꺼진 두 번의 push)
        pushes = [v for wid, prop, v in subject.vue_bridge.pushed if wid == 'btn_auto_toggle' and prop == 'checked']
        self.assertEqual(pushes, [True, False])

    def test_repeated_clicks_do_not_spam_notifications(self):
        subject = _Subject(generating=True)
        for _ in range(5):
            subject.btn_auto_toggle.setChecked(True)
        self.assertEqual(len(subject.vue_bridge.notes), 1)
        self.assertFalse(subject.btn_auto_toggle.isChecked())

    def test_toggle_when_idle_turns_on(self):
        subject = _Subject(generating=False)
        subject.btn_auto_toggle.setChecked(True)
        self.assertTrue(subject.btn_auto_toggle.isChecked())
        self.assertEqual(subject.vue_bridge.notes, [])
        self.assertEqual(subject.btn_generate.text(), "자동화 시작")


if __name__ == "__main__":
    unittest.main()
