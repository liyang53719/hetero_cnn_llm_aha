# Packed Public M16 asset preparation proposal

This is a separate, preparation-only contract. It does not amend the original
M16 fresh verifier, the existing M128 seal, numerical thresholds, output fences,
or the untouched be00 workspace. No producer or authentic numerical run was
executed while preparing this proposal. No weights were copied or downloaded.

## Exact origin, no relabeling

`pins.json` binds the retained metadata from commit
`be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5`: the M128 ASSETS and SETUP receipts,
their setup summary, source/context maps, payload manifest, backend identity,
native M16 result and paired-recipe reports, and original library/reference
compile receipts. Absolute paths and the origin workspace device/inode remain
authentic; an origin cannot be silently relocated or given new compile times.

The retained 13-tensor/22-segment payload is Qwen/Qwen2-1.5B-Instruct layer 0,
revision `ba1cf1846d7df0a0591d6c00649f57e798519da8`, plus embedding rows 0–255.
The subset is 94,382,080 bytes. Whole-checkpoint verification is not claimed.

The retained native M16 producer is explicitly
`qwen2-native-qkv-qk-pair-generated-v1`. Both BF16/FP32 modes, both original
reference methods, all 29 logical and export shapes, original BF16 limits,
exact mask, diagnostic-only FP32/softmax semantics, and the 116 export records
are retained. This is not relabeled as the original unmodified native producer.
The paired M128 report remains origin evidence; M128 tensor exports/arena are
not selected for reuse. Backend-order equivalence remains unproven.

`reuse.verify_reuse(origin, metadata_only=True)` is the default. It reads JSON
and source files, checks paths and stat sizes, and rejects aliases. It does not
open payloads, activation exports, tables or ELF bytes. Its result is
`METADATA_ONLY_NOT_READY`, with current-backend verification explicitly false.

The opt-in `metadata_only=False` additionally streams selected files as opaque
bytes and verifies the recorded compiler binary. It still decodes no tensors,
imports no numerical framework, launches no process, and never returns ready.
This mode was not executed during preparation. Current runtime identity is
checked separately by the deferred producer before any reference computation.

## M16-specific outputs required

The existing sequential/reduced binaries accept runtime M16. Their original
CPP/header hashes match the original M16 contract, but their existing M128
output inventories cannot substitute for M16 outputs. Reuse retains their
original compile receipts; it does not fabricate a new build.

- Readonly arena: 188,043,264 bytes; SHA256
  `0a94ea142c28a6c1ce4b8ad928caecee9c5721bb6e4bc0eb097eebd8202aabf8`
- Input X: 98,304 bytes; SHA256
  `271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c`
- Retained full table: 328,448 bytes; SHA256
  `5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045`

The arena is newly packed by the unchanged original helper for token/position
IDs 0–15, past=0, with zero intermediate preloads. The original table is read
in place. Exactly two original reference invocations each emit 22 raw outputs;
the sequential producer also emits its original 29 tensor exports. These new
outputs stay in a fresh, disjoint private directory.

## Execution boundary and integration

`producer.py` has a plan-only CLI. It deliberately has no `--execute` option:

    python -B -m candidates.qwen2_resident_matrix.attention_packed_m16_assets.producer \
      --origin /path/to/untouched-be00-run --output /path/to/new-m16-references

`--check-metadata` adds the read-only metadata/source audit. Neither CLI path
calls `produce()` or opens authentic payload/ELF bytes.

`produce()` is an uninvoked primitive for a later separately reviewed launcher.
It must run in a fresh process using the retained Python 3.12 environment with
the original four-thread environment policy. It rechecks Torch 2.10.0+cpu,
NumPy 2.3.5, Transformers 4.40.1, exact installed model sources/build identity,
AVX512/MKLDNN, unset ATEN_CPU_CAPABILITY, deterministic settings and thread counts.
It disables bytecode writes to the original source and directs temporary/cache
files into the new output. It does not install, download, compile, copy payloads,
load an alternate numerical top, or execute the Public DUT.

Proposed limits, not authorization or a completion estimate: one attempt,
120-second shared work ceiling, at most 30 seconds per reference process,
5 seconds to kill/reap an interrupted child group, and a proposed 126-second
external supervisor. SIGALRM and SIGTERM raise through the process-group cleanup
path, with work/termination signals deferred during bounded cleanup. Receipts
are atomically published; caught write/fsync/publication failures remove the
completion marker. No automatic retry is provided. The launcher must require
successful child exit plus the fully validated receipt: a file alone never
establishes completion. It remains responsible for the external deadline and
safe failure evidence, including an unkillable child or SIGKILL case.

`reuse.snapshot()` returns the five-file preparation source closure for the
future linked launch contract. The deferred producer checks it before/after
and emits it in `M16_REFERENCES.json`. Original metadata is preserved as explicit
origin references. New reference run receipts have real new paths/timings.

The output is always
`REFERENCE_PREPARATION_ONLY_NOT_NUMERICALLY_ADMITTED`: ready_for_actual=false,
packed_source_profile_linked=false, numerical_acceptance=false,
full_29_node_acceptance=false, hardware_recipe_acceptance=false and
rtl_execution=false. The separate `attention_packed_m16` owner must freeze its
composed source/observer profile, build and verify the combined library using
the unchanged original strict builder/verifier in that composed tree, then
implement reviewed linked admission. This proposal cannot authorize that run.

## Cold tests

    python -B -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_assets.test_assets -q
    python -B -O -m unittest candidates.qwen2_resident_matrix.attention_packed_m16_assets.test_assets -q

Tests use invented metadata, tiny synthetic files and mocked subprocesses only.
They cover strict JSON, shape/type/path/alias guards, original threshold and
diagnostic semantics, plan-only behavior, bounded budgets and signal cleanup.
They do not generate arrays, install packages, hash authentic payloads, execute
reference producers or establish numerical acceptance.
