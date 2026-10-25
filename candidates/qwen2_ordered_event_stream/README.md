# R2 correction: cancellation and original exception identity

R1 was blocked by independent review receipt SHA503ed5315c1bf8778e9dc366b5a142c3702cdca6c4fdaf93c11864d07cfc9e7c: monitor cleanup SystemExit could replace an original driver RuntimeError, and raw receipt MemoryError could replace an original driver ValueError. R1 is not a GO release.

R2 catches monitor-only SystemExit and other non-cancellation BaseException as sticky capture failures. Original driver Exception/SystemExit/KeyboardInterrupt identities always propagate. KeyboardInterrupt during setup cancels before driver execution and cleans already-entered observers; cleanup KeyboardInterrupt with no original error remains cancellation after other cleanup. If an original driver exception is already active, cleanup/receipt failure cannot replace it. Explicit user cancellation is outside any promise to continue computation. Raw receipt failures are diagnostic state and later acceptance FAIL, never replacement driver return values. Storage callback SystemExit is converted to an Exception understood by the unchanged old callback; storage KeyboardInterrupt remains cancellation.

No R1 frozen file was changed. The author publication adaptation did not repeat capacity samples or tests; the published capacity samples preserve the earlier R1 measurements, while SOURCE_PROVENANCE.json and software_tests/RESULTS.json pin the author R2 regression/delta evidence. Independent R2 review separately repeated a synthetic M16 storage sample: 44,355 events, 3,988,979 bytes and process MaxRSS 16,372 KiB. This is not DUT RSS or a hard memory bound. No native, numerical, official-reference or RTL execution occurred.

# Bounded complete raw event retention candidate

Status: SOFTWARE PREPARATION ONLY. No DUT/native/ML/official-reference/RTL run, no numerical PASS, no M16 PASS, and no M128 budget admission. The independent frozen budget audit was preserved unchanged.

## Scope and integration boundary

`candidates/qwen2_ordered_event_stream/` is a new independent candidate. The original fullgraph entry, observer, resident Matrix service/client, native ELF, and all old pins are untouched. `RETENTION_WIRING_DIFF.patch` compares the original fullgraph entry's three files to the new three-file wiring. New storage is in `stream.py`; existing nine-method frame-sensitive `_return` callback is inherited unchanged. Attention `_line` and `_return` callbacks also remain inherited directly, without stack-frame-changing wrappers.

- `service_trace.make_trace(..., event_stream_path)` uses an append-only disk sink, never a Python list of events. Its `seal()` returns a small receipt, not `tuple(events)`.
- `bridge.make_dispatch(..., enabled=False, event_stream_path=None)` remains default off and calls the same direct binding, ordered lanes and actual owner driver with original final ACK stall 5 / raw-KV false. State holds only raw/sealed receipts, not full event tuples.
- `runner.run_actual` changes only the bridge destination, event retention and receipt count, plus explicitly importing the unchanged old registry. It still requires M16, wall <=1800, the same original execution admission, and unchanged numerical/terminal gates. This piece does NOT enable M128.
- This runner and the independently prepared M128/oracle runner share an old baseline. Neither set of pins describes their future merge. A fresh composer must check both exact baseline/patch/postimages and all merged imports before any combined profile can qualify.

New profile fields are mandatory: `event_stream_max_bytes` and `event_stream_max_events`. Destination is `out/attention_service_events.q2evt`. The nested `actual_attention_capture/EVIDENCE.json` references it as `../attention_service_events.q2evt` with explicit `path_base=evidence_directory`.

## Complete raw recording versus successful acceptance

File format is `Q2EVT1\r\n`, followed by each original event as a little-endian u32 byte count plus compact ASCII JSON of the exact `(method, edge, payload)` tuple. A footer contains marker 0xffffffff, u64 count and SHA256 of all framed records. The single-pass reader additionally returns SHA256 of the exact file bytes from that same FD. Record limit is 1024 encoded bytes, raw event ceiling 3,000,000, absolute configurable byte ceiling 1 GiB. No tensor values are serialized beyond the old callback's existing immutable operand/result SHA256 strings.

