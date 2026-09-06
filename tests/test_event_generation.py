"""Event Gen Vue-to-queue contract regression tests."""

from __future__ import annotations

import math
import unittest

from core.event_generation import (
    MAX_EVENT_SCENARIOS,
    EventGenerationPlanError,
    plan_event_generation,
)
from ui.generator_main import GeneratorMainUI
from ui.model_download_actions import ModelDownloadActionsMixin


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _Bridge:
    def __init__(self):
        self.showNotification = _Signal()


class _QueueManager:
    def __init__(self):
        self.start_count = 0

    def start(self):
        self.start_count += 1


class _HiddenEventTab:
    def __getattribute__(self, name):
        raise AssertionError(f"hidden EventGen tab was accessed: {name}")


class _Harness(ModelDownloadActionsMixin):
    _handle_vue_action = GeneratorMainUI._handle_vue_action
    _handle_event_generation_request = (
        GeneratorMainUI._handle_event_generation_request
    )
    _start_event_search = GeneratorMainUI._start_event_search

    def __init__(self):
        self.vue_bridge = _Bridge()
        self.queue_manager = _QueueManager()
        self.event_gen_tab = _HiddenEventTab()
        self.received = []
        self.statuses = []
        self.search_runs = []
        self.load_requests = []

    def _handle_creator_action(self, _action, _payload):
        return False

    def _handle_chat_action(self, _action, _payload):
        return False

    def receive_event_scenarios(self, scenarios):
        self.received.append(scenarios)

    def show_status(self, message):
        self.statuses.append(message)

    def _run_event_search_worker(self, loader, payload):
        self.search_runs.append((loader, payload))

    def _auto_load_event_data(self, ratings):
        self.load_requests.append(ratings)


def _request(prompt="1girl"):
    return {
        "scenarios": [
            {
                "name": "Step 0",
                "payload": {
                    "prompt": prompt,
                    "negative_prompt": "low quality",
                    "steps": 25,
                    "alwayson_scripts": {"NegPiP": {"args": [True]}},
                },
            }
        ]
    }


class EventGenerationPlanTests(unittest.TestCase):
    def test_plan_validates_detaches_and_preserves_queue_payload(self):
        request = _request(" 1girl, blue hair ")

        plan = plan_event_generation(request)

        self.assertEqual(plan.count, 1)
        self.assertEqual(plan.scenarios[0]["name"], "Step 0")
        self.assertEqual(
            plan.scenarios[0]["payload"],
            {
                "prompt": "1girl, blue hair",
                "negative_prompt": "low quality",
                "steps": 25,
                "alwayson_scripts": {"NegPiP": {"args": [True]}},
            },
        )
        request["scenarios"][0]["payload"]["prompt"] = "changed"
        request["scenarios"][0]["payload"]["alwayson_scripts"]["NegPiP"][
            "args"
        ][0] = False
        self.assertEqual(plan.scenarios[0]["payload"]["prompt"], "1girl, blue hair")
        self.assertEqual(
            plan.scenarios[0]["payload"]["alwayson_scripts"]["NegPiP"][
                "args"
            ],
            [True],
        )

    def test_missing_or_invalid_scenarios_fail_the_whole_plan(self):
        invalid_requests = (
            None,
            {},
            {"scenarios": []},
            {"scenarios": [None]},
            {"scenarios": [{}]},
            {"scenarios": [{"payload": {"prompt": "   "}}]},
            {"scenarios": [{"payload": {"prompt": "ok", "negative_prompt": 3}}]},
            {"scenarios": [{"payload": {"prompt": "ok", "cfg_scale": math.inf}}]},
        )

        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaises(EventGenerationPlanError):
                    plan_event_generation(request)

    def test_plan_has_a_bounded_scenario_count(self):
        scenario = {"payload": {"prompt": "ok"}}
        with self.assertRaises(EventGenerationPlanError):
            plan_event_generation(
                {"scenarios": [scenario] * (MAX_EVENT_SCENARIOS + 1)}
            )


class EventGenerationActionTests(unittest.TestCase):
    def test_generate_now_enqueues_exact_vue_plan_and_starts_queue(self):
        harness = _Harness()
        request = _request("vue prompt")

        harness._handle_vue_action("event_generate_now", request)

        self.assertEqual(len(harness.received), 1)
        self.assertEqual(
            harness.received[0][0]["payload"]["prompt"], "vue prompt"
        )
        self.assertEqual(harness.queue_manager.start_count, 1)

    def test_add_to_queue_does_not_start_processing(self):
        harness = _Harness()

        harness._handle_vue_action("event_add_to_queue", _request())

        self.assertEqual(len(harness.received), 1)
        self.assertEqual(harness.queue_manager.start_count, 0)

    def test_invalid_request_neither_enqueues_nor_starts(self):
        harness = _Harness()

        harness._handle_vue_action("event_generate_now", {"scenarios": []})

        self.assertEqual(harness.received, [])
        self.assertEqual(harness.queue_manager.start_count, 0)
        self.assertEqual(harness.vue_bridge.showNotification.calls[0][0], "warning")

    def test_select_event_never_touches_hidden_pyqt_result_list(self):
        harness = _Harness()

        harness._handle_vue_action("select_event", {"index": 4})

        self.assertEqual(harness.received, [])
        self.assertEqual(harness.queue_manager.start_count, 0)

    def test_event_search_uses_window_owned_loader_not_hidden_tab(self):
        harness = _Harness()
        loader = object()
        harness._event_loader = loader
        harness._event_loader_ratings = ("g",)
        payload = {"ratings": ["g"], "prompt": "running"}

        harness._start_event_search(payload)

        self.assertEqual(harness.search_runs, [(loader, payload)])
        self.assertEqual(harness.load_requests, [])

    def test_event_search_reloads_when_rating_selection_changes(self):
        harness = _Harness()
        harness._event_loader = object()
        harness._event_loader_ratings = ("g",)
        payload = {"ratings": ["s", "q"], "prompt": "running"}

        harness._start_event_search(payload)

        self.assertEqual(harness.search_runs, [])
        self.assertEqual(harness.load_requests, [("s", "q")])
        self.assertIs(harness._pending_event_payload, payload)


if __name__ == "__main__":
    unittest.main()
