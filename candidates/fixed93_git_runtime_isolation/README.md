# Isolate fixed Git execution dependencies

These two stdlib-only preparers separate fixed Git source provenance from an actively committed publication checkout. They do not delete Git pins, repin a moving HEAD, run Git, compile or load native code, run preflight, or execute a model.

## Small tests

From this directory, run the two independent synthetic suites:

    python -I -S -B test_prepare_fixed_git.py
    python -I -S -B test_successor_metadata.py

The snapshot suite covers 30 metadata and tiny-file cases. It only parses the supplied historical verifier fixture as AST. The successor suite covers 29 pure metadata cases under a single-CPU, 10-second CPU and 128 MiB address-space cap. It never calls the materialization entry point. Passing these tests is not Git execution, native qualification or full-block numerical acceptance.

## Separately authorized materialization

Every path argument is explicit; there are no private-machine path defaults.

    python -I -S -B prepare_fixed_git.py --runtime-pins ABSOLUTE_PINNED_RUNTIME_JSON --profile-root ABSOLUTE_PINNED_PROFILE --output ABSOLUTE_FRESH_SNAPSHOT

The first tool requires four exact historical content pins. It reconstructs the fixed HEAD bytes from the pinned lineage and checks the original SHA, streams the exact five other Git files into normal independent files, and preserves the verifier except its two lineage-binding literals. Eighteen runtime paths relocate; the other 1,620 pins remain unchanged. Output is capped at 64 MiB, including its final receipt. It never reads the live publication HEAD or copies loose objects. This is a dedicated fixed-identity directory, not an OS-immutable sandbox.

    python -I -S -B prepare_successor.py --predecessor ABSOLUTE_PINNED_ASSEMBLY --snapshot ABSOLUTE_REVIEWED_SNAPSHOT --snapshot-receipt-sha REVIEWED_RECEIPT_SHA256 --output ABSOLUTE_FRESH_ASSEMBLY

The second tool requires three exact predecessor content pins and the explicitly reviewed snapshot receipt SHA. It independently checks eighteen path relocations, fifteen unchanged nongenerated Git/profile pins, the other 1,620 unchanged runtime pins, and current profile/manifest consistency. Only three small metadata files are replaced and one isolation contract added. All 306 model-source, nine selected and six support files remain byte-identical. It copies no weights, frozen input/reference payloads, Git pack or old run files. Output is capped at 9 MiB including a new receipt. No admission or prior PASS is inherited.

Both commands fail on aliases, changed pins, inconsistent inventories or a nonfresh output. Checked reads use one FD with before/after identities. A failed output is left for inspection, not deleted or retried automatically. The later full preflight must still hash all 1,638 runtime dependencies and all 46 frozen nonreference files, stat the 30 reference payloads, and preserve the original reference gate. These tools do not waive that preflight or prove a complete M128 run.

This source package intentionally excludes machine-specific runtime manifests, raw logs, materialization receipts, Git objects, inputs, weights and reference payloads.
