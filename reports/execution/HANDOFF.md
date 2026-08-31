# Local-agent handoff v7.3 — main only

Pull `main`, run `check_main_only_workflow.sh` and `sandbox_validate.sh`; do not create branches or force-push.

## Active Qwen2 gate

q128 single-process E2 PASS: 1,536 rows/240 tasks/3,222,082 cycles. q384 sampled E2 PASS: 2,304 compared rows containing all frozen 180 rows, 1,872 controller tasks/4,608 merges, 14,756,016 cycles. Next run q1024 frozen 108 rows with 12,672 tasks and exactly 43,008 merges, then random backpressure, zero score/probability DDR and service curves.

Use `scripts/import_service_curve.py` for measured Attention/SiLU/DDR/queue/bank/event JSON. Below 315 t/s reopens the budget.

## v7.2 synchronized

The repository now includes multi-seed Attention vectors, integrated low-bit frontend source, eight-slot state/COW source, tiny Qwen3.8 multilayer trace and service importer. These are E0/source-ready, not replacements for local RTL gates.

## Model identity

Qwen3.5-35B-A3B is `qwen3_5_moe`: 40 layers, 30 GDN + 10 dense full-attention, 256 experts top-8, standard residual.

Qwen3.8-Flash-Next is `qwen4_exp`: 48 layers, 36 GDN + 12 QSA, four-branch gated residual, PLE, 512 experts top-10. It is not Qwen3-8B or a dense Qwen3.8 architecture. See `reports/QWEN35_QWEN38_FLASH_NEXT_ARCHITECTURE_DELTA.md` and `reports/QWEN_MODEL_FAMILY_SANDBOX_PLAN_V7_3.md`.
