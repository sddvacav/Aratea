import sys
import unittest
from pathlib import Path

ARTIFACT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ARTIFACT_ROOT))

from modules.r11_dual_caliber.g11_dual_caliber_contract import (
    CALIBER_GE5,
    CALIBER_HQ_LOSO,
    CaliberRecord,
    DualCaliberLedger,
    evaluate_grouped,
    metric_bundle,
    promotion_decision,
)


class DualCaliberTests(unittest.TestCase):
    def record(self, caliber, r2=0.90, status="PASS", n_groups=6, coverage=0.80):
        return CaliberRecord(
            target="UTS",
            caliber=caliber,
            split_manifest_sha256="a" * 64,
            dataset_sha256="b" * 64,
            feature_schema_sha256="c" * 64,
            metrics={"r2": r2, "mae": 10.0, "rmse": 15.0, "n_samples": 100},
            n_groups=n_groups,
            coverage=coverage,
            seeds=(7, 17, 27),
            status=status,
        )

    def test_exact_metrics(self):
        metrics = metric_bundle([1, 2, 3], [1, 2, 3])
        self.assertEqual(metrics["r2"], 1.0)
        self.assertEqual(metrics["mae"], 0.0)
        self.assertEqual(metrics["rmse"], 0.0)

    def test_constant_target_does_not_fake_r2(self):
        self.assertIsNone(metric_bundle([2, 2, 2], [2, 2, 2])["r2"])

    def test_nonfinite_values_rejected(self):
        with self.assertRaises(ValueError):
            metric_bundle([1, float("nan")], [1, 2])

    def test_grouped_recomputes_pooled(self):
        result = evaluate_grouped([1, 2, 3, 4], [1, 2, 3, 4], ["a", "a", "b", "b"])
        self.assertEqual(result["pooled"]["r2"], 1.0)
        self.assertEqual(result["n_groups"], 2)

    def test_ge5_only_can_never_fullscore(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_GE5))
        decision = promotion_decision(ledger, "UTS")
        self.assertFalse(decision["fullscore_eligible"])
        self.assertEqual(decision["decision"], "below_gate_continue_optimization")
        self.assertIn("missing_hq_loso_receipt", decision["reasons"])

    def test_loso_pass_without_external_receipt_is_not_fullscore(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_HQ_LOSO))
        decision = promotion_decision(ledger, "UTS")
        self.assertEqual(decision["decision"], "CHALLENGER_HQ_LOSO_PASS_NOT_FULLSCORE")
        self.assertFalse(decision["fullscore_eligible"])

    def test_invalid_external_receipt_rejected(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_HQ_LOSO))
        decision = promotion_decision(ledger, "UTS", external_fullscore_receipt={"status": "PASS"})
        self.assertFalse(decision["fullscore_eligible"])
        self.assertIn("external_fullscore_receipt_invalid", decision["reasons"])

    def test_valid_external_noncompensatory_receipt(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_HQ_LOSO))
        receipt = {
            "status": "PASS",
            "hq_loso_all_targets_pass": True,
            "non_compensatory_gates_green": True,
            "claim": "FULLSCORE",
        }
        decision = promotion_decision(ledger, "UTS", external_fullscore_receipt=receipt)
        self.assertTrue(decision["fullscore_eligible"])
        self.assertEqual(decision["decision"], "FULLSCORE_ELIGIBLE_BY_EXTERNAL_NONCOMPENSATORY_RECEIPT")

    def test_duplicate_caliber_record_rejected(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_GE5))
        with self.assertRaises(ValueError):
            ledger.add(self.record(CALIBER_GE5))

    def test_loso_below_coverage_gate_stays_below_gate(self):
        ledger = DualCaliberLedger()
        ledger.add(self.record(CALIBER_HQ_LOSO, coverage=0.20))
        decision = promotion_decision(ledger, "UTS")
        self.assertEqual(decision["decision"], "below_gate_continue_optimization")
        self.assertIn("loso_coverage_below_gate", decision["reasons"])


if __name__ == "__main__":
    unittest.main()
