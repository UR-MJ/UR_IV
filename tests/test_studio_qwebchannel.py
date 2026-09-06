"""Contract tests for the generic Studio QWebChannel Adapter."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal

from core.studio_application import (
    CallContext,
    StudioApplication,
    StudioApplicationError,
)
from ui.studio_qwebchannel import DesktopNativeHost, StudioQWebChannelAdapter


class _FakeApplication:
    def __init__(self) -> None:
        self.event_epoch = "fake-epoch"
        self.describe_context = None
        self.invoke_calls = []
        self.subscribe_context = None
        self.sink = None
        self.unsubscribe_count = 0
        self.subscribe_calls = []
        self.sinks = []
        self.subscribe_errors = {}

    def describe(self, context):
        self.describe_context = context
        return {
            "version": 1,
            "eventEpoch": self.event_epoch,
            "eventCursor": 0,
            "operations": [{"name": "runtime.list", "version": 1}],
        }

    def invoke(self, context, request):
        self.invoke_calls.append((context, request))
        return {
            "version": 1,
            "requestId": request["requestId"],
            "status": "ok",
            "data": {"echo": request["input"]},
            "seq": 4,
        }

    def subscribe(self, context, sink, after_seq=0):
        self.subscribe_context = context
        self.sink = sink
        self.subscribe_calls.append(after_seq)
        self.sinks.append(sink)
        if after_seq in self.subscribe_errors:
            raise self.subscribe_errors[after_seq]

        def unsubscribe():
            self.unsubscribe_count += 1

        return unsubscribe


class _Bridge(QObject):
    backendRuntimeEvent = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.refreshes = 0
        self.runtime_events = []
        self.backendRuntimeEvent.connect(
            lambda raw: self.runtime_events.append(json.loads(raw))
        )

    def _refresh_forge_module_widgets(self):
        self.refreshes += 1


class _RestartWindow(_Bridge):
    def __init__(self) -> None:
        super().__init__()
        self.quit_count = 0

    def _quit_app(self):
        self.quit_count += 1


class StudioQWebChannelAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.application = _FakeApplication()
        self.context = CallContext(
            principal_id="test-ui",
            transport="qwebchannel",
            capabilities=frozenset({"native"}),
        )
        self.adapter = StudioQWebChannelAdapter(self.application, self.context)

    def tearDown(self):
        self.adapter.close()

    def test_describe_and_invoke_forward_one_fixed_context(self):
        meta = self.adapter.metaObject()
        self.assertGreaterEqual(meta.indexOfSignal("event(QString)"), 0)
        self.assertGreaterEqual(meta.indexOfSlot("describe()"), 0)
        self.assertGreaterEqual(meta.indexOfSlot("invoke(QString)"), 0)

        description = json.loads(self.adapter.describe())
        self.assertEqual(description["operations"][0]["name"], "runtime.list")
        self.assertIs(self.application.describe_context, self.context)
        self.assertIsNone(self.application.subscribe_context)

        request = {
            "version": 1,
            "requestId": "req-1",
            "operation": "runtime.list",
            "input": {},
        }
        reply = json.loads(self.adapter.invoke(json.dumps(request)))
        self.assertEqual(reply["status"], "ok")
        self.assertEqual(reply["requestId"], "req-1")
        forwarded_context, forwarded_request = self.application.invoke_calls[0]
        self.assertIs(forwarded_context, self.context)
        self.assertEqual(forwarded_request, request)

    def test_invalid_json_is_rejected_before_application_dispatch(self):
        reply = json.loads(self.adapter.invoke("[1, 2, 3]"))
        self.assertEqual(reply["status"], "error")
        self.assertEqual(reply["error"]["code"], "INVALID_JSON")
        self.assertEqual(self.application.invoke_calls, [])

        non_finite = json.loads(self.adapter.invoke('{"requestId":"bad","input":NaN}'))
        self.assertEqual(non_finite["error"]["code"], "INVALID_JSON")
        self.assertEqual(self.application.invoke_calls, [])

    def test_application_events_are_forwarded_as_one_json_signal(self):
        received = []
        self.adapter.event.connect(received.append)
        self.assertEqual(json.loads(self.adapter.resume(0))["status"], "ok")
        event = {
            "version": 1,
            "eventEpoch": "fake-epoch",
            "seq": 5,
            "topic": "jobs/job-1",
            "type": "job.changed",
            "operation": "runtime.install",
            "jobId": "job-1",
            "phase": "progress",
            "data": {"percent": 50},
        }
        self.application.sink(event)
        self.assertEqual(json.loads(received[0]), event)

    def test_resume_replaces_subscription_and_replays_from_requested_cursor(self):
        meta = self.adapter.metaObject()
        self.assertGreaterEqual(meta.indexOfSlot("resume(int)"), 0)
        self.assertEqual(self.application.subscribe_calls, [])
        self.assertEqual(json.loads(self.adapter.resume(0))["status"], "ok")
        stale_sink = self.application.sinks[-1]

        reply = json.loads(self.adapter.resume(17))

        self.assertEqual(reply, {
            "version": 1,
            "status": "ok",
            "afterSeq": 17,
            "eventEpoch": "fake-epoch",
        })
        self.assertEqual(self.application.subscribe_calls, [0, 17])
        self.assertEqual(self.application.unsubscribe_count, 1)

        received = []
        self.adapter.event.connect(received.append)
        replayed = {
            "version": 1,
            "eventEpoch": "fake-epoch",
            "seq": 18,
            "topic": "runtime.operation",
            "type": "completed",
            "operation": "runtime.execute",
            "data": {},
        }
        stale_sink(replayed)
        self.assertEqual(received, [])
        self.application.sinks[-1](replayed)
        self.assertEqual(json.loads(received[-1]), replayed)

        invalid = json.loads(self.adapter.resume(-1))
        self.assertEqual(invalid["status"], "error")
        self.assertEqual(invalid["error"]["code"], "INVALID_CURSOR")
        self.assertEqual(self.application.subscribe_calls, [0, 17])

        self.adapter.close()
        closed = json.loads(self.adapter.resume(17))
        self.assertEqual(closed["status"], "error")
        self.assertEqual(closed["error"]["code"], "UNAVAILABLE")
        self.assertEqual(self.application.subscribe_calls, [0, 17])

    def test_resume_preserves_structured_cursor_expired_error(self):
        self.application.subscribe_errors[17] = StudioApplicationError(
            "CURSOR_EXPIRED",
            "event cursor가 보관 범위를 벗어났습니다",
            retryable=True,
            details={"earliestSeq": 20, "currentSeq": 1043},
        )

        reply = json.loads(self.adapter.resume(17))

        self.assertEqual(reply["status"], "error")
        self.assertEqual(reply["eventEpoch"], "fake-epoch")
        self.assertEqual(reply["error"], {
            "code": "CURSOR_EXPIRED",
            "message": "event cursor가 보관 범위를 벗어났습니다",
            "retryable": True,
            "details": {"earliestSeq": 20, "currentSeq": 1043},
        })

    def test_constructor_is_lazy_when_cursor_zero_is_no_longer_replayable(self):
        application = _FakeApplication()
        application.subscribe_errors[0] = StudioApplicationError(
            "CURSOR_EXPIRED",
            "zero cursor expired",
            retryable=True,
            details={"earliestSeq": 2, "currentSeq": 1025},
        )

        adapter = StudioQWebChannelAdapter(application, self.context)
        try:
            self.assertEqual(application.subscribe_calls, [])
            self.assertEqual(json.loads(adapter.describe())["eventEpoch"], "fake-epoch")
            reply = json.loads(adapter.resume(0))
            self.assertEqual(reply["error"]["code"], "CURSOR_EXPIRED")
        finally:
            adapter.close()

    def test_close_unsubscribes_once(self):
        self.assertEqual(json.loads(self.adapter.resume(0))["status"], "ok")
        self.adapter.close()
        self.adapter.close()
        self.assertEqual(self.application.unsubscribe_count, 1)

    def test_desktop_native_host_picks_directory_and_refreshes_bridge(self):
        bridge = _Bridge()
        host = DesktopNativeHost(bridge, bridge)
        with tempfile.TemporaryDirectory() as temp:
            chosen = str(Path(temp) / "chosen")
            with patch(
                "ui.studio_qwebchannel.select_directory",
                return_value=chosen,
            ) as picker:
                result = host.pick_directory("runtime_install", "forge", temp)
        self.assertEqual(result, chosen)
        self.assertIn("Forge Neo", picker.call_args.args[1])
        self.assertIs(picker.call_args.args[0], bridge)
        self.assertEqual(picker.call_args.args[2], temp)
        host.refresh_model_widgets()
        self.assertEqual(bridge.refreshes, 1)

    def test_desktop_native_host_forwards_runtime_event_on_qt_thread(self):
        bridge = _Bridge()
        host = DesktopNativeHost(bridge, bridge)
        payload = {
            "type": "completed",
            "engine": "forge",
            "operationId": "job-1",
        }

        worker = threading.Thread(target=host.handle_runtime_event, args=(payload,))
        worker.start()
        worker.join(1)
        deadline = time.monotonic() + 1
        while not bridge.runtime_events and time.monotonic() < deadline:
            self.qt_app.processEvents()

        self.assertEqual(bridge.runtime_events, [payload])

    def test_desktop_native_host_schedules_clean_restart_on_qt_thread(self):
        window = _RestartWindow()
        host = DesktopNativeHost(window, window)
        scheduled = []

        with patch(
            "ui.studio_qwebchannel.QTimer.singleShot",
            side_effect=lambda delay, callback: scheduled.append((delay, callback)),
        ):
            worker = threading.Thread(
                target=host.request_app_restart,
                args=({"restartRequired": True},),
            )
            worker.start()
            worker.join(1)
            deadline = time.monotonic() + 1
            while not scheduled and time.monotonic() < deadline:
                self.qt_app.processEvents()

        self.assertEqual(len(scheduled), 1)
        self.assertGreaterEqual(scheduled[0][0], 1000)
        scheduled[0][1]()
        self.assertEqual(window.quit_count, 1)

    def test_web_context_cannot_reach_native_host(self):
        class NativeHostSpy:
            calls = 0

            def pick_directory(self, kind, selector, current):
                self.calls += 1
                return "C:/should-not-be-visible"

        host = NativeHostSpy()
        application = StudioApplication(host=host)
        adapter = StudioQWebChannelAdapter(
            application,
            CallContext(
                principal_id="web-ui",
                transport="qwebchannel-websocket",
                capabilities=frozenset(),
            ),
        )
        try:
            reply = json.loads(adapter.invoke(json.dumps({
                "version": 1,
                "requestId": "web-native-denied",
                "operation": "native.pick_directory",
                "input": {"purpose": "runtime_install", "engine": "forge"},
            })))
        finally:
            adapter.close()
        self.assertEqual(reply["status"], "error")
        self.assertEqual(reply["error"]["code"], "FORBIDDEN")
        self.assertEqual(host.calls, 0)


if __name__ == "__main__":
    unittest.main()
