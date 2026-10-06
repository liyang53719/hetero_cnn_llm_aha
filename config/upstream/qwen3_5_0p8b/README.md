# Qwen3.5-0.8B pinned source metadata

These five files preserve upstream raw bytes. `manifest.json` records immutable revisions, exact URLs, lengths and SHA256 hashes. Python files retain their upstream copyright/license headers and are read as evidence only; the geometry gate never imports or executes them.

The model checkpoint and Transformers code revisions are independently pinned. This does not establish that the code is the checkpoint's original training implementation. The index checks tensor names; shapes are derived from config/code, not read from safetensors headers. No checkpoint weight payload is included.

Run `python scripts/run_qwen35_dense_contract.py` from the repository root to validate the bundle, compiler profile and complete main-text tensor-name inventory offline. Full numerical/precision/RTL/performance gates remain open.
