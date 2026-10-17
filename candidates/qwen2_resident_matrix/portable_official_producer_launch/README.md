# Fresh same-host hosted M16 producer launcher

This is source preparation and cold-control validation. It does not constitute a
producer, Public M16, M128, RTL, or hardware qualification. No workflow in this
package automatically starts it. A separately reviewed caller must own the
actual launch and enforce an external TERM at 890 seconds, then KILL 10 seconds
later. The Python parent uses the same absolute 890-second work, 899-second
cleanup, and 900-second receipt deadlines. Timing on a fresh hosted runner has
not been measured.

## Invocation contract

After source publication and separate launch review, invoke the script with the
exact hosted CPython 3.12.15 interpreter, isolated mode, no bytecode writes, and
normal optimization: `python -I -B <root>/candidates/qwen2_resident_matrix/portable_official_producer_launch/launch.py --root <root> --out <fresh-private-output>`.

The source root must be the actual Git checkout matching the first push attempt's
GITHUB_SHA. The output must not exist and must be disjoint from the source root.
The published consumer helper validates the one setup-python loader directory.
Required resources are at least four affinity CPUs, 6 GiB MemAvailable, and 4 GiB
available disk. ISA overrides, source-side bytecode caches, and unpinned package
initializers are rejected. Dynamic control imports execute checked source bytes.

## What a real invocation would do

1. Validate the exact complete source, original tiny-consumer, and wheel closure.
2. Observe the actual Git HEAD in an owned child and create a private venv.
3. Bootstrap pinned pip 25.0.1, then install the 25 exact official runtime wheels
   using direct HTTPS URLs, SHA256, binary-only/no-dependency/no-index installation,
   and disabled pip configuration/cache. Both installs plus metadata inventory
   share one 300-second work cap. Reports must match the complete pinned package
   names, versions, URLs, SHA256, roles, and Python target. The resulting
   interpreter must contain exactly 26 distributions, all inside its venv.
4. Rerun the unchanged original fixed-case tiny consumer on that host and venv,
   with its existing 150-second work cap and authentic runtime/source result.
5. Create one exclusive source-bound parent context and one producer child. The
   child creates the official M16 output plus both independent C++ references,
   preserving the original native forward, 29-stage/116-export validators and
   phase budgets. It cannot authorize a Public run.
6. After observing and cleaning the original producer, launch a distinct owned
   verifier in the same venv and four-thread environment. It replays the original
   full export/small-gate array validator using `decode_native=True`; it does not
   generate another forward. The parent checks its exact attempt/source/context/
   runtime receipt, observes zero exit and cleanup, and rehashes the artifacts.
7. Only then write private QUALIFICATION.json, preserving the exact consumer-entry
   schema. `child_pid` and `child_exit_code` identify the producer, not its verifier.

All command leaders remain unreaped until identity-checked process-group cleanup.
On cancellation the producer gets cooperative TERM time to reap its independently
owned compiler group before the parent sends KILL. Every started stage retains
its observed/final exit and cleanup outcome, including failure. A nonzero exit,
missing output, deadline, validation failure, or cleanup failure prevents a new
qualification receipt. Reusing an existing output is rejected before writes.

## Outputs and boundaries

The private output contains package reports, installed metadata, detailed logs,
fresh tiny sources/ELF/result, parent context, producer tensors and references,
the independent verifier receipt, and the qualification. Only the bounded
`evidence/summary.json` is intended as safe uploaded status evidence. Never upload
weights, arrays, private logs, or the entire output directory.

A serialized receipt is not authority to start the full M16 entry. Its actual
caller must check the launcher's zero exit and owned cleanup, retain the same
host/boot, interpreter, compiler and fresh tiny evidence, and use the exact entry
admission API. This package neither composes nor launches that full entry. An
old AVX512 native/M16 PASS or another runner's tiny PASS never transfers.

## Cold verification

Run the package's test files from a complete source checkout with `python -I -B
-m unittest discover -s <package> -p 'test*.py'`, and again with `-O`. Tests use
synthetic byte-only metadata/orchestration and bounded stdlib process controls.
They do not install packages, download weights, compile native code, import
Torch/NumPy/ctypes, execute a numerical model, or start CI. Full runtime
qualification remains unmeasured and unclaimed.

Pip provenance checks follow the official
[installation report specification](https://pip.pypa.io/en/stable/reference/installation-report/)
and the [pinned pip configuration implementation](https://github.com/pypa/pip/blob/25.0.1/src/pip/_internal/configuration.py).
