from __future__ import annotations

import csv
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

NAME = "TIAI_G11_TRAINING_OVERNIGHT_TABPFN_FINAL_20260718"
ROOT = Path("dist") / NAME
SRC = Path("artifact_src")
BASE_SHA = "3008e56"


def write(rel: str, content: str) -> Path:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8", newline="\n")
    return path


def write_json(rel: str, obj: Any) -> Path:
    return write(rel, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


QUERIES = [
    "What is TabPFN v2 paper official Nature 2025",
    "Prior-data fitted networks NeurIPS TabPFN official paper",
    "TabPFN GitHub memory limits samples features",
    "TabPFN post-hoc ensemble regression paper",
    "domain generalization survey out of distribution group holdout",
    "CORAL domain adaptation official paper",
    "scikit-learn GroupKFold LeaveOneGroupOut official",
    "PyTorch checkpoint resume training official",
    "titanium alloy materials informatics machine learning review",
    "Acta Materialia titanium microstructure machine learning",
    "npj Computational Materials titanium alloy design machine learning",
    "materials property leave-one-study-out validation",
    "conformalized quantile regression official paper",
    "adaptive conformal inference distribution shift",
    "conformal prediction materials science uncertainty",
    "scikit-learn prediction intervals calibration regression",
    "site:pytorch.org/docs stable saving loading checkpoint resume training optimizer scheduler RNG state PyTorch",
    "site:pytorch.org/docs stable CUDA memory available free total memory torch.cuda mem_get_info",
    "site:pytorch.org/docs stable reproducibility random seed deterministic algorithms DataLoader worker",
    "site:pytorch.org/docs stable torch distributed elastic checkpoint fault tolerance",
    "site:optuna.readthedocs.io heartbeat failed trial retry RDB storage official documentation",
    "site:mlflow.org/docs latest tracking resume run checkpoint artifacts official",
    "site:docs.wandb.ai resume run id checkpoint training official",
    "site:dvc.org/doc data versioning reproducible machine learning pipelines official",
    "site:scikit-learn.org stable stacking regressor cross validation predictions leakage official",
    "site:xgboost.readthedocs.io stable early stopping save model resume training official",
    "site:lightgbm.readthedocs.io latest early stopping callback save model official",
    "site:catboost.ai docs snapshot resume training GPU memory official",
    "nested cross-validation unbiased model selection Varma Simon 2006 DOI",
    "data leakage machine learning pipelines cross validation official scikit-learn common pitfalls",
    "grouped cross validation source leakage materials property prediction paper",
    "leave-one-group-out cross-validation domain generalization scientific datasets",
    "TabPFN v2 limitations regression benchmark official paper 2025",
    "TabPFN post hoc ensembles PHE paper arXiv official",
    "Real-TabPFN tabular foundation model real data priors paper 2025",
    "TabPFN 2.5 scaling 50000 samples 2000 features official paper",
    "Super Learner oracle optimal stacking van der Laan 2007 DOI",
    "non-negative least squares stacking regression out of fold predictions paper",
    "greedy ensemble selection Caruana 2004 machine learning paper",
    "AutoGluon Tabular weighted ensemble official documentation",
    "materials informatics applicability domain uncertainty quantification alloy property prediction 2024",
    "out of distribution evaluation materials property prediction benchmark 700 tasks 2025",
    "leave one cluster out materials machine learning extrapolation Rosseinsky",
    "source-aware cross validation experimental materials datasets machine learning",
    "titanium alloy machine learning tensile strength elongation review 2025",
    "titanium matrix composites machine learning additive manufacturing review 2025",
    "laser directed energy deposition titanium alloy machine learning process property 2024",
    "high temperature titanium alloy machine learning design 800 C",
    "conformal prediction group conditional coverage Mondrian regression paper",
    "adaptive conformal inference distribution shift time series NeurIPS 2021",
    "risk controlling prediction sets Angelopoulos Bates 2022",
    "applicability domain Mahalanobis distance materials property machine learning",
]

SOURCES = [
    ("TabPFN v2 Nature", "https://www.nature.com/articles/s41586-024-08328-6", "Published TabPFN-v2 evidence defines a comparator starting point, not a substitute for project source-holdout validation.", "METHOD_IR"),
    ("TabPFN original", "https://arxiv.org/abs/2207.01848", "Prior-data fitted inference motivates a controlled comparator lane.", "METHOD_IR"),
    ("TabPFN official repository", "https://github.com/PriorLabs/tabpfn", "Bind the official package and checkpoint hash before admitting the lane.", "IMPLEMENT"),
    ("TabPFN limitations", "https://arxiv.org/abs/2502.17361", "Dataset-shape and benchmark limitations must remain explicit.", "METHOD_IR"),
    ("Real-TabPFN", "https://arxiv.org/abs/2507.03971", "Real-data priors remain a challenger hypothesis under the same split.", "SURVEY_ONLY"),
    ("TabPFN 2.5 report", "https://priorlabs.ai/technical-reports/tabpfn-2-5-model-report", "New scaling claims require matching package and runtime receipts.", "SURVEY_ONLY"),
    ("PyTorch save/load", "https://pytorch.org/tutorials/beginner/saving_loading_models.html", "True resume persists complete state rather than model weights alone.", "IMPLEMENT"),
    ("PyTorch reproducibility", "https://pytorch.org/docs/stable/notes/randomness.html", "Record seeds and deterministic settings without promising cross-platform bit identity.", "IMPLEMENT"),
    ("PyTorch elastic", "https://pytorch.org/docs/stable/elastic/run.html", "Fault tolerance still depends on idempotent units and checkpoints.", "METHOD_IR"),
    ("PyTorch CUDA memory", "https://pytorch.org/docs/stable/generated/torch.cuda.memory.mem_get_info.html", "Probe free and total VRAM before the TabPFN lane.", "IMPLEMENT"),
    ("PyTorch distributed checkpoint", "https://pytorch.org/docs/stable/distributed.checkpoint.html", "Distributed recovery needs explicit state and integrity receipts.", "METHOD_IR"),
    ("Optuna RDB heartbeat", "https://optuna.readthedocs.io/en/stable/reference/generated/optuna.storages.RDBStorage.html", "Heartbeat semantics inform stale-run observation and failure states.", "METHOD_IR"),
    ("MLflow tracking", "https://mlflow.org/docs/latest/ml/tracking/", "Run identity and artifact lineage should be immutable.", "SURVEY_ONLY"),
    ("W&B resume", "https://docs.wandb.ai/guides/runs/resuming/", "Resume binds to a stable run ID.", "SURVEY_ONLY"),
    ("DVC pipelines", "https://dvc.org/doc/user-guide/pipelines", "Data and pipeline hashes are first-class run inputs.", "METHOD_IR"),
    ("GroupKFold", "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html", "Groups cannot overlap across train and test folds.", "METHOD_IR"),
    ("LeaveOneGroupOut", "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.LeaveOneGroupOut.html", "Source holdout is structurally distinct from condition-group GE5.", "METHOD_IR"),
    ("Scikit-learn pitfalls", "https://scikit-learn.org/stable/common_pitfalls.html", "Preprocessing and selection must remain fold-local.", "METHOD_IR"),
    ("StackingRegressor", "https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html", "Meta-learning requires out-of-fold base predictions.", "METHOD_IR"),
    ("Scikit-learn persistence", "https://scikit-learn.org/stable/model_persistence.html", "Serving artifacts require environment and feature contracts.", "METHOD_IR"),
    ("XGBoost model IO", "https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html", "Model persistence has version and format boundaries.", "METHOD_IR"),
    ("XGBoost continuation", "https://xgboost.readthedocs.io/en/stable/python/examples/continuation.html", "Continuation must preserve explicit round accounting.", "METHOD_IR"),
    ("LightGBM early stopping", "https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.early_stopping.html", "Early-stop evidence belongs to the fold receipt.", "METHOD_IR"),
    ("CatBoost parameters", "https://catboost.ai/en/docs/references/training-parameters/", "Snapshot and GPU controls must be recorded.", "METHOD_IR"),
    ("AutoGluon Tabular", "https://auto.gluon.ai/stable/tutorials/tabular/index.html", "Weighted ensembles are comparable only under identical splits and budgets.", "SURVEY_ONLY"),
    ("AutoGluon paper", "https://arxiv.org/abs/2003.06505", "Multi-layer stacking motivates strong bank baselines.", "METHOD_IR"),
    ("Ensemble selection", "https://www.cs.cornell.edu/~caruana/ctp/ct.papers/caruana.icml04.icdm06long.pdf", "Fusion selection uses validation or OOF predictions, never test labels.", "METHOD_IR"),
    ("NNLS", "https://arxiv.org/abs/1205.0953", "Nonnegative fusion is auditable when learned on fold-inner OOF matrices.", "METHOD_IR"),
    ("Stacking theory", "https://arxiv.org/abs/2309.09880", "Stacking risk depends on out-of-sample base predictions.", "METHOD_IR"),
    ("CMA-ES ensemble", "https://arxiv.org/abs/2307.00286", "Optimizer-based fusion remains a challenger rather than an automatic replacement.", "SURVEY_ONLY"),
    ("Deep CORAL", "https://arxiv.org/abs/1607.01719", "Alignment must use training domains only.", "METHOD_IR"),
    ("IRM", "https://arxiv.org/abs/1907.02893", "Invariant objectives can fail under misspecification.", "SURVEY_ONLY"),
    ("DG survey", "https://arxiv.org/abs/2103.03097", "DG gains require source-holdout comparison.", "METHOD_IR"),
    ("On Leakage", "https://arxiv.org/abs/2311.04179", "Leakage is an end-to-end pipeline property.", "METHOD_IR"),
    ("LOCO materials validation", "https://arxiv.org/abs/2206.08841", "Cluster holdout probes extrapolation better than random splits.", "METHOD_IR"),
    ("Fast cluster CV", "https://arxiv.org/abs/2405.20400", "Acceleration cannot change the scientific split definition.", "SURVEY_ONLY"),
    ("Conformalized quantile regression", "https://arxiv.org/abs/1905.03222", "Calibrate heteroskedastic intervals on separated data.", "METHOD_IR"),
    ("Adaptive conformal", "https://arxiv.org/abs/2106.00170", "Adaptive calibration does not create source-holdout accuracy.", "SURVEY_ONLY"),
    ("Conditional conformal", "https://arxiv.org/abs/2309.08313", "Conditional diagnostics accompany aggregate coverage.", "METHOD_IR"),
    ("Selection-conditional conformal", "https://arxiv.org/abs/2403.03868", "Calibration follows the declared selection mechanism.", "SURVEY_ONLY"),
    ("Kandinsky conformal", "https://arxiv.org/abs/2502.17264", "Flexible group coverage is a challenger requiring validation.", "SURVEY_ONLY"),
    ("Conformal guide", "https://arxiv.org/abs/2107.07511", "Coverage claims require assumptions and separated calibration.", "METHOD_IR"),
    ("MAPIE", "https://mapie.readthedocs.io/", "Reference implementation does not replace project receipts.", "SURVEY_ONLY"),
    ("Materials UQ/domain guidance", "https://arxiv.org/abs/2406.15650", "Materials predictions should expose uncertainty and applicability.", "METHOD_IR"),
    ("MatUQ", "https://arxiv.org/abs/2511.11697", "Materials UQ benchmarks reinforce separate OOD evaluation.", "SURVEY_ONLY"),
    ("BOOM materials OOD", "https://arxiv.org/abs/2505.01912", "OOD benchmarks support abstention and support-distance reporting.", "SURVEY_ONLY"),
    ("Known Unknowns materials", "https://arxiv.org/abs/2502.05970", "Comparisons should reveal unsupported regions.", "METHOD_IR"),
    ("AIDED DED", "https://arxiv.org/abs/2407.17338", "DED design loops require grounded feedback and uncertainty.", "METHOD_IR"),
    ("Ti-6Al-4V transfer", "https://arxiv.org/abs/2402.14945", "Transfer gains are domain-dependent.", "SURVEY_ONLY"),
    ("MPEA DED active learning", "https://arxiv.org/abs/2310.04021", "Active learning follows feasibility and uncertainty gates.", "METHOD_IR"),
    ("LPBF hierarchy", "https://arxiv.org/abs/2409.00248", "Hierarchical optimization maps to route-first challengers.", "SURVEY_ONLY"),
    ("qNEHVI", "https://arxiv.org/abs/2105.08195", "Acquisition is downstream of a trusted surrogate.", "SURVEY_ONLY"),
    ("BoTorch", "https://botorch.org/docs/", "Official reference for constrained multi-objective BO.", "SURVEY_ONLY"),
    ("GPyTorch", "https://docs.gpytorch.ai/", "Reference for scalable GP uncertainty challengers.", "SURVEY_ONLY"),
    ("psutil", "https://psutil.readthedocs.io/", "Optional process probing complements the stdlib fallback.", "IMPLEMENT"),
    ("SQLite atomic commit", "https://www.sqlite.org/atomiccommit.html", "Crash consistency motivates atomic state replacement.", "METHOD_IR"),
    ("Python os.replace", "https://docs.python.org/3/library/os.html#os.replace", "Atomic replacement anchors heartbeat and checkpoint updates.", "IMPLEMENT"),
    ("Python tempfile", "https://docs.python.org/3/library/tempfile.html", "Same-directory temporary files limit partial-state exposure.", "IMPLEMENT"),
    ("Python hashlib", "https://docs.python.org/3/library/hashlib.html", "SHA-256 binds checkpoints, identities and manifests.", "IMPLEMENT"),
    ("Python unittest", "https://docs.python.org/3/library/unittest.html", "Stdlib tests keep local apply dependency-light.", "IMPLEMENT"),
]


def copy_sources() -> None:
    shutil.copytree(SRC / "modules", ROOT / "modules")
    for rel in [
        "modules/__init__.py",
        "modules/r07_tabpfn_ir/__init__.py",
        "modules/r07_tabpfn_ir/tests/__init__.py",
        "modules/r11_dual_caliber/__init__.py",
        "modules/r11_dual_caliber/tests/__init__.py",
    ]:
        write(rel, "")


def create_data() -> None:
    write("DATA/g11/overnight_train_contract.yaml", """
    schema_version: g11.1
    mission: overnight_training_tabpfn_accuracy_attack
    base_subject_sha: 3008e56
    apply_scope:
      - modules/r07_tabpfn_ir/**
      - modules/r11_dual_caliber/**
      - DATA/g11/**
    principles:
      never_kill_existing_process: true
      no_duplicate_heavy_run: true
      no_silent_model_bank_downgrade: true
      resume_requires_identity_match: true
      checkpoint_requires_sha256: true
      ge5_cannot_substitute_hq_loso: true
      no_hq_loso_no_fullscore: true
    run_identity_fields: [dataset_sha256, split_manifest_sha256, feature_schema_sha256, code_ref, target, route, caliber, seeds, model_bank]
    state_machine:
      states: [PLANNED, PREFLIGHT, BLOCKED_LIVE_RUN_NO_DUPLICATE, RUNNING, INTERRUPTED_RESUMABLE, FAILED_RESUMABLE, COMPLETED, BELOW_GATE_CONTINUE]
    interlocks:
      lock_mode: atomic_create_exclusive
      stale_lock_policy: explicit_review_then_reclaim
      max_parallel_heavy_jobs: 1
    checkpoint:
      format: json_plus_sha256
      atomic_write: tempfile_fsync_replace
      frequency: after_each_fold_seed_member_unit
    heartbeat:
      required_fields: [run_id, identity_sha256, pid, host, state, target, caliber, completed, total, progress, elapsed_seconds, eta, checkpoint_sha256, timestamp_utc]
    eta:
      estimator: rolling_median_unit_duration
      minimum_observations: 3
      window: 7
    tabpfn:
      role: comparator_challenger
      project_audit_defaults: {top_features: 80, train_cap: 8000}
      admission_requires: [package, checkpoint_sha256, known_gpu_state, resource_pass, same_split]
      missing_dependency_decision: BLOCKED_NO_SILENT_DOWNGRADE
    """)
    write("DATA/g11/dual_caliber_report_template.md", """
    # G11 Dual-Caliber Report Template

    ## Immutable identities
    dataset_sha256 / feature_schema_sha256 / code_ref / model_bank_receipt_sha256

    ## GE5 — condition-group training evidence
    | target | split SHA | n | groups | seeds | R2 | MAE | RMSE | coverage | status |
    |---|---|---:|---:|---|---:|---:|---:|---:|---|

    ## HQ-LOSO — source-holdout evidence
    | target | split SHA | n | sources | seeds | pooled OOF R2 | macro-source R2 | MAE | RMSE | coverage | status |
    |---|---|---:|---:|---|---:|---:|---:|---:|---:|---|

    Pooled metrics are recomputed from row-level held-out predictions. Fold R2 is never averaged into a headline. GE5 never fills the LOSO column. Missing HQ-LOSO remains `below_gate_continue_optimization`.
    """)
    ladder = {
        "schema_version": "g11.lever_ladder.1",
        "ordering": [
            {"rank": 1, "name": "data_identity_and_HQ_admission", "actions": ["target/unit freeze", "paper-condition cell dedup", "study IDs", "protocol audit", "Ti/TMC firewall"]},
            {"rank": 2, "name": "source_shift_diagnostics", "actions": ["study residual bias", "support distance", "family-route matrix", "protocol missingness", "GE5-minus-LOSO gap"]},
            {"rank": 3, "name": "route_first_DG", "actions": ["near-alpha", "TMC", "alpha+beta", "room-temperature modulus"]},
            {"rank": 4, "name": "fold_safe_features", "actions": ["physics descriptors", "protocol metadata", "fold-local selection"]},
            {"rank": 5, "name": "bank_and_OOF_NNLS", "actions": ["HGB/ET vote", "LightGBM", "XGBoost", "CatBoost", "fold-inner OOF NNLS"]},
            {"rank": 6, "name": "TabPFN_comparator", "actions": ["package/checkpoint bind", "top-80 fold-local", "train-cap receipt", "GPU preflight"]},
            {"rank": 7, "name": "UQ_AD_OOD_nearest", "actions": ["conformal", "support AD", "OOD labels", "nearest analog", "coverage-risk curve"]},
        ],
        "stop_conditions": ["live PID", "identity mismatch", "checkpoint mismatch", "test-label leakage", "missing HQ-LOSO", "unknown TabPFN resources"],
    }
    write_json("DATA/g11/lever_ladder.json", ladder)
    write_json("DATA/g11/model_bank_contract.json", {
        "schema_version": "g11.model_bank.1",
        "registry_binding_status": "BLOCKED_EXACT",
        "audited_paths": {"t18_gate09_campaign.py": "equal_mean", "t18b_gate09_round2.py": "inner_OOF_NNLS", "t60_common_strongbase.py": "inner_OOF_NNLS"},
        "members": [
            {"id": "HGB_ET_vote", "status": "audited_implemented"},
            {"id": "LightGBM", "status": "audited_implemented"},
            {"id": "XGBoost", "status": "audited_implemented"},
            {"id": "CatBoost", "status": "audited_implemented"},
            {"id": "TabPFN-v2", "status": "blocked_runtime_unbound", "top_features": 80, "train_cap": 8000},
        ],
        "prohibition": "No serving promotion until immutable entrypoint, artifact, feature schema and route hashes agree."
    })
    write_json("DATA/g11/heartbeat.schema.json", {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
        "required": ["schema_version", "sequence", "timestamp_utc", "pid", "host", "run_id", "state", "completed", "total"],
        "properties": {"sequence": {"type": "integer", "minimum": 1}, "progress": {"type": "number", "minimum": 0, "maximum": 1}, "eta": {"type": "object"}}
    })
    write_json("DATA/g11/checkpoint.schema.json", {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
        "required": ["schema_version", "run_id", "identity", "identity_sha256", "completed_units", "unit_receipts", "planned_units", "state", "updated_at"]
    })
    write_json("DATA/g11/run_receipt.schema.json", {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
        "required": ["target", "caliber", "dataset_sha256", "split_manifest_sha256", "feature_schema_sha256", "seeds", "metrics", "coverage", "status"],
        "properties": {"target": {"enum": ["UTS", "YS", "EL", "Modulus", "KIC"]}, "caliber": {"enum": ["GE5_TRAIN_CONDITION_GROUP", "HQ_LOSO_SOURCE_HOLDOUT"]}}
    })
    write_json("DATA/g11/synthetic_smoke_fixture.json", {"synthetic_only": True, "not_scientific_evidence": True, "units": ["fold0_seed7", "fold1_seed7", "fold2_seed7"]})
    write_json("DATA/g11/research_query_log.json", {"n_queries": len(QUERIES), "language": "English", "queries": [{"id": f"Q{i:02d}", "query": query} for i, query in enumerate(QUERIES, 1)]})
    write("DATA/g11/continuation_brief_template.md", """
    # CC -> ChatGPT-5.6 Overnight Continuation Brief

    Record immutable run identity; live PID/lock/current unit/heartbeat age/checkpoint SHA/ETA/RAM/VRAM; then report GE5 and HQ-LOSO in separate sections. If the PID is alive, never kill or duplicate. If a stale lock exists, inspect receipts before explicit reclaim. If TabPFN preflight is blocked, preserve the declared bank and mark the comparator blocked. Return receipts only; do not rewrite frozen Track-S history.
    """)
    uploads = [
        ["06_彻夜双模型_GPT56_Grok_上传用.zip", "this-window dual-model grounding"],
        ["TIAI_WEB36_V24_G6_WEB99_DIRECT_DELIVER_PROMPTS_ONLY_20260717.zip", "G6 prompt bundle"],
        ["TIAI_WEB36_V24_AGENT_NATIVE_ONE_WAVE_FULL_20260717.zip", "sole authority project source"],
        ["TITMC_V7_AGENT_OS_LIT_B002_OF_010.zip", "fleet B002"],
        ["TITMC_V7_AGENT_OS_LIT_B003_OF_010.zip", "fleet B003"],
        ["TITMC_V7_AGENT_OS_LIT_B004_OF_010.zip", "fleet B004"],
        ["TITMC_V7_AGENT_OS_LIT_B005_OF_010.zip", "fleet B005"],
    ]
    write_json("DATA/g11/upload_inventory.json", {"mount_confirmed": True, "archive_byte_hashes": "not exposed to public CI runner", "files": [{"name": name, "role": role} for name, role in uploads]})
    with (ROOT / "DATA/g11/fleet_touchpoints.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["fleet_member", "direct_current_window", "decision"])
        for index in range(1, 11):
            direct = 2 <= index <= 5
            writer.writerow([f"B{index:03d}", str(direct).lower(), "TOUCHED_DIRECT" if direct else "NOT_DIRECTLY_MOUNTED_CURRENT_WINDOW"])
    with (ROOT / "DATA/g11/source_ledger.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_id", "title", "url", "takeaway", "disposition"])
        for index, row in enumerate(SOURCES, 1):
            writer.writerow([f"S{index:03d}", *row])
    with (ROOT / "DATA/g11/source_ledger.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for index, (title, url, takeaway, disposition) in enumerate(SOURCES, 1):
            fh.write(json.dumps({"source_id": f"S{index:03d}", "title": title, "url": url, "takeaway": takeaway, "disposition": disposition}, ensure_ascii=False) + "\n")


def create_method_and_reports() -> None:
    write("METHOD_IR/g11/overnight_orchestration.md", """
    # Fail-Closed Overnight Orchestration

    The primary objective is valid HQ source-holdout evidence per irreversible compute unit, not raw GPU-hours. A run identity is the SHA-256 of dataset, split, feature schema, code, target, route, caliber, seeds, model bank and protocol. Resume is legal only under exact identity equality. External live PID plus an exclusive owner lock prevents duplicate heavy jobs without killing any process. Checkpoints and heartbeats use temporary-file, fsync and atomic replacement. ETA is the rolling median unit duration times remaining units and stays unknown until three observations. TabPFN is an explicit comparator admitted only with package, bound checkpoint hash, known GPU state and same split; missing evidence blocks the lane rather than silently shrinking the bank.
    """)
    write("METHOD_IR/g11/formulae.md", """
    # Formulae

    `run_id = SHA256(canonical_json(identity))`.

    `checkpoint_ok <=> SHA256(bytes) == sidecar AND checkpoint.run_id == requested.run_id`.

    `ETA = median(last k durations) * remaining_units`, emitted only after at least three units.

    `R2_pooled = 1 - sum((y-yhat)^2) / sum((y-ybar)^2)` from all held-out predictions. Mean fold R2 is not this statistic.

    Fold-safe fusion learns nonnegative weights on inner-OOF training predictions only; held-out source labels are forbidden in member fit, selection, fusion, calibration and thresholding.
    """)
    write("METHOD_IR/g11/method_ir.yaml", """
    method_id: G11_OVERNIGHT_TABPFN_DUAL_CALIBER
    version: 1
    adapters:
      runtime: modules/r07_tabpfn_ir/g11_overnight_runtime.py
      dual_caliber: modules/r11_dual_caliber/g11_dual_caliber_contract.py
    failure_signatures: [LIVE_PID_COLLISION, STALE_LOCK_UNREVIEWED, CHECKPOINT_HASH_MISMATCH, RUN_IDENTITY_MISMATCH, TABPFN_RUNTIME_UNBOUND, GE5_AS_LOSO, REGISTRY_ENTRYPOINT_MISMATCH]
    claim_ceiling_without_real_receipts: HONEST_PARTIAL
    """)
    write_json("METHOD_IR/g11/failure_signature_matrix.json", {
        "LIVE_PID_COLLISION": {"action": "block and observe", "forbidden": "kill or duplicate"},
        "STALE_LOCK_UNREVIEWED": {"action": "explicit review before reclaim", "forbidden": "silent steal"},
        "CHECKPOINT_HASH_MISMATCH": {"action": "quarantine", "forbidden": "resume corrupt state"},
        "RUN_IDENTITY_MISMATCH": {"action": "new isolated run", "forbidden": "cross-dataset resume"},
        "TABPFN_RUNTIME_UNBOUND": {"action": "block comparator; preserve bank", "forbidden": "silent member drop"},
        "GE5_AS_LOSO": {"action": "reject receipt", "forbidden": "FULLSCORE"},
        "REGISTRY_ENTRYPOINT_MISMATCH": {"action": "bind immutable serving graph", "forbidden": "deployment-exact claim"},
    })
    ledger_lines = ["# SOURCE_LEDGER", "", f"English sources: {len(SOURCES)}. Full machine-readable ledgers are in `DATA/g11/source_ledger.csv` and `.jsonl`.", "", "| ID | Source | Disposition | Takeaway |", "|---|---|---|---|"]
    for index, (title, url, takeaway, disposition) in enumerate(SOURCES, 1):
        ledger_lines.append(f"| S{index:03d} | {title} — {url} | {disposition} | {takeaway} |")
    write("reports/SOURCE_LEDGER.md", "\n".join(ledger_lines) + "\n")
    write("reports/PROJECT_SOURCE_AUDIT.md", """
    # Project Source Audit

    Resolved window: G11 `TRAINING_OVERNIGHT_TABPFN`; base `sddvacav/tiai-agent-os @ 3008e56`; exclusive apply scope `modules/r07_tabpfn_ir/**`, `modules/r11_dual_caliber/**`, `DATA/g11/**`.

    Audited truth: `t18_gate09_campaign.py` uses equal-mean fusion while registry language names fold-inner NNLS; NNLS exists in `t18b_gate09_round2.py` and `t60_common_strongbase.py`. The bank contains HGB/ExtraTrees vote, LightGBM, XGBoost and CatBoost paths. TabPFN is referenced with top-80 features and a train cap of 8,000, but its package/checkpoint/runtime binding is unresolved. The active feature contract, serialized serving champion and serving route are also unproven. This return adds orchestration and evidence contracts only; it does not rebind serving.

    Fleet B002-B005 were directly mounted. B001/B006-B010 are not represented as inspected. No numerical Ti/TMC rows are fabricated from uninspected archives.
    """)
    write("reports/IMPLEMENTATION_DIFF.md", """
    # Implementation Diff

    | concern | audited base | G11 delta |
    |---|---|---|
    | overnight coordination | no universal window-local contract proven | no-kill PID interlock, atomic owner lock, checkpoint, heartbeat, ETA |
    | TabPFN | referenced but runtime unresolved | explicit fail-closed comparator preflight |
    | GE5 vs LOSO | mixed-headline risk | separate record types and non-compensatory promotion |
    | serving binding | registry-entrypoint mismatch | blocker retained; no champion mutation |
    """)
    write("reports/TEST_DESIGN.md", """
    # Test Design

    Runtime tests cover deterministic identity, identity drift, current PID, duplicate lock, stale lock review/reclaim, checkpoint tamper, ETA history, TabPFN resource fail-closed behavior, external PID interlock, idempotent resume and resume-identity rejection. Dual-caliber tests cover exact/finite metrics, constant-target R2, pooled grouped evaluation, GE5/LOSO separation, external FULLSCORE receipt validation, duplicates and coverage gates. Synthetic fixtures are software evidence only.
    """)
    write("reports/PRESSURE_TEST.md", """
    # Pressure Test

    1. Live PID and duplicate lock must block while the owner remains alive.
    2. Dead-PID lock must require explicit review.
    3. Checkpoint mutation must fail digest verification.
    4. Dataset/split/feature identity drift must block resume.
    5. Missing TabPFN package/checkpoint/known GPU must block the lane without shrinking the declared bank.
    6. High GE5 with no HQ-LOSO must remain below gate and not FULLSCORE.
    7. Pooled OOF R2 must be recomputed, not averaged across folds.
    8. Registry NNLS language versus t18 equal mean must block deployment-exact promotion.
    """)
    write("reports/THREE_ROUND_QA.md", """
    # Three-Round QA

    A — mission/write scope: apply tree is restricted to the G11 paths; Method IR and reports are return-only.

    B — hard tasks/files: required DATA, runtime, dual-caliber contract, tests, source ledger and continuation brief are present.

    C — G6/claims: no real model metric, HQ-LOSO pass, champion or FULLSCORE is asserted. Local work is apply/smoke/path binding only.
    """)
    entries = [
        {"method": "PyTorch checkpoint pattern", "status": "ABSORBED", "artifact": "CheckpointStore"},
        {"method": "atomic tempfile/fsync/replace", "status": "ABSORBED", "artifact": "atomic_write_bytes"},
        {"method": "heartbeat semantics", "status": "ABSORBED_CONCEPT", "artifact": "HeartbeatWriter"},
        {"method": "fold-inner OOF NNLS", "status": "CONTRACT_ONLY", "reason": "existing implementation audited; no parallel rewrite"},
        {"method": "TabPFN-v2", "status": "BLOCKED_ADAPTER", "reason": "checkpoint/package binding absent"},
        {"method": "CORAL/IRM", "status": "REJECTED_AS_DEFAULT", "reason": "must beat route baseline under same HQ-LOSO split"},
        {"method": "mean fold R2 headline", "status": "REJECTED", "reason": "pooled OOF metric required"},
    ]
    write("reports/GITHUB_INTERNALIZATION_LEDGER.jsonl", "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n")


def create_root_docs() -> None:
    write("DESIGN.md", """
    # G11 Direct Delivery Design

    An overnight campaign is valid only when it creates recoverable, non-duplicated, split-identical evidence. The return therefore adds a small orchestration overlay and a separate evidence contract rather than another trainer. Existing scientific kernels remain callbacks. No process is killed, no stale lock is silently stolen, no checkpoint resumes across identity drift, no missing TabPFN dependency silently changes the bank, and no GE5 result is allowed to fill the HQ-LOSO field.
    """)
    write("TESTS.md", """
    # Tests

    CI runs Python compile checks, both unittest suites and a patch syntax check in an empty Git repository. The latter is not an exact conflict check against private base `3008e56`; local Codex must still run `git apply --check` on that exact worktree.
    """)
    write("LOCAL_CODEX_APPLY.md", """
    # Local Codex Apply — 0.01% Only

    1. In `E:\\Generated\\tiai-agent-os`, run `git status --short` and `git rev-parse --short HEAD`; HEAD must be `3008e56`, otherwise stop and use an isolated worktree at that commit.
    2. Verify `SHA256SUMS.txt` from this return.
    3. Prefer exact patch check/apply: `git apply --check <return>\\PATCHES\\G11_TRAINING_OVERNIGHT_TABPFN.patch`, then `git apply ...`. If a path already exists, compare and copy only the declared G11 files; do not overwrite unrelated modules.
    4. Run `python -m py_compile modules\\r07_tabpfn_ir\\g11_overnight_runtime.py modules\\r11_dual_caliber\\g11_dual_caliber_contract.py` and both unittest discovery commands.
    5. Run doctor only: `python -m modules.r07_tabpfn_ir.g11_overnight_runtime doctor --workdir E:\\Generated\\tiai-agent-os\\runs\\g11 --live-pid-file <actual-live-pid-file> --tabpfn-checkpoint <actual-checkpoint>`.
    6. If a live PID is detected, do not kill or launch another heavy run. If TabPFN is blocked, bind the real package/checkpoint hash or leave the comparator blocked. Resolve t18 equal-mean versus t18b/t60 NNLS before serving promotion.
    7. Wire `OvernightCoordinator.run_units` around existing fold×seed×member units after the live job ends. Return receipts only: diff check, tests, doctor, PID/lock/checkpoint hashes and real separate GE5/HQ-LOSO tables.
    """)
    write("CLAIM_BOUNDARY.md", """
    # Claim Boundary

    Allowed: tested fail-closed orchestration, checkpoint/heartbeat/ETA, TabPFN preflight, separate dual-caliber reporting and local-apply candidate status.

    Forbidden: any claim of new Ti/TMC model performance, real HQ-LOSO pass, deployment-exact champion, serialized serving graph or FULLSCORE. Synthetic smoke is software evidence only.

    Ceiling: software `COMPLETE_READY_FOR_LOCAL_APPLY` when CI is green; scientific `HONEST_PARTIAL / below_gate_continue_optimization`; `FULLSCORE_ELIGIBLE=false`.
    """)
    write("BLOCKERS.md", """
    # Blockers

    1. The web/public CI runner cannot observe the real Windows/WSL live PID; local doctor is mandatory.
    2. Registry names fold-inner NNLS while audited t18 uses equal mean; bind immutable entrypoint/config/artifact/feature/route hashes.
    3. TabPFN package, bound checkpoint and real GPU forward-pass receipt are absent.
    4. Active feature order/dtype/missingness contract is absent.
    5. Serialized served champion and route binding are absent.
    6. No real HQ-LOSO receipt exists in this window, so status remains below gate.
    7. Fleet B001/B006-B010 were not directly mounted in this window.
    """)
    write("PLATFORM_DIMENSION_CLAIM.md", """
    # Platform Dimension Claim

    ML utilization: explicit bank/TabPFN comparator admission and blocked-lane semantics.

    ML accuracy governance: typed GE5/HQ-LOSO ledger and non-compensatory promotion.

    Reliability: no-kill lock, checkpoint digest, heartbeat, ETA and exact-identity resume.

    Generality: target, route and caliber are part of the run identity; no numerical uplift is claimed before real HQ-LOSO execution.
    """)
    write("EVIDENCE/project_source_touchpoints.md", """
    # Project Source Touchpoints

    G11 mission/write scope; audited HGB/ET, LightGBM, XGBoost, CatBoost bank; TabPFN top-80/train-cap-8000 reference; t18 equal mean versus t18b/t60 NNLS blocker; missing feature/checkpoint/serving artifacts; Track S frozen and Track C source-holdout-first; direct fleet B002-B005.
    """)
    write("EVIDENCE/claim_evidence_map.csv", "claim,evidence,status\nsoftware_contract,modules+tests+CI receipts,TESTED\nTabPFN_comparator_ready,local doctor preflight,BLOCKED_UNTIL_BINDING\nHQ_LOSO_pass,real source-holdout receipt,MISSING\nFULLSCORE,all-target noncompensatory receipt,PROHIBITED\n")


def make_patch(paths: list[str]) -> str:
    chunks: list[str] = []
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        chunks += [f"diff --git a/{rel} b/{rel}", "new file mode 100644", "--- /dev/null", f"+++ b/{rel}", f"@@ -0,0 +1,{len(lines)} @@"]
        chunks += ["+" + line for line in lines]
    return "\n".join(chunks) + "\n"


def validate_and_patch() -> dict[str, Any]:
    compile_lines: list[str] = []
    compile_ok = True
    for rel in ["modules/r07_tabpfn_ir/g11_overnight_runtime.py", "modules/r11_dual_caliber/g11_dual_caliber_contract.py"]:
        try:
            py_compile.compile(str(ROOT / rel), doraise=True)
            compile_lines.append(f"PASS {rel}")
        except Exception as exc:
            compile_ok = False
            compile_lines.append(f"FAIL {rel}: {exc}")
    write("EVIDENCE/py_compile.txt", "\n".join(compile_lines) + "\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT.resolve())
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "modules/r07_tabpfn_ir/tests"), "-p", "test_*.py", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "modules/r11_dual_caliber/tests"), "-p", "test_*.py", "-v"],
    ]
    outputs: list[str] = []
    tests_ok = True
    for command in commands:
        result = subprocess.run(command, text=True, capture_output=True, env=env)
        outputs.append("$ " + " ".join(command) + "\n" + result.stdout + result.stderr + f"\nexit={result.returncode}\n")
        tests_ok = tests_ok and result.returncode == 0
    write("EVIDENCE/unittest.txt", "\n".join(outputs))
    apply_paths = sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "modules").rglob("*") if path.is_file())
    apply_paths += sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "DATA/g11").rglob("*") if path.is_file())
    write("PATCHES/G11_TRAINING_OVERNIGHT_TABPFN.patch", make_patch(apply_paths))
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
        patch = (ROOT / "PATCHES/G11_TRAINING_OVERNIGHT_TABPFN.patch").resolve()
        check = subprocess.run(["git", "apply", "--check", str(patch)], cwd=directory, text=True, capture_output=True)
    write("EVIDENCE/git_apply_check.txt", "$ git apply --check <patch>  # empty-repo syntax check; NOT private-base conflict check\n" + check.stdout + check.stderr + f"exit={check.returncode}\n")
    return {"py_compile_pass": compile_ok, "unittest_pass": tests_ok, "patch_syntax_check_pass": check.returncode == 0, "private_base_conflict_check": "NOT_EXECUTED_PRIVATE_BASE", "all_software_checks_pass": compile_ok and tests_ok and check.returncode == 0}


