# Fresh Qwen2 M128 tail acquisition

This sibling leaves the original input recipe and its old manifest contract
unchanged. It acquires only the existing 14 fixed HTTP206 ranges from the pinned
official Qwen2-1.5B-Instruct revision. It validates 87,297,024 bytes against all
14 segment hashes and five whole-tensor hashes, the safetensors header, and the
original source-pinned metadata validator. It never downloads the full shard.

Default execution is a stdlib-only metadata check, with no payload reads,
network, writes, model, materialization, numeric package or RTL execution:

    python -B -S candidates/qwen2_live_tail_acquisition_m128/acquire.py

Explicit, authorized acquisition requires an absent sibling output path. There
is no resume, overwrite, arbitrary URL, arbitrary range or historical manifest
reuse. Real acquisition UTC timestamps and HTTP206 receipts are recorded in a
new FRESH_ACQUISITION.json with source identities before and after download.
Raw payloads and detailed receipts remain ignored in work/.

    python -B -S candidates/qwen2_live_tail_acquisition_m128/acquire.py --action acquire --execute --download --out work/qwen2_live_tail_acquisition_m128/run01/raw
    python -B -S candidates/qwen2_live_tail_acquisition_m128/acquire.py --action audit --execute --subset work/qwen2_live_tail_acquisition_m128/run01/raw

These files are not accepted by the old tail recipe's read_raw() loader. A
separate reviewed consumer is needed to materialize or numerically use the new
acquisition. No old PASS, old manifest, original HTTP timestamps, materialized
inputs, reference outputs, numerical or hardware acceptance is claimed.

Cold tests use synthetic bounded bytes and mocked responses only:

    python -B -S -m unittest discover -s candidates/qwen2_live_tail_acquisition_m128/tests -v
    python -B -S -O -m unittest discover -s candidates/qwen2_live_tail_acquisition_m128/tests -v

## Per-segment recovery after a lost session

`restore.py` keeps the fresh-only recipe above unchanged. Its default is also
metadata-only. It can copy the two hash-verified wo/gamma1 files from an explicitly
incomplete attempt without inventing lost HTTP receipts or timestamps. Their
provenance is `hash_verified_local_copy_from_incomplete_attempt`, with
`http_receipts_available: false` and `http_acquired_at: null`.

The remaining fixed segment indices 2..13 each require one separately authorized
`--action segment --execute --download --index N --out <recovery-path>` call.
Apply a 100-second outer timeout to each call; the downloader has a 90-second
socket timeout. Each successful call immediately persists its exact segment and
actual HTTP206 receipt. A completed segment is reverified without a request.
A segment file without a receipt requires a new fixed-range request to establish
fresh evidence. Neither payload pins nor source contracts are weakened.

Initialization requires `--action init --execute --reuse-incomplete <fresh-path>
--out <recovery-path>`. Recovery paths have the exact form
`work/qwen2_live_tail_segment_recovery_m128/<run-id>/<stage-id>`. A fresh output
is required for initialization. `--action finalize --execute --out ...` verifies
all 14 segment hashes and five tensor hashes, then writes RAW_READY.json.
`--action audit --execute --out ...` independently reads that result again.

The mixed-provenance seal explicitly records 12 fresh HTTP206 receipts and two
reused tensors lacking stored HTTP receipts. It never claims 14 current receipts.
This is pinned input recovery only and is deliberately separate from both the
fresh-only acquisition manifest and the historical tail materializer contract.

## Materialize the recovered five readonly roles

`materialize.py` uses the unchanged original pinned `transpose_words` and
`widen_bf16` functions, and the original independent byte-lane correspondence
validator. It consumes only a validated new RAW_READY.json and binds that exact
manifest, all raw/segment/receipt files and source identities before and after.
The new INPUTS_READY.json records its separate recipe ID and the honest mixed
raw provenance. Original metadata and historical manifests are not rewritten.
Five full output hashes provide additional corroboration; they do not replace
raw pin verification or the exact byte correspondence check.

    python -B -S candidates/qwen2_live_tail_acquisition_m128/materialize.py
    python -B -S candidates/qwen2_live_tail_acquisition_m128/materialize.py --action materialize --execute --subset <verified-new-raw> --out <fresh-input-stage>
    python -B -S -O candidates/qwen2_live_tail_acquisition_m128/materialize.py --action audit --execute --subset <verified-new-raw> --inputs <new-input-stage>

`read_inputs(relative, subset, namespace, pins)` returns the newly verified
input receipt; obtain namespace/pins with this module's `a.load_contract()`.
Consumers must use the new identity and reader explicitly. These inputs do not
satisfy the original recipe's historical raw-manifest contract by substitution.
No model, official forward, Matrix/Scalar numerical execution or RTL is run.

## Independent strict provenance reader

The unchanged original `restore.py`/`materialize.py` receipts remain historical
producer evidence. The original reuse reader did not strictly validate every
reuse-provenance field or the complete timestamp chain. `strict_reader.py`
adds those checks independently, while fixing all three original producer
source hashes and the three already-existing state/raw/input JSON hashes.
It neither rewrites those sources/receipts nor regenerates raw/materialized data.

`validate_provenance(state, ready, pins, inputs=None)` is a pure dictionary
validator: no filesystem, payload, network or writes. It checks the exact reuse
field set, fixed tensor identity, canonical common source directory, absence of
invented HTTP receipts, and copy <= state <= every fresh HTTP receipt <= raw
completion <= input creation. `verify_metadata()` reads only the fixed JSON and
source metadata, returning `result`, `state`, `raw`, and `inputs`.

    python -B -S candidates/qwen2_live_tail_acquisition_m128/strict_reader.py
    python -B -S candidates/qwen2_live_tail_acquisition_m128/strict_reader.py --action metadata --execute

`read_raw()` and `read_inputs()` are separate full-payload audit entry points;
they apply strict metadata checks before and after the original full byte/hash
and correspondence checks. Do not call those APIs, the original materializer's
`read_inputs`/`snapshot`, or the restorer's `state_read`/`verify_all` from a
metadata-only consumer.

    python -B -S -O candidates/qwen2_live_tail_acquisition_m128/strict_reader.py --action inputs-audit --execute

The cold test suite constructs synthetic metadata from published source pins;
its temporary JSON/hash fixtures are not real acquisition evidence. It runs in
a source-only checkout without work/. An optional real-receipt integration test
requires `QWEN2_STRICT_REAL_METADATA=1`; it skips if the ignored JSON is absent.
That separate test verifies the two actual original reuse records without
rewriting them. No old producer PASS or complete lost HTTP provenance is implied.