- `replay_raw()` preserves original raw tickets, epochs, values, event order and invalid lifecycle events. It only proves bounded encoding/footer/count/hash integrity. Consuming a prefix is NOT complete recording proof.
- `replay()` / `verify()` additionally require exact successful group/event counts and lifecycle validation. Canonical replay transiently substitutes only the proven first-appearance ticket ordinal. No permanent ticket dictionary or canonical event array exists.
- `raw_complete=True` means the entire observed recording has a flushed/fsynced footer. `complete=True` additionally means successful lifecycle acceptance. A raw-complete aborted/foreign stream MUST remain `complete=False`.
- Audit errors are sticky but do not raise into the inherited callback. While storage remains writable and in bounds, later original abort/ACK/release events continue to be recorded. Final `seal()` rejects the whole stream. Synthetic abort/foreign fixtures prove the trailing owner response and release are retained and raw replay equals the whole invalid input sequence.
- A true storage/encoding/byte/count-cap failure can only preserve an incomplete prefix. It raises inside the old callback's existing try/except, which stops monitoring without replacing the service return/ACK. No retry, sampling or fabricated continuation. Receipt includes successful-record count, observed append attempts, first/last fully written frame SHA, failed frame SHA when encodable, and sticky reason. The unobserved tail count is unknown, not zero.
- Open/header failures produce an absent/partial receipt and later capture FAIL, not a replacement driver exception. Existing files are never overwritten or adopted. Original driver exceptions still propagate; cleanup cannot replace or suppress them.
- `max_events` is independently admitted, not the successful expected count. Example successful M128 count is 2,478,339; a candidate finite cap 2,478,403 permits 64 extra failure-tail events. The 64 is an explicit policy allowance, NOT a proof that all possible abort/erroneous tails fit. Exceeding either cap must record incomplete truncation, not silently drop events.

## Lifecycle and native ticket proof boundary

The pinned native `ffn_attention/matrix_numeric.cpp` declares `nextTicket=1`, assigns `ticket=nextTicket++` in `beginGroup`, and deliberately does not reset nextTicket in `td_reset`. Release/abort do not assign nextTicket. Python Matrix reset advances epoch and clears ownership. Exact source identities are in `SOURCE_LOGICAL_PINS.json`.

This auditor accepts only one successful normal pc12 owner, context0, QK opcode0x23/profile2/mask255 with eight steps, and legacy PV opcode0x24/profile0/mask1 with 1..128 steps. At most one original group is live. It checks every step boundary/result/done/reply debt, one owner terminal response, release, exact groups and constant epoch. First ticket need not equal 1 because the same ELF may have completed prefix groups. All tickets are positive uint64, first ticket must leave room for the expected group count, and later group tickets must strictly increase; within-group result/done/reply ticket and epoch must match exactly. Therefore first-appearance normalization is a bijection on the admitted finite non-wrap sequence without retaining historical ticket objects.

This is NOT a general reuse/reset/abort/multi-owner/wrap protocol. Native uint64 overflow is not itself prevented by this candidate; a wrapped/decreasing/zero ticket stream cannot pass. Multi-owner, reset epoch changes and abort remain raw evidence but reject successful seal. No hardware resource or service arithmetic changes are made.

## Passive monitoring failures and foreign ownership

Source origin/hash/class/MRO/exact code binding errors remain pre-execution refusals. Only after those checks can non-cancellation monitoring installation/cleanup failure fall back to the original driver with sticky later acceptance FAIL. The source-bound frame callbacks are not wrapped.

The two narrow adapters check slots 3/4, global and each target-code local mask, reserve an instance-specific label, and retain exact bound callback objects. `get_tool=None` does not prove callback absence: if `register_callback` returns an old hook, restoration is attempted and the candidate refuses. Successful restoration preserves that stale hook; an API restoration failure is reported as uncertain and is not blindly retried. On cleanup, changed label/global/local mask or replaced callback is preserved, with sticky error and residual tool reported. Cleanup is once-only and never retries an uncertain failed operation. Non-cancellation monitoring errors are recorded without escaping into the service callback; explicit KeyboardInterrupt cancellation propagates as documented above, while cleanup cannot replace an already active original driver exception. This is failure isolation, not evidence that production off/on noninterference has been run.

## Bounded measurements, not DUT RSS

