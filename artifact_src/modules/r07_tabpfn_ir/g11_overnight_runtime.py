from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import socket
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

SCHEMA_VERSION = "g11.1"


class InterlockError(RuntimeError):
    pass


class CheckpointIntegrityError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    atomic_write_bytes(Path(path), canonical_json(dict(data)) + b"\n")


@dataclasses.dataclass(frozen=True)
class RunIdentity:
    dataset_sha256: str
    split_manifest_sha256: str
    feature_schema_sha256: str
    code_ref: str
    target: str
    route: str
    caliber: str
    seeds: tuple[int, ...]
    model_bank: tuple[str, ...]
    protocol_version: str = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.as_dict()))


def pid_is_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, 0, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def read_pid_file(path: Path) -> Optional[int]:
    path = Path(path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, int):
            return obj
        if isinstance(obj, dict) and isinstance(obj.get("pid"), int):
            return int(obj["pid"])
    except json.JSONDecodeError:
        pass
    try:
        return int(text)
    except ValueError:
        return None


class AtomicRunLock:
    def __init__(self, path: Path, run_id: str, allow_stale_reclaim: bool = False):
        self.path = Path(path)
        self.run_id = run_id
        self.allow_stale_reclaim = allow_stale_reclaim
        self.token = hashlib.sha256(f"{os.getpid()}:{time.time_ns()}:{run_id}".encode()).hexdigest()
        self.owned = False

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"pid": None, "parse_error": True}

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": SCHEMA_VERSION,
            "token": self.token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "run_id": self.run_id,
            "acquired_at": utc_now(),
        }
        while True:
            try:
                fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(record, fh, sort_keys=True)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                self.owned = True
                return
            except FileExistsError:
                existing = self._read()
                pid = existing.get("pid")
                if isinstance(pid, int) and pid_is_alive(pid):
                    raise InterlockError(f"BLOCKED_LIVE_RUN_NO_DUPLICATE: pid={pid}")
                if not self.allow_stale_reclaim:
                    raise InterlockError("BLOCKED_STALE_LOCK_REVIEW_REQUIRED")
                stale = self.path.with_name(f"{self.path.name}.stale.{int(time.time())}")
                try:
                    os.replace(self.path, stale)
                except FileNotFoundError:
                    continue

    def release(self) -> None:
        if self.owned and self.path.exists() and self._read().get("token") == self.token:
            self.path.unlink(missing_ok=True)
        self.owned = False

    def __enter__(self) -> "AtomicRunLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class CheckpointStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / "coordinator_state.json"
        self.digest_path = self.directory / "coordinator_state.sha256"

    def save(self, state: Mapping[str, Any]) -> str:
        payload = canonical_json(dict(state)) + b"\n"
        digest = sha256_bytes(payload)
        atomic_write_bytes(self.state_path, payload)
        atomic_write_bytes(self.digest_path, (digest + "\n").encode("ascii"))
        return digest

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists() or not self.digest_path.exists():
            raise FileNotFoundError("checkpoint or digest missing")
        payload = self.state_path.read_bytes()
        expected = self.digest_path.read_text(encoding="ascii").strip()
        actual = sha256_bytes(payload)
        if expected != actual:
            raise CheckpointIntegrityError(f"checkpoint_sha256_mismatch:{expected}:{actual}")
        return json.loads(payload)

    def exists(self) -> bool:
        return self.state_path.exists() and self.digest_path.exists()


@dataclasses.dataclass(frozen=True)
class ResourceSnapshot:
    collected_at: str
    ram_available_bytes: Optional[int]
    ram_total_bytes: Optional[int]
    gpu_known: bool
    gpu_free_bytes: Optional[int]
    gpu_total_bytes: Optional[int]
    cuda_device: Optional[str]
    torch_version: Optional[str]
    note: str

    @staticmethod
    def collect() -> "ResourceSnapshot":
        available = total = None
        notes: list[str] = []
        try:
            if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
                page = int(os.sysconf("SC_PAGE_SIZE"))
                total = page * int(os.sysconf("SC_PHYS_PAGES"))
                available = page * int(os.sysconf("SC_AVPHYS_PAGES"))
        except Exception as exc:
            notes.append(f"ram_probe_failed:{type(exc).__name__}")
        gpu_known = False
        gpu_free = gpu_total = None
        device = torch_version = None
        try:
            import torch
            torch_version = getattr(torch, "__version__", None)
            if torch.cuda.is_available():
                gpu_free, gpu_total = map(int, torch.cuda.mem_get_info())
                device = torch.cuda.get_device_name(torch.cuda.current_device())
                gpu_known = True
            else:
                notes.append("cuda_unavailable")
        except Exception as exc:
            notes.append(f"torch_gpu_probe_unavailable:{type(exc).__name__}")
        return ResourceSnapshot(utc_now(), available, total, gpu_known, gpu_free, gpu_total, device, torch_version, ";".join(notes) or "ok")