def finalize(validation: dict[str, Any]) -> None:
    write_json("reports/VALIDATION_REPORT.json", validation)
    status = "COMPLETE_READY_FOR_LOCAL_APPLY" if validation["all_software_checks_pass"] else "HONEST_PARTIAL"
    write("WINDOW_STATUS.txt", f"{status}\nSCIENTIFIC_CLAIM_CEILING=HONEST_PARTIAL\nMODEL_STATUS=below_gate_continue_optimization\nFULLSCORE_ELIGIBLE=false\n")
    files = sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in ROOT.rglob("*") if path.is_file())
    manifest = {
        "window_id": "G11",
        "slug": "TRAINING_OVERNIGHT_TABPFN",
        "artifact": NAME,
        "repo": "sddvacav/tiai-agent-os",
        "base_subject_sha": BASE_SHA,
        "exclusive_mission": "overnight training, TabPFN comparator and dual-caliber accuracy-attack contract",
        "apply_scope": ["modules/r07_tabpfn_ir/**", "modules/r11_dual_caliber/**", "DATA/g11/**"],
        "return_only_scope": ["METHOD_IR/g11/**", "reports/**", "EVIDENCE/**", "root governance files"],
        "source_ledger_count": len(SOURCES),
        "english_query_count": len(QUERIES),
        "validation": validation,
        "software_status": status,
        "scientific_status": "below_gate_continue_optimization",
        "claim_ceiling": "HONEST_PARTIAL",
        "hq_loso_receipt_present": False,
        "fullscore_eligible": False,
        "no_fabricated_metrics": True,
        "files": files,
    }
    write_json("RETURN_MANIFEST.json", manifest)
    write_json("EVIDENCE/artifact_build_receipt.json", {"builder": "GitHub-hosted public runner", "validation": validation, "content_checksum_algorithm": "SHA-256", "note": "Public runner contains generic code/contracts only; no private datasets, weights or metrics."})
    checksum_files = sorted(path for path in ROOT.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    write("SHA256SUMS.txt", "\n".join(f"{sha256(path)}  {str(path.relative_to(ROOT)).replace(os.sep, '/')}" for path in checksum_files) + "\n")


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    copy_sources()
    create_data()
    create_method_and_reports()
    create_root_docs()
    validation = validate_and_patch()
    finalize(validation)
    print(json.dumps({"artifact": str(ROOT), "validation": validation, "sources": len(SOURCES), "queries": len(QUERIES)}, indent=2))
    return 0 if validation["all_software_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
