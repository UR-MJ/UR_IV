import threading
import unittest

from core.resource_coordinator import (
    GenerationResourceCoordinator,
    ResourceBusyError,
    ResourceTransitionError,
    get_generation_coordinator,
)


class ResourceCoordinatorTests(unittest.TestCase):
    def test_unloads_before_running_and_returns_to_idle(self):
        calls = []
        coordinator = GenerationResourceCoordinator(
            unload_llm=lambda: calls.append("unload") or True,
            on_state=lambda state: calls.append(state.phase),
        )
        with coordinator.reserve("h3") as state:
            self.assertEqual(state.phase, "running")
            self.assertTrue(state.llm_unloaded)
        self.assertEqual(coordinator.state.phase, "idle")
        self.assertEqual(calls[:3], ["preparing", "unload", "running"])

    def test_does_not_invoke_unsupplied_external_process_hooks(self):
        coordinator = GenerationResourceCoordinator()
        with coordinator.reserve("krea", unload_llm=False):
            self.assertEqual(coordinator.state.owner, "krea")

    def test_rejects_concurrent_generation(self):
        coordinator = GenerationResourceCoordinator()
        entered = threading.Event()
        release = threading.Event()

        def hold():
            with coordinator.reserve("first", unload_llm=False):
                entered.set()
                release.wait(2)

        thread = threading.Thread(target=hold)
        thread.start()
        self.assertTrue(entered.wait(1))
        with self.assertRaises(ResourceBusyError):
            with coordinator.reserve("second", unload_llm=False):
                pass
        release.set()
        thread.join(2)

    def test_failed_unload_releases_lease(self):
        coordinator = GenerationResourceCoordinator(unload_llm=lambda: False)
        with self.assertRaises(ResourceTransitionError):
            with coordinator.reserve("first"):
                pass
        with coordinator.reserve("second", unload_llm=False):
            self.assertEqual(coordinator.state.owner, "second")

    def test_process_wide_accessor_keeps_one_shared_lease(self):
        first = get_generation_coordinator()
        second = get_generation_coordinator()
        self.assertIs(first, second)

    def test_hooks_can_be_configured_after_coordinator_creation(self):
        calls = []
        coordinator = GenerationResourceCoordinator()
        coordinator.configure(
            unload_llm=lambda: calls.append("unload") or True,
            on_state=lambda state: calls.append(state.phase),
        )
        with coordinator.reserve("creator"):
            pass
        self.assertIn("unload", calls)
        self.assertEqual(calls[-1], "idle")


if __name__ == "__main__":
    unittest.main()