@dataclasses.dataclass(frozen=True)
class ResourcePolicy:
    min_ram_free_bytes: int = 8 * 1024**3
    min_gpu_free_bytes_tabpfn: int = 10 * 1024**3
    require_known_gpu_for_tabpfn: bool = True
    max_parallel_heavy_jobs: int = 1

    def evaluate(self, snapshot: ResourceSnapshot, lane: str) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if snapshot.ram_available_bytes is None:
            reasons.append("ram_unknown")
        elif snapshot.ram_available_bytes < self.min_ram_free_bytes:
            reasons.append("insufficient_ram_free")
        if lane == "tabpfn":
            if self.require_known_gpu_for_tabpfn and not snapshot.gpu_known:
                reasons.append("gpu_unknown_or_unavailable")
            elif snapshot.gpu_free_bytes is not None and snapshot.gpu_free_bytes < self.min_gpu_free_bytes_tabpfn:
                reasons.append("insufficient_gpu_free")
        return not reasons, reasons


@dataclasses.dataclass(frozen=True)
class TabPFNPreflight:
    package_available: bool
    checkpoint_exists: bool
    checkpoint_sha256: Optional[str]
    resource_ok: bool
    reasons: tuple[str, ...]
    status: str

    @staticmethod
    def run(checkpoint: Optional[Path], policy: ResourcePolicy, snapshot: Optional[ResourceSnapshot] = None) -> "TabPFNPreflight":
        snapshot = snapshot or ResourceSnapshot.collect()
        package_available = importlib.util.find_spec("tabpfn") is not None
        checkpoint_exists = bool(checkpoint and Path(checkpoint).is_file())
        digest = None
        if checkpoint_exists and checkpoint is not None:
            h = hashlib.sha256()
            with Path(checkpoint).open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            digest = h.hexdigest()
        resource_ok, reasons = policy.evaluate(snapshot, "tabpfn")
        if not package_available:
            reasons.append("tabpfn_package_missing")
        if not checkpoint_exists:
            reasons.append("bound_checkpoint_missing")
        ok = package_available and checkpoint_exists and resource_ok
        return TabPFNPreflight(package_available, checkpoint_exists, digest, resource_ok, tuple(reasons), "ELIGIBLE_COMPARATOR_LANE" if ok else "BLOCKED_NO_SILENT_DOWNGRADE")


class RobustETA:
    def __init__(self, window: int = 7, min_observations: int = 3):
        self.window = max(3, int(window))
        self.min_observations = max(3, int(min_observations))
        self.durations: list[float] = []

    def observe(self, seconds: float) -> None:
        if math.isfinite(seconds) and seconds >= 0:
            self.durations.append(float(seconds))

    def estimate(self, remaining_units: int) -> dict[str, Any]:
        if remaining_units <= 0:
            return {"eta_seconds": 0.0, "confidence": "complete", "n_observations": len(self.durations)}
        if len(self.durations) < self.min_observations:
            return {"eta_seconds": None, "confidence": "insufficient_history", "n_observations": len(self.durations)}
        sample = self.durations[-self.window:]
        median = statistics.median(sample)
        relative_iqr = None
        if len(sample) >= 4 and median > 0:
            q1, _, q3 = statistics.quantiles(sample, n=4, method="inclusive")
            relative_iqr = (q3 - q1) / median
        return {
            "eta_seconds": median * remaining_units,
            "seconds_per_unit_median": median,
            "relative_iqr": relative_iqr,
            "confidence": "medium" if relative_iqr is None or relative_iqr <= 0.5 else "low",
            "n_observations": len(self.durations),
        }


class HeartbeatWriter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.sequence = 0

    def emit(self, **fields: Any) -> dict[str, Any]:
        self.sequence += 1
        payload = {
            "schema_version": SCHEMA_VERSION,
            "sequence": self.sequence,
            "timestamp_utc": utc_now(),
            "pid": os.getpid(),
            "host": socket.gethostname(),
            **fields,
        }
        atomic_write_json(self.path, payload)
        return payload


