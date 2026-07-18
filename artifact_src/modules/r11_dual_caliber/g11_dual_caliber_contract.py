from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Optional, Sequence

CALIBER_GE5 = "GE5_TRAIN_CONDITION_GROUP"
CALIBER_HQ_LOSO = "HQ_LOSO_SOURCE_HOLDOUT"
ALLOWED_CALIBERS = {CALIBER_GE5, CALIBER_HQ_LOSO}


def finite_floats(values: Iterable[float]) -> list[float]:
    out = [float(value) for value in values]
    if not out or any(not math.isfinite(value) for value in out):
        raise ValueError("metrics require non-empty finite arrays")
    return out


def metric_bundle(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, Any]:
    truth, prediction = finite_floats(y_true), finite_floats(y_pred)
    if len(truth) != len(prediction):
        raise ValueError("y_true and y_pred length mismatch")
    n_samples = len(truth)
    errors = [pred - true for true, pred in zip(truth, prediction)]
    mae = sum(abs(error) for error in errors) / n_samples
    rmse = math.sqrt(sum(error * error for error in errors) / n_samples)
    mean_true = sum(truth) / n_samples
    ss_total = sum((value - mean_true) ** 2 for value in truth)
    ss_residual = sum(error * error for error in errors)
    return {
        "n_samples": n_samples,
        "r2": None if ss_total == 0 else 1.0 - ss_residual / ss_total,
        "mae": mae,
        "rmse": rmse,
        "constant_target": ss_total == 0,
    }


def evaluate_grouped(y_true: Sequence[float], y_pred: Sequence[float], groups: Sequence[str]) -> dict[str, Any]:
    if not (len(y_true) == len(y_pred) == len(groups)):
        raise ValueError("grouped arrays length mismatch")
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        if group is None or str(group).strip() == "":
            raise ValueError("source/study group is required")
        buckets[str(group)].append(index)
    per_group: dict[str, dict[str, Any]] = {}
    valid_group_r2: list[float] = []
    for group, indices in sorted(buckets.items()):
        metrics = metric_bundle([y_true[i] for i in indices], [y_pred[i] for i in indices])
        per_group[group] = metrics
        if metrics["r2"] is not None:
            valid_group_r2.append(float(metrics["r2"]))
    return {
        "pooled": metric_bundle(y_true, y_pred),
        "n_groups": len(buckets),
        "macro_group_r2": sum(valid_group_r2) / len(valid_group_r2) if valid_group_r2 else None,
        "per_group": per_group,
        "warning": "pooled OOF metrics are recomputed from every held-out prediction; fold R2 is not averaged into a headline",
    }


def valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


@dataclasses.dataclass(frozen=True)
class CaliberRecord:
    target: str
    caliber: str
    split_manifest_sha256: str
    dataset_sha256: str
    feature_schema_sha256: str
    metrics: Mapping[str, Any]
    n_groups: int
    coverage: float
    seeds: tuple[int, ...]
    status: str
    receipt_path: Optional[str] = None

    def validate(self) -> None:
        if self.caliber not in ALLOWED_CALIBERS:
            raise ValueError(f"unknown caliber: {self.caliber}")
        for name, value in {
            "split_manifest_sha256": self.split_manifest_sha256,
            "dataset_sha256": self.dataset_sha256,
            "feature_schema_sha256": self.feature_schema_sha256,
        }.items():
            if not valid_sha256(value):
                raise ValueError(f"{name} must be a SHA-256 digest")
        if not (0.0 <= self.coverage <= 1.0):
            raise ValueError("coverage outside [0,1]")
        if self.caliber == CALIBER_HQ_LOSO and self.n_groups < 2:
            raise ValueError("HQ-LOSO requires at least two held-out source groups")
        if not self.seeds:
            raise ValueError("at least one seed is required")


