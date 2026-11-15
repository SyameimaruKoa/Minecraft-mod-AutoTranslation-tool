import collections
import threading
import time
import unittest

from dynamic_plamo_pool import translate_dynamic_model_pool_batches


def run_pool(items, translator, discover, models, **options):
    return translate_dynamic_model_pool_batches(
        items, workers=1, batch_size=1, translator=translator,
        models=models, discover_models=discover, label="PLaMo",
        refresh_seconds=0.01, hedge_after_seconds=0.02, **options
    )


class DynamicPoolTests(unittest.TestCase):
    def test_fast_pc_pulls_more_batches_without_waiting_for_slow_pc(self):
        counts = collections.Counter()
        lock = threading.Lock()

        def translate(batch, model, active):
            time.sleep(0.025 if model == "slow" else 0.001)
            with lock:
                counts[model] += len(batch)
            return batch

        items = {f"key-{i}": f"value-{i}" for i in range(45)}
        self.assertEqual(
            run_pool(items, translate, lambda: ["slow", "fast"], ["slow", "fast"],
                     hedge_after_seconds=0.05),
            items
        )
        self.assertGreater(counts["fast"], counts["slow"])
        self.assertGreater(counts["fast"], 25)

    def test_pc_joins_without_restarting_the_translation(self):
        selected = ["initial"]
        lock = threading.Lock()
        first_started = threading.Event()
        seen = set()

        def discover():
            with lock:
                return list(selected)

        def join():
            self.assertTrue(first_started.wait(2))
            with lock:
                selected.append("new")

        helper = threading.Thread(target=join)
        helper.start()

        def translate(batch, model, active):
            first_started.set()
            time.sleep(0.025 if model == "initial" else 0.002)
            with lock:
                seen.add(model)
            return batch

        items = {f"item-{i}": str(i) for i in range(16)}
        try:
            self.assertEqual(run_pool(items, translate, discover, ["initial"]), items)
            self.assertEqual(seen, {"initial", "new"})
        finally:
            helper.join(2)

    def test_removed_pc_is_reassigned_without_waiting_for_its_request(self):
        selected = ["vanishing", "survivor"]
        lock = threading.Lock()
        blocked = threading.Event()
        entered = threading.Event()
        returned = threading.Event()
        accepted = []

        def discover():
            with lock:
                return list(selected)

        def detach():
            self.assertTrue(entered.wait(2))
            with lock:
                selected.remove("vanishing")

        helper = threading.Thread(target=detach)
        helper.start()

        def translate(batch, model, active):
            if model == "vanishing":
                entered.set()
                blocked.wait(3)
                if active():
                    accepted.append("vanishing-late")
                returned.set()
            return batch

        items = {f"item-{i}": str(i) for i in range(5)}
        try:
            started = time.monotonic()
            self.assertEqual(
                run_pool(items, translate, discover, ["vanishing", "survivor"]),
                items
            )
            self.assertLess(time.monotonic() - started, 2)
        finally:
            blocked.set()
            self.assertTrue(returned.wait(2))
            helper.join(2)
        self.assertEqual(accepted, [])

    def test_no_translation_models_left_stops_without_waiting_for_stale_request(self):
        selected = ["single"]
        lock = threading.Lock()
        blocked = threading.Event()
        entered = threading.Event()

        def discover():
            with lock:
                return list(selected)

        def detach():
            self.assertTrue(entered.wait(2))
            with lock:
                selected.clear()

        helper = threading.Thread(target=detach)
        helper.start()

        def translate(batch, model, active):
            entered.set()
            blocked.wait(3)
            return batch

        try:
            with self.assertRaisesRegex(RuntimeError, "0台"):
                run_pool({"a": "text"}, translate, discover, ["single"])
        finally:
            blocked.set()
            helper.join(2)

    def test_tail_hedge_moves_slow_final_batch_to_idle_fast_pc(self):
        blocked = threading.Event()
        slow_started = threading.Event()
        slow_finished = threading.Event()
        late_callbacks = []

        def translate(batch, model, active):
            if model == "slow":
                slow_started.set()
                blocked.wait(3)
                if active():
                    late_callbacks.append("slow")
                slow_finished.set()
            else:
                time.sleep(0.002)
            return batch

        items = {"slow-task": "a", "fast-task": "b"}
        try:
            self.assertEqual(
                run_pool(items, translate, lambda: ["slow", "fast"],
                         ["slow", "fast"]),
                items
            )
            self.assertTrue(slow_started.is_set())
        finally:
            blocked.set()
            self.assertTrue(slow_finished.wait(2))
        self.assertFalse(late_callbacks)

    def test_temporary_discovery_failure_does_not_abort_active_translation(self):
        calls = 0
        def discover():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("temporary CLI timeout")
            return ["working"]
        items = {str(i): str(i) for i in range(5)}
        self.assertEqual(
            run_pool(
                items,
                lambda batch, model, active: (time.sleep(0.007), batch)[1],
                discover, ["working"], hedge_after_seconds=0.1
            ), items
        )
        self.assertGreaterEqual(calls, 2)

    def test_active_model_failure_is_not_mistaken_for_disappearance(self):
        def fail(batch, model, active):
            raise RuntimeError("invalid translation")
        with self.assertRaisesRegex(RuntimeError, "invalid translation"):
            run_pool({"a": "b"}, fail, lambda: ["working"], ["working"])


if __name__ == "__main__":
    unittest.main()
