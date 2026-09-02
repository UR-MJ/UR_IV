from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ui.generator_actions import ActionsMixin
from ui.generator_main import GeneratorMainUI


_TEST_IDENTITY = {"label": "2026_07", "fingerprint": "f" * 64}
_TEST_SNAPSHOT = "f" * 32
_TEST_LINEAGE = {**_TEST_IDENTITY, "snapshot_id": _TEST_SNAPSHOT}


class _DeckSubject(ActionsMixin):
    def __init__(self, path: Path) -> None:
        self._path = path

    def _deck_state_path(self):
        return str(self._path)


class SearchDeckStateTests(unittest.TestCase):
    def test_deck_round_trip_requires_the_same_search_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last_deck.json"
            rows = [{"general": "first"}, {"general": "second"}]
            snapshot_id = "a" * 32

            subject = _DeckSubject(path)
            subject.filtered_results = rows
            subject.shuffled_prompt_deck = [rows[1]]
            subject._search_snapshot_id = snapshot_id
            subject._save_deck_state()

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["snapshot_id"], snapshot_id)

            restored = _DeckSubject(path)
            restored.filtered_results = rows
            restored._search_snapshot_id = snapshot_id
            self.assertTrue(restored._restore_deck_state())
            self.assertEqual(restored.shuffled_prompt_deck, [rows[1]])

    def test_same_sized_deck_from_another_search_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last_deck.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "snapshot_id": "a" * 32,
                        "pool_size": 2,
                        "remaining": [1],
                    }
                ),
                encoding="utf-8",
            )
            subject = _DeckSubject(path)
            subject.filtered_results = [
                {"general": "different first"},
                {"general": "different second"},
            ]
            subject._search_snapshot_id = "b" * 32

            self.assertFalse(subject._restore_deck_state())

    def test_empty_vue_filter_clears_runtime_deck_and_persists_active_cache(self) -> None:
        class Subject:
            filtered_results = [{"general": "old"}]
            shuffled_prompt_deck = [{"general": "old"}]
            _rating_filter = {"g", "s", "q", "e"}
            _search_dataset_identity = _TEST_IDENTITY
            _search_snapshot_id = _TEST_SNAPSHOT

            def __init__(self) -> None:
                self.persisted = []
                self.deck_saves = 0
                self.statuses = []

            @staticmethod
            def _handle_creator_action(_action, _payload):
                return False

            @staticmethod
            def _handle_chat_action(_action, _payload):
                return False

            def _persist_search_results(self, active, full=None):
                self.persisted.append((active, full))

            def _save_deck_state(self):
                self.deck_saves += 1

            def show_status(self, message):
                self.statuses.append(message)

        subject = Subject()

        GeneratorMainUI._handle_vue_action(
            subject,
            "update_prompt_deck",
            {"results": [], "lineage": _TEST_LINEAGE},
        )

        self.assertEqual(subject.filtered_results, [])
        self.assertEqual(subject.shuffled_prompt_deck, [])
        self.assertEqual(subject.persisted, [([], None)])
        self.assertEqual(subject.deck_saves, 1)

    def test_empty_vue_filter_stops_running_automation(self) -> None:
        class Subject:
            filtered_results = [{"general": "old"}]
            shuffled_prompt_deck = [{"general": "old"}]
            _rating_filter = {"g", "s", "q", "e"}
            _search_dataset_identity = _TEST_IDENTITY
            _search_snapshot_id = _TEST_SNAPSHOT
            is_automating = True

            def __init__(self) -> None:
                self.stop_messages = []

            @staticmethod
            def _handle_creator_action(_action, _payload):
                return False

            @staticmethod
            def _handle_chat_action(_action, _payload):
                return False

            @staticmethod
            def _persist_search_results(_active, full=None):
                return None

            @staticmethod
            def _save_deck_state():
                return None

            def _stop_automation(self, message=None):
                self.is_automating = False
                self.stop_messages.append(message)

        subject = Subject()

        GeneratorMainUI._handle_vue_action(
            subject,
            "update_prompt_deck",
            {"results": [], "lineage": _TEST_LINEAGE},
        )

        self.assertFalse(subject.is_automating)
        self.assertEqual(
            subject.stop_messages,
            ["검색 필터 결과가 없어 자동화를 중지했습니다."],
        )

    def test_delayed_filter_from_another_snapshot_is_rejected(self) -> None:
        current_identity = {"label": "2026_07", "fingerprint": "b" * 64}
        stale_lineage = {
            "label": "2026_07",
            "fingerprint": "a" * 64,
            "snapshot_id": "a" * 32,
        }

        class Subject:
            filtered_results = [{"general": "current_b"}]
            shuffled_prompt_deck = [{"general": "current_b"}]
            _rating_filter = {"g", "s", "q", "e"}
            _search_dataset_identity = current_identity
            _search_snapshot_id = "b" * 32

            def __init__(self) -> None:
                self.persisted = []
                self.statuses = []

            @staticmethod
            def _handle_creator_action(_action, _payload):
                return False

            @staticmethod
            def _handle_chat_action(_action, _payload):
                return False

            def _persist_search_results(self, active, full=None):
                self.persisted.append((active, full))

            @staticmethod
            def _save_deck_state():
                return None

            def show_status(self, message):
                self.statuses.append(message)

        subject = Subject()

        GeneratorMainUI._handle_vue_action(
            subject,
            "update_prompt_deck",
            {
                "results": [{"general": "stale_a"}],
                "lineage": stale_lineage,
            },
        )

        self.assertEqual(subject.filtered_results, [{"general": "current_b"}])
        self.assertEqual(subject.shuffled_prompt_deck, [{"general": "current_b"}])
        self.assertEqual(subject.persisted, [])
        self.assertTrue(any("일치하지" in item for item in subject.statuses))

    def test_imported_results_start_a_new_cache_and_deck_snapshot(self) -> None:
        identity = {"label": "2026_07", "fingerprint": "f" * 64}

        class Signal:
            def __init__(self) -> None:
                self.values = []

            def emit(self, value) -> None:
                self.values.append(value)

        class Bridge:
            searchResultsReady = Signal()
            searchResultLineage = Signal()

        class Store:
            @staticmethod
            def dataset_info():
                return identity

        class Subject:
            vue_bridge = Bridge()
            _search_snapshot_id = "a" * 32

            def __init__(self) -> None:
                self.persisted = []
                self.deck_saves = 0
                self.statuses = []

            @staticmethod
            def _handle_creator_action(_action, _payload):
                return False

            @staticmethod
            def _handle_chat_action(_action, _payload):
                return False

            def _persist_search_results(self, active, full=None, **kwargs):
                self.persisted.append((active, full, kwargs))

            def _save_deck_state(self):
                self.deck_saves += 1

            def show_status(self, message):
                self.statuses.append(message)

        frame = pd.DataFrame(
            [
                {
                    "general": "imported_tag",
                    "character": "",
                    "copyright": "",
                    "artist": "",
                    "rating": "g",
                }
            ]
        )
        subject = Subject()

        with (
            patch(
                "ui.generator_main.QFileDialog.getOpenFileName",
                return_value=("import.parquet", "Parquet Files (*.parquet)"),
            ),
            patch("pandas.read_parquet", return_value=frame),
            patch("core.search_result_store.SearchResultStore", Store),
        ):
            GeneratorMainUI._handle_vue_action(
                subject,
                "import_search_results",
                {},
            )

        self.assertEqual(len(subject.filtered_results), 1)
        self.assertNotEqual(subject._search_snapshot_id, "a" * 32)
        self.assertEqual(subject._search_dataset_identity, identity)
        active, full, kwargs = subject.persisted[0]
        self.assertEqual(active, full)
        self.assertEqual(kwargs["dataset_identity"], identity)
        self.assertEqual(kwargs["snapshot_id"], subject._search_snapshot_id)
        self.assertEqual(subject.deck_saves, 1)
        self.assertEqual(
            json.loads(subject.vue_bridge.searchResultLineage.values[0]),
            {
                **identity,
                "snapshot_id": subject._search_snapshot_id,
            },
        )


if __name__ == "__main__":
    unittest.main()
