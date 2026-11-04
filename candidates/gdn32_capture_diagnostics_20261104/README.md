# Finite DUT capture diagnostics (source only)

The consumer reports capture failures as `DUT_CAPTURE` and retains the fixed `TimeoutError` class. The paired safe collector accepts those finite values while preserving exact fields, authenticated gzip/outer-cleanup checks, bounded output and refusal behavior. It never prints exception messages, raw logs, weights or model outputs.

This fixes observability only. Run 41861520194, job 126684286288, ended with supervised consumer exit 2 after 4774.21 seconds against a 4764-second DUT window. An internal wall timeout is consistent with this evidence, but the original inner capture receipt is unavailable; actual DUT exit and numerical mismatch are not proven.

No workflow, launch nonce, historical retry5 source or execution budget is changed. A future runner must explicitly pin this collector and the current source catalog. Historical launch manifests continue to bind their historical source commit, not current main. Hardware, driver, numerical acceptance and MAC capacity are unchanged.

Run from repository root:

    python -B candidates/gdn32_capture_diagnostics_20261104/test_diagnostics.py
    python -O -B candidates/gdn32_capture_diagnostics_20261104/test_diagnostics.py

The tests exercise finite events and actual bounded gzip/receipt reader behavior with synthetic receipts. They perform no native execution and establish no numerical acceptance.
