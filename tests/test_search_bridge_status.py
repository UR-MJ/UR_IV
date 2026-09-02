from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSignal

from ui.vue_bridge import VueBridge


class _FakeSearchWorker(QObject):
    results_ready = pyqtSignal(list, int)
    status_update = pyqtSignal(str)

    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self._running = False

    def start(self) -> None:
        self._running = True

    def isRunning(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False

    def wait(self, _milliseconds: int) -> bool:
        return True


class SearchBridgeStatusTests(unittest.TestCase):
    def test_worker_error_status_reaches_the_search_view_channel(self) -> None:
        bridge = VueBridge()
        statuses = []
        bridge.searchStatus.connect(statuses.append)

        with patch(
            "workers.search_worker.PandasSearchWorker",
            _FakeSearchWorker,
        ):
            bridge.searchDanbooru(json.dumps({"ratings": ["g"]}))
            bridge._search_worker.status_update.emit(
                "❌ 활성 검색 shard 검증 실패"
            )

        self.assertIn("❌ 활성 검색 shard 검증 실패", statuses)

    def test_replaced_worker_cannot_publish_a_late_error_status(self) -> None:
        bridge = VueBridge()
        statuses = []
        bridge.searchStatus.connect(statuses.append)

        with patch(
            "workers.search_worker.PandasSearchWorker",
            _FakeSearchWorker,
        ):
            bridge.searchDanbooru(json.dumps({"ratings": ["g"]}))
            first = bridge._search_worker
            bridge.searchDanbooru(json.dumps({"ratings": ["s"]}))
            first.status_update.emit("❌ 오래된 worker 오류")

        self.assertNotIn("❌ 오래된 worker 오류", statuses)

    def test_rejected_result_cannot_be_overwritten_by_late_success_status(self) -> None:
        bridge = VueBridge()
        statuses = []
        bridge.searchStatus.connect(statuses.append)

        with patch(
            "workers.search_worker.PandasSearchWorker",
            _FakeSearchWorker,
        ):
            bridge.searchDanbooru(json.dumps({"ratings": ["g"]}))
            worker = bridge._search_worker
            worker.results_ready.emit([{"general": "unverified"}], 1)
            worker.status_update.emit("✅ 검색 완료: 1건")

        self.assertTrue(statuses[-1].startswith("❌"), statuses)
        self.assertNotIn("✅ 검색 완료: 1건", statuses)

    def test_manifest_change_during_result_processing_prevents_publication_and_runtime_mutation(
        self,
    ) -> None:
        verified_identity = {"label": "2026_07", "fingerprint": "a" * 64}
        changed_identity = {"label": "2026_07", "fingerprint": "b" * 64}
        previous_identity = {"label": "previous", "fingerprint": "c" * 64}

        class Parent(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.filtered_results = [{"general": "existing"}]
                self.shuffled_prompt_deck = [{"general": "existing-deck"}]
                self._search_dataset_identity = previous_identity
                self._search_snapshot_id = "d" * 32
                self.persist_calls = []
                self.deck_save_calls = 0

            def _persist_search_results(self, *args, **kwargs) -> None:
                self.persist_calls.append((args, kwargs))

            def _save_deck_state(self) -> None:
                self.deck_save_calls += 1

        class Store:
            dataset_info_calls = 0
            changed_during_serialization = False

            def dataset_info(self):
                type(self).dataset_info_calls += 1
                return (
                    changed_identity
                    if type(self).changed_during_serialization
                    else verified_identity
                )

        real_dumps = json.dumps

        def dumps_and_change(value, *args, **kwargs):
            encoded = real_dumps(value, *args, **kwargs)
            if isinstance(value, list):
                Store.changed_during_serialization = True
            return encoded

        parent = Parent()
        bridge = VueBridge(parent)
        statuses = []
        published = []
        lineages = []
        bridge.searchStatus.connect(statuses.append)
        bridge.searchResultsReady.connect(lambda payload: published.append(json.loads(payload)))
        bridge.searchResultLineage.connect(lambda payload: lineages.append(json.loads(payload)))
        query_json = real_dumps({"ratings": ["g"]})

        with (
            patch("workers.search_worker.PandasSearchWorker", _FakeSearchWorker),
            patch("core.search_result_store.SearchResultStore", Store),
            patch("ui.vue_bridge.json.dumps", side_effect=dumps_and_change),
        ):
            bridge.searchDanbooru(query_json)
            worker = bridge._search_worker
            worker.dataset_identity = verified_identity
            worker.results_ready.emit([{"general": "new-result"}], 1)
            worker.status_update.emit("✅ 검색 완료: 1건")

        self.assertEqual(Store.dataset_info_calls, 2)
        self.assertEqual(published, [])
        self.assertEqual(lineages, [])
        self.assertTrue(statuses[-1].startswith("❌"), statuses)
        self.assertNotIn("✅ 검색 완료: 1건", statuses)
        self.assertEqual(parent.filtered_results, [{"general": "existing"}])
        self.assertEqual(parent.shuffled_prompt_deck, [{"general": "existing-deck"}])
        self.assertEqual(parent._search_dataset_identity, previous_identity)
        self.assertEqual(parent._search_snapshot_id, "d" * 32)
        self.assertEqual(parent.persist_calls, [])
        self.assertEqual(parent.deck_save_calls, 0)

    def test_accepted_result_publishes_lineage_before_rows(self) -> None:
        identity = {"label": "2026_07", "fingerprint": "a" * 64}

        class Store:
            @staticmethod
            def dataset_info():
                return identity

            @staticmethod
            def save(*_args, **_kwargs):
                return None

        bridge = VueBridge()
        events = []
        bridge.searchResultLineage.connect(
            lambda payload: events.append(("lineage", json.loads(payload)))
        )
        bridge.searchResultsReady.connect(
            lambda payload: events.append(("results", json.loads(payload)))
        )

        with (
            patch("workers.search_worker.PandasSearchWorker", _FakeSearchWorker),
            patch("core.search_result_store.SearchResultStore", Store),
        ):
            bridge.searchDanbooru(json.dumps({"ratings": ["g"]}))
            worker = bridge._search_worker
            worker.dataset_identity = identity
            worker.results_ready.emit([{"general": "accepted"}], 1)

        self.assertEqual(events[0][0], "lineage")
        self.assertEqual(events[0][1]["label"], "2026_07")
        self.assertEqual(events[0][1]["fingerprint"], "a" * 64)
        self.assertRegex(events[0][1]["snapshot_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(events[1], ("results", [{
            "copyright": "",
            "character": "",
            "artist": "",
            "general": "accepted",
            "rating": "",
            "image_width": None,
            "image_height": None,
        }]))

    def test_valid_empty_cache_restores_runtime_snapshot_lineage(self) -> None:
        identity = {"label": "2026_07", "fingerprint": "f" * 64}

        class Parent(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.filtered_results = [{"general": "stale"}]
                self.shuffled_prompt_deck = [{"general": "stale"}]

            @staticmethod
            def _restore_deck_state():
                return False

        class Store:
            last_error = None
            last_snapshot_id = "a" * 32
            last_dataset_identity = identity

            @staticmethod
            def load_active():
                return []

        parent = Parent()
        bridge = VueBridge(parent)
        lineages = []
        bridge.searchResultLineage.connect(
            lambda payload: lineages.append(json.loads(payload))
        )

        with patch("core.search_result_store.SearchResultStore", Store):
            self.assertEqual(json.loads(bridge.loadLastSearchResults()), [])

        self.assertEqual(parent._search_snapshot_id, "a" * 32)
        self.assertEqual(parent._search_dataset_identity, identity)
        self.assertEqual(parent.filtered_results, [])
        self.assertEqual(parent.shuffled_prompt_deck, [])
        self.assertEqual(lineages, [{
            **identity,
            "snapshot_id": "a" * 32,
        }])


if __name__ == "__main__":
    unittest.main()