class OvernightCoordinator:
    def __init__(self, workdir: Path, identity: RunIdentity, live_pid_file: Optional[Path] = None, allow_stale_reclaim: bool = False):
        self.workdir = Path(workdir)
        self.identity = identity
        self.run_id = identity.digest[:20]
        self.live_pid_file = Path(live_pid_file) if live_pid_file else None
        self.lock = AtomicRunLock(self.workdir / "run.lock", self.run_id, allow_stale_reclaim)
        self.store = CheckpointStore(self.workdir / "checkpoints")
        self.heartbeat = HeartbeatWriter(self.workdir / "heartbeat.json")
        self.eta = RobustETA()
        self.started = time.monotonic()

    def assert_external_interlock(self) -> None:
        if self.live_pid_file:
            pid = read_pid_file(self.live_pid_file)
            if pid is not None and pid != os.getpid() and pid_is_alive(pid):
                raise InterlockError(f"BLOCKED_LIVE_LOSO_PID_NO_DUPLICATE: pid={pid}")

    def _initial_state(self, units: Sequence[str]) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "identity": self.identity.as_dict(),
            "identity_sha256": self.identity.digest,
            "completed_units": [],
            "unit_receipts": {},
            "planned_units": list(units),
            "state": "READY",
            "updated_at": utc_now(),
        }

    def run_units(self, units: Sequence[str], callback: Callable[[str, Path], Mapping[str, Any]], resume: bool = True) -> dict[str, Any]:
        self.assert_external_interlock()
        with self.lock:
            state = self.store.load() if resume and self.store.exists() else self._initial_state(units)
            if state.get("identity_sha256") != self.identity.digest:
                raise CheckpointIntegrityError("resume_identity_mismatch")
            completed = set(state.get("completed_units", []))
            total = len(units)
            state["state"] = "RUNNING"
            self.store.save(state)
            self.heartbeat.emit(run_id=self.run_id, identity_sha256=self.identity.digest, state="RUNNING", target=self.identity.target, caliber=self.identity.caliber, completed=len(completed), total=total, progress=(len(completed) / total if total else 1.0), eta=self.eta.estimate(total - len(completed)), resource_snapshot=dataclasses.asdict(ResourceSnapshot.collect()))
            try:
                for unit in units:
                    if unit in completed:
                        continue
                    unit_dir = self.workdir / "units" / unit
                    unit_dir.mkdir(parents=True, exist_ok=True)
                    t0 = time.monotonic()
                    receipt = dict(callback(unit, unit_dir))
                    duration = time.monotonic() - t0
                    self.eta.observe(duration)
                    completed.add(unit)
                    state["completed_units"] = [u for u in units if u in completed]
                    state["unit_receipts"][unit] = {**receipt, "duration_seconds": duration, "completed_at": utc_now()}
                    state["updated_at"] = utc_now()
                    checkpoint_sha = self.store.save(state)
                    remaining = total - len(completed)
                    self.heartbeat.emit(run_id=self.run_id, identity_sha256=self.identity.digest, state="RUNNING", target=self.identity.target, caliber=self.identity.caliber, current_unit=unit, completed=len(completed), total=total, progress=(len(completed) / total if total else 1.0), elapsed_seconds=time.monotonic() - self.started, eta=self.eta.estimate(remaining), checkpoint_sha256=checkpoint_sha)
                state["state"] = "COMPLETED"
                state["updated_at"] = utc_now()
                checkpoint_sha = self.store.save(state)
                self.heartbeat.emit(run_id=self.run_id, identity_sha256=self.identity.digest, state="COMPLETED", target=self.identity.target, caliber=self.identity.caliber, completed=total, total=total, progress=1.0, eta=self.eta.estimate(0), checkpoint_sha256=checkpoint_sha)
                return state
            except KeyboardInterrupt:
                state["state"] = "INTERRUPTED_RESUMABLE"
                state["updated_at"] = utc_now()
                self.store.save(state)
                raise
            except Exception as exc:
                state["state"] = "FAILED_RESUMABLE"
                state["failure"] = {"type": type(exc).__name__, "message": str(exc)}
                state["updated_at"] = utc_now()
                self.store.save(state)
                raise


def doctor(workdir: Path, live_pid_file: Optional[Path], checkpoint: Optional[Path]) -> dict[str, Any]:
    snapshot = ResourceSnapshot.collect()
    preflight = TabPFNPreflight.run(checkpoint, ResourcePolicy(), snapshot)
    pid = read_pid_file(live_pid_file) if live_pid_file else None
    alive = pid_is_alive(pid) if pid is not None else False
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": utc_now(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "workdir": str(workdir),
        "disk_free_bytes": shutil.disk_usage(Path(workdir).parent if Path(workdir).parent.exists() else Path.cwd()).free,
        "live_pid_file": str(live_pid_file) if live_pid_file else None,
        "live_pid": pid,
        "live_pid_alive": alive,
        "resource_snapshot": dataclasses.asdict(snapshot),
        "tabpfn_preflight": dataclasses.asdict(preflight),
        "decision": "BLOCKED_LIVE_RUN_NO_DUPLICATE" if alive else "SAFE_FOR_COORDINATOR_PREFLIGHT_ONLY",
    }


def smoke(workdir: Path) -> dict[str, Any]:
    identity = RunIdentity("0" * 64, "1" * 64, "2" * 64, "smoke", "UTS", "synthetic", "GE5_TRAIN_CONDITION_GROUP", (7,), ("HGB", "ExtraTrees"))
    coordinator = OvernightCoordinator(workdir, identity)
    def callback(unit: str, unit_dir: Path) -> Mapping[str, Any]:
        atomic_write_json(unit_dir / "receipt.json", {"unit": unit, "synthetic": True})
        return {"status": "SYNTHETIC_SMOKE_PASS"}
    state = coordinator.run_units(["fold0", "fold1", "fold2"], callback)
    return {"state": state["state"], "run_id": coordinator.run_id}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="G11 fail-closed overnight coordinator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--workdir", type=Path, required=True)
    p_doctor.add_argument("--live-pid-file", type=Path)
    p_doctor.add_argument("--tabpfn-checkpoint", type=Path)
    p_smoke = sub.add_parser("smoke")
    p_smoke.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        print(json.dumps(doctor(args.workdir, args.live_pid_file, args.tabpfn_checkpoint), indent=2))
    else:
        print(json.dumps(smoke(args.workdir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
