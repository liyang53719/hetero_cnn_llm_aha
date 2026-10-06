# Pinned safetensors metadata snapshots

These are original safetensors length-prefix + JSON header bytes, config/index
bytes, and separately pinned official Transformers source files. They are
provenance data; no vendored Python is imported or executed by these validators.

- Qwen2-1.5B-Instruct: `ba1cf1846d7df0a0591d6c00649f57e798519da8`
- Qwen3.5-0.8B: `2fc06364715b967f1860aea9cf38778875588b17`
- Qwen3.5-35B-A3B: `62704185bd97ad488cfc404e7caea797396b74dc`

The 16 header files contain 321,392 bytes and describe 2,637 tensors. Original
HTTP range metadata is reduced to the stable request, status, Content-Range,
length, body SHA256, acquisition date and opaque ETag; temporary signed redirect
URLs are deliberately omitted. An ETag is not interpreted as a content digest.
Official model API replies are archived snapshots: their revision is fixed, but
popularity fields in fresh API replies can vary. Advertised LFS whole-file hashes
remain **unverified locally**. No tensor payload was downloaded.

Each `manifest.json` binds its exact profile/config/forward/index/API/header and
receipt bytes. Code independently pins each manifest's SHA256. The offline check
validates full tensor extents, shape × dtype bytes, gap/overlap/file bounds,
index-to-shard coverage, and all main-text tensor shapes against fixed geometry.
Storage dtype is preserved: Qwen3.5 GDN A_log and norm.weight are F32; dt_bias is
BF16. This does not establish the arithmetic precision policy.

Qwen2 is one unsharded `model.safetensors`; its index URL returns HTTP404. The
single-file case is validated against official API metadata. Transformers
v4.40.1 was resolved to commit `9fe3f585bb4ea29f209dc705d269fbe292e1128f`, retaining
the existing source hashes. Qwen3.5's checkpoint and framework pins are separate;
they are not claimed to be the checkpoint-training implementations.

## Reproduce

Offline, with project dependencies installed:

```sh
PYTHONPATH=src python scripts/validate_workload_evidence.py --output work/header_workload_report.json
PYTHONPATH=src python scripts/validate_workload_evidence.py --require-complete
```

The second command intentionally exits 2: U00.2 remains OPEN.

Optional network re-acquisition into a new/empty directory:

```sh
python scripts/collect_weight_headers.py --output work/fresh_pinned_headers
```

The downloader first reads 8 bytes, checks the bounded header length, then reads
only that header. It rejects non-206 or mismatched ranges before reading a body,
and requires exact pinned header SHA256. Offline CI does not require Hugging Face
availability. No model support, official inference, actual RTL, or 90% utilization
claim follows from either command.

Transformers source files retain upstream copyright/Apache-2.0 notices; see the
repository LICENSE and source URLs recorded in each manifest.
