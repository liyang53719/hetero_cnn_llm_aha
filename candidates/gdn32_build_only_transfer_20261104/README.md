# GDN32 build-only seven-file transfer

This dormant source publication adds a unique one-shot listener. Only a subsequent commit adding `ci_launch/gdn32_build_only_transfer_20261104_once.json` can launch it; the guard requires that commit to contain exactly that addition, point to its direct source parent, use attempt 1 and bind the existing explicit transfer approval receipt.

It calls the existing `gdn32_first_model162_producer_20261104` build and export entrypoints unchanged with `--hardware-source gdn-chunk32-abort-v2`. No model weights, reference data, runtime preparation, numerical consumer or DUT execution is performed. Export requires every original build stage's successful exit, owned-group cleanup and finalized lossless capture, then validates the exact seven-file manifest.

Only `dut.bin`, `hardware.sv`, `driver.cpp`, `source_manifest.json`, `tool_manifest.json`, `build_receipt.json` and `frozen_artifact.json` are uploaded. No logs, NPZ, references or weights. The artifact expires after seven days. This transfer is build provenance only, not Chisel numerical acceptance or final RTL replay.

Resource limits are unchanged: 9,000-second job; 7,200-second inclusive build cap; 900-second export reserve; fresh x86_64/Python 3.12 host; >=13 GiB available memory; >=20,671,240,864 free disk bytes; serial compilation and existing per-stage process-tree limits. Each stage also needs its full declared cap plus cleanup to fit remaining time. Failure stays INCOMPLETE and cannot trigger automatic reruns.

The previous same-hardware run's 28 bootstrap/build stages took 5,496.81 seconds in total, sampled peak RSS 9,669,734,400 bytes and peak tree 6,174,979,281 bytes. This is a cost observation, not a duration guarantee. This standalone path avoids spending the remaining hosted job time on full numerical acceptance.

Before cloud execution, verify this new artifact's source/run identity and complete seven-file hashes, fresh ABI/resource admission, the unchanged 4096-MAC hardware and numerical contracts, and a supported original-Chisel-first acceptance path. The existing older local binaries have different identities and cannot substitute for this cohort. Do not call generated-SV execution native Chisel simulation.