class DualCaliberLedger:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], CaliberRecord] = {}

    def add(self, record: CaliberRecord) -> None:
        record.validate()
        key = record.target, record.caliber
        if key in self.records:
            raise ValueError(f"duplicate target/caliber record: {key}")
        self.records[key] = record

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "g11.dual_caliber.1",
            "records": [dataclasses.asdict(record) for _, record in sorted(self.records.items())],
            "headline_policy": {
                "GE5": "training/condition-group evidence only",
                "HQ_LOSO": "source-holdout evidence only",
                "prohibition": "GE5 cannot populate or substitute the HQ-LOSO field",
            },
        }

    def render_markdown(self) -> str:
        rows = [
            "| target | caliber | R2 | MAE | RMSE | n | n_groups | coverage | status |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for _, record in sorted(self.records.items()):
            metrics = record.metrics
            def fmt(value: Any) -> str:
                if value is None:
                    return "NA"
                return f"{value:.6f}" if isinstance(value, float) else str(value)
            rows.append(
                f"| {record.target} | {record.caliber} | {fmt(metrics.get('r2'))} | "
                f"{fmt(metrics.get('mae'))} | {fmt(metrics.get('rmse'))} | "
                f"{fmt(metrics.get('n_samples'))} | {record.n_groups} | {record.coverage:.4f} | {record.status} |"
            )
        return "\n".join(rows) + "\n"


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(receipt), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def promotion_decision(
    ledger: DualCaliberLedger,
    target: str,
    loso_r2_gate: float = 0.85,
    min_loso_groups: int = 5,
    min_coverage: float = 0.60,
    external_fullscore_receipt: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    ge5 = ledger.records.get((target, CALIBER_GE5))
    loso = ledger.records.get((target, CALIBER_HQ_LOSO))
    reasons: list[str] = []
    if loso is None:
        reasons.append("missing_hq_loso_receipt")
    else:
        r2 = loso.metrics.get("r2")
        if r2 is None or float(r2) < loso_r2_gate:
            reasons.append("hq_loso_below_gate")
        if loso.n_groups < min_loso_groups:
            reasons.append("insufficient_loso_groups")
        if loso.coverage < min_coverage:
            reasons.append("loso_coverage_below_gate")
        if "pass" not in loso.status.lower():
            reasons.append("loso_status_not_pass")
    loso_blockers = {
        "missing_hq_loso_receipt",
        "hq_loso_below_gate",
        "insufficient_loso_groups",
        "loso_coverage_below_gate",
        "loso_status_not_pass",
    }
    loso_pass = loso is not None and not any(reason in loso_blockers for reason in reasons)
    external_digest = None
    external_ok = False
    if external_fullscore_receipt is None:
        reasons.append("external_fullscore_receipt_absent")
    else:
        external_digest = receipt_digest(external_fullscore_receipt)
        external_ok = (
            external_fullscore_receipt.get("status") == "PASS"
            and external_fullscore_receipt.get("hq_loso_all_targets_pass") is True
            and external_fullscore_receipt.get("non_compensatory_gates_green") is True
            and external_fullscore_receipt.get("claim") == "FULLSCORE"
        )
        if not external_ok:
            reasons.append("external_fullscore_receipt_invalid")
    if loso_pass and external_ok:
        decision = "FULLSCORE_ELIGIBLE_BY_EXTERNAL_NONCOMPENSATORY_RECEIPT"
    elif loso_pass:
        decision = "CHALLENGER_HQ_LOSO_PASS_NOT_FULLSCORE"
    else:
        decision = "below_gate_continue_optimization"
    return {
        "target": target,
        "decision": decision,
        "ge5_present": ge5 is not None,
        "hq_loso_present": loso is not None,
        "fullscore_eligible": bool(loso_pass and external_ok),
        "reasons": reasons,
        "external_receipt_sha256": external_digest,
        "policy": {
            "loso_r2_gate": loso_r2_gate,
            "min_loso_groups": min_loso_groups,
            "min_coverage": min_coverage,
            "GE5_cannot_substitute_LOSO": True,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="G11 dual-caliber contract")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if not args.smoke:
        parser.error("use --smoke or import this module")
    ledger = DualCaliberLedger()
    ledger.add(CaliberRecord("UTS", CALIBER_GE5, "a" * 64, "b" * 64, "c" * 64, metric_bundle([1, 2, 3], [1, 2, 3]), 5, 1.0, (7,), "PASS_SYNTHETIC_SMOKE"))
    print(json.dumps({"ledger": ledger.to_dict(), "decision": promotion_decision(ledger, "UTS")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
