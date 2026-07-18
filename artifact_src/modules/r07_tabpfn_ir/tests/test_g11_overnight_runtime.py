import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ARTIFACT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ARTIFACT_ROOT))

from modules.r07_tabpfn_ir.g11_overnight_runtime import (
    AtomicRunLock,
    CheckpointIntegrityError,
    CheckpointStore,
    InterlockError,
    OvernightCoordinator,
    ResourcePolicy,
    ResourceSnapshot,
    RobustETA,
    RunIdentity,
    TabPFNPreflight,
    pid_is_alive,
)


class RuntimeContractTests(unittest.TestCase):
    def identity(self, dataset="0" * 64):
        return RunIdentity(
            dataset_sha256=dataset,
            split_manifest_sha256="1" * 64,
            feature_schema_sha256="2" * 64,
            code_ref="3008e56",
            target="UTS",
            route="near_alpha",
            caliber="GE5_TRAIN_CONDITION_GROUP",
            seeds=(7, 17),
            model_bank=("HGB", "ExtraTrees"),
        )

    def test_identity_is_deterministic(self):
        self.assertEqual(self.identity().digest, self.identity().digest)
        self.assertEqual(len(self.identity().digest), 64)

    def test_identity_changes_with_dataset(self):
        self.assertNotEqual(self.identity("0" * 64).digest, self.identity("9" * 64).digest)

    def test_current_pid_is_alive(self):
        self.assertTrue(pid_is_alive(os.getpid()))

    def test_live_lock_blocks_without_killing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            first = AtomicRunLock(path, "A")
            first.acquire()
            try:
                with self.assertRaises(InterlockError):
                    AtomicRunLock(path, "B").acquire()
                self.assertTrue(pid_is_alive(os.getpid()))
            finally:
                first.release()

    def test_stale_lock_requires_explicit_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            path.write_text(json.dumps({"pid": 999999999, "token": "old"}), encoding="utf-8")
            with self.assertRaises(InterlockError):
                AtomicRunLock(path, "B", allow_stale_reclaim=False).acquire()

    def test_stale_lock_can_be_archived_after_explicit_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            path.write_text(json.dumps({"pid": 999999999, "token": "old"}), encoding="utf-8")
            lock = AtomicRunLock(path, "B", allow_stale_reclaim=True)
            lock.acquire()
            try:
                self.assertTrue(list(Path(directory).glob("run.lock.stale.*")))
            finally:
                lock.release()

    def test_checkpoint_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(Path(directory))
            store.save({"a": 1})
            self.assertEqual(store.load()["a"], 1)
            store.state_path.write_text('{"a":2}\n', encoding="utf-8")
            with self.assertRaises(CheckpointIntegrityError):
                store.load()

    def test_eta_unknown_until_three_observations(self):
        eta = RobustETA()
        eta.observe(1)
        eta.observe(2)
        self.assertIsNone(eta.estimate(10)["eta_seconds"])
        eta.observe(3)
        self.assertEqual(eta.estimate(2)["eta_seconds"], 4)

    def test_tabpfn_unknown_gpu_and_checkpoint_fail_closed(self):
        snapshot = ResourceSnapshot(
            collected_at="synthetic",
            ram_available_bytes=32 * 1024**3,
            ram_total_bytes=64 * 1024**3,
            gpu_known=False,
            gpu_free_bytes=None,
            gpu_total_bytes=None,
            cuda_device=None,
            torch_version=None,
            note="synthetic",
        )
        result = TabPFNPreflight.run(None, ResourcePolicy(), snapshot)
        self.assertEqual(result.status, "BLOCKED_NO_SILENT_DOWNGRADE")
        self.assertIn("gpu_unknown_or_unavailable", result.reasons)
        self.assertIn("bound_checkpoint_missing", result.reasons)

    def test_external_live_pid_interlock(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                pid_file = Path(directory) / "live.pid"
                pid_file.write_text(str(process.pid), encoding="utf-8")
                coordinator = OvernightCoordinator(Path(directory) / "run", self.identity(), pid_file)
                with self.assertRaises(InterlockError):
                    coordinator.assert_external_interlock()
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                process.wait(timeout=10)

    def test_coordinator_resume_skips_completed_units(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            coordinator = OvernightCoordinator(Path(directory), self.identity())
            def callback(unit, unit_dir):
                calls.append(unit)
                return {"status": "PASS"}
            first = coordinator.run_units(["a", "b", "c"], callback)
            self.assertEqual(first["state"], "COMPLETED")
            second = OvernightCoordinator(Path(directory), self.identity()).run_units(["a", "b", "c"], callback)
            self.assertEqual(second["state"], "COMPLETED")
            self.assertEqual(calls, ["a", "b", "c"])

    def test_resume_identity_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            first = OvernightCoordinator(Path(directory), self.identity())
            first.run_units(["a"], lambda unit, unit_dir: {"status": "PASS"})
            second = OvernightCoordinator(Path(directory), self.identity("9" * 64))
            with self.assertRaises(CheckpointIntegrityError):
                second.run_units(["a"], lambda unit, unit_dir: {"status": "PASS"})


if __name__ == "__main__":
    unittest.main()