`synthetic_evidence/M{1,16,32}.json` retains R1 measurements of lazy synthetic records with their original R1 source hashes, not new R2 measurements. `synthetic_evidence/CAPACITY_PROVENANCE.json` states this boundary. Each process has AS384 MiB, CPU45s, file64 MiB, FD64; shell timeout60s. Generated files are temporary synthetic data. Commands:

```
python -I -S -B candidates/qwen2_ordered_event_stream/measure_capacity.py --rows 1
python -I -S -B candidates/qwen2_ordered_event_stream/measure_capacity.py --rows 16
python -I -S -B candidates/qwen2_ordered_event_stream/measure_capacity.py --rows 32
```

M32 covers 164,547 complete events, including multi-step legacy PV and multiple QK groups. Small synthetic edge/ticket numbers are NOT a conservative file-size maximum. `synthetic_evidence/SCHEMA_BOUND.json` gives a separate exact successful-schema upper bound with max uint64 edge/ticket/epoch, uint32 tags, 64-character digests and maximum Boolean widths. M128's successful records require at most 327,511,498 bytes including header/footer by that schema calculation. A separately admitted 512 MiB file cap has room for that successful schema, but is not a universal guarantee for malformed/error streams. The absolute per-record hard bound remains 1024 bytes.

Recursive `sys.getsizeof` measures a Python object graph, not allocator/native/file/page-cache memory and not RSS. `tracemalloc` measures Python allocation peaks while writing/replaying. `ru_maxrss` is the synthetic process's actual high-water RSS and includes its interpreter/imports/measurement overhead, NOT a future full DUT. Final sample results and exact source hashes are recorded in the JSON logs. Only final R1 measurements with original source hashes and explicit provenance are published; no new R2 capacity run is claimed.

This removes the old long-lived raw list + two tuple pointer arrays, future canonical arrays, and full-run JSON str/bytes copies from this retention chain. It does not reduce native compute, PackedFields arrays, observer metadata sets, SiLU buffers, other fullgraph captures, or I/O/fsync cost. Old 491 MB full-block RSS is still insufficient for a new M128 overall budget. M128's 2,478,339 callbacks and replay cost are not estimated from these synthetic timings as DUT throughput.

## Reproduction and acceptance status

R1 baseline had four scripts: `test_stream.py`, `test_service_trace.py`, `test_bridge.py`, `test_runner.py`. `software_tests/RESULTS.json` records this R2 revision: 109 tests under `-I -S -O` and 14 delta tests in normal mode. R1 separately passed 95 tests in each of four modes; that is not relabeled as R2 testing. `reference_functions.py` contains verbatim dedented old callback/canonical functions only for software comparison; its original source/fragment pins are in `REFERENCE_FUNCTIONS.json`. Tests never import target DUT/ML/native modules, launch references or read tensor payloads.

Covered: exact raw replay; old canonical equality at M1/M2/M16; ticket alpha bijection/collision/foreign/result/done/reply, step/edge order, duplicates, abort, multi-owner, epoch, uint64 boundary; truncation/hash/trailing/byte/count limits; partial and failed writes/open/header/flush/fsync/close; failed raw audit continuing ACK/release; raw path resolution; original binding code/class checks; busy, dormant/replaced callback and foreign local/global mask protection; driver-return/original-exception preservation; runner terminal/reference ordering and unchanged M16/1800 gates.

Published source identities are listed in `SOURCE_PROVENANCE.json`; the repository directory also contains the documented metadata and synthetic evidence. The private outer delivery manifest is not published. Independent exact source/control review passed within the scope recorded in `INDEPENDENT_REVIEW_PROJECTION.json`. It is not a numerical result or execution authorization. Fixed physical MAC count4096, legacy PV upper bound63.57%, and 80/90% hardware thresholds are unchanged and not passed.

SOURCE_PROVENANCE.json retains the historical author-stage PENDING status. The later bounded source/control review is identified in INDEPENDENT_REVIEW_PROJECTION.json; that projection does not grant numerical or execution authority.

Source-input pins for matrix_numeric.cpp and matrix_service.py identify previously composed selected postimages, not the bare current main files. A future composer must reconstruct those exact pinned preimages or independently qualify its delta; checking out raw main alone does not establish compatibility or numerical admission.
