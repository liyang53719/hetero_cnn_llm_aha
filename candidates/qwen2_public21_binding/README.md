# Current-source public21 binding candidate

This package is an isolated source-composition and control-test handoff. It does
not change production sources or wire a reduction coordinator into the production
`QwenOwnerKernel`. Its separately named harness binds the actual public decoder
to the actual reduction coordinator; owner/backend returns in its tests are
controlled protocol stimuli. No arithmetic or full-block numerical claim follows.

## Cold gate

From the repository root, with a fresh destination whose parent already exists:

```sh
python candidates/qwen2_public21_binding/compose.py \
  --out "$PWD/work/public21_binding_sources"
python candidates/qwen2_public21_binding/test_source_gate.py
python -O candidates/qwen2_public21_binding/test_source_gate.py
python candidates/qwen2_public21_binding/test_control_gate.py
python -O candidates/qwen2_public21_binding/test_control_gate.py
```

The default and only execution scope is `SOURCE_COMPOSITION_ONLY`. Python's `-O`
mode does not disable any guard. `--run-rtl` fails closed with an explicit message;
this package does not silently reinterpret an RTL request as a source pass.

The gate performs no network access, dependency downloads, compilation,
elaboration, RTL simulation, fixture generation, or numeric-payload generation.
It never updates source pins, patches, or historical evidence. There is no
refresh/rebase option. Drift requires a separate reviewed source change.

## Exact composition and provenance

1. Verify the immutable original overlay manifest against its fixed SHA-256.
   Verify its effective patch, nine conflict resolutions, all 15 historical patch
   identities, and every composition-helper identity. Historical helpers are
   provenance only; none executes.
2. Read the exact 70 Scala and six SV source files from Git commit
   `8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689`. Check every consumed source and
   provenance file against both the execution HEAD and current working bytes.
   The current public-dispatch generator, its pin file, and baseline control test
   additionally bind fixed commit `36dd2c473815a931e1f74463e9d43e538c11f2f6`.
3. Apply `current_overlay.patch` at exact declared line positions, with no hunk
   fuzz or offset. Verify all 76 intermediate postimages. Exactly 20 files change.
4. Apply `attention_preflight.patch` only to `HostBlockCommands.scala`. Verify all
   76 attention-stage postimages. This adds the explicit official-profile Attention typed
   virtual-root preflight using the existing resident scanner. The preflight is
   guarded by resident enablement and the official numeric policy.
5. Apply the separately pinned `dispatch_abort.patch` to the actual parser,
   verify its exact before/after identities and every final source postimage.
   This is an explicit third stage; it does not revise either prior patch.
6. Verify the separately pinned harness and test, copy them into the isolated
   output, then recheck every consumed working input. Publish only to a fresh,
   ignored directory below this checkout's `work/`, with no symlink or traversal
   paths and no overwriting old evidence.

The fixed source commits must already be available locally; the gate will not
fetch missing Git objects. The actual execution HEAD is recorded. No HEAD allowlist is used: unrelated
metadata commits can advance while all consumed bytes remain exact. A commit ID
alone never establishes semantic equivalence. Any consumed Git-source,
working-source, helper, patch, or manifest drift rejects composition.

The 92 current H2048/loan added lines remain represented: 84 literal and eight
explicit adaptations. The new loan/fixed-bank source files remain byte-identical.
Borrower and loan defaults stay false, and the default numeric policy is
`LegacyV0`. The old kernel is never copied from a historical assembled tree.

`evidence/overlay_manifest.json`, `explicit_resolutions.json`, and
`evidence/compile_inputs.json` preserve the reviewed proposal bytes, including
historical identifiers and paths for provenance. Those historical paths are not
used to obtain or overwrite composed source files. The original attention adapter
is preserved as evidence; the gate applies only the explicit checked patch.

## Compiler handoff

`compile_inputs.json`, `compile_sources_91.list`, and `test_sources_2.list` in the
fresh output describe exactly:

- 70 composed repository Scala sources, including P0 and integration sources
- 20 caller-fetched, individually pinned HardFloat Scala files
- One candidate `Public21DispatchHarness.scala` Compile source
- Two Test sources/classes: existing `Qwen2Public21DispatchControlSpec` and new
  `Public21ReductionDispatchControlSpec`

All listed paths are relative to that output. By default the 20 external
HardFloat paths are an explicit missing-input contract, and
`compile_inputs_ready` is false. To materialize them without fetching anything:

```sh
python candidates/qwen2_public21_binding/compose.py \
  --out "$PWD/work/public21_binding_sources_with_hardfloat" \
  --hardfloat-source /caller/fetched/source/root
```

The supplied root must contain `hardfloat/src/main/scala/` with exactly the 20
pinned files. The fixed HardFloat commit is
`c1105e6ac6a0dd90fc80893efc4830ab609005d3`. Their identities also bind the existing
repository HardFloat pin file. No dependency tree is committed here.

The included opt-in `run_control.py` uses the caller's already-provisioned
Scala 2.13.16, Chisel/plugin 6.7.0, sbt 1.10.2, chiseltest 6.0.0, and ScalaTest
3.2.19 toolchain. It must use a fresh isolated target, the exact 91 Compile and
two Test source lists, and freshly generated metadata fixtures from the current
`candidates/qwen2_resident_matrix/public_dispatch/generate_contract.py`.
Hash the fixture gate, each manifest, each metadata table, the toolchain, and all
source inputs before and after running both test classes. Do not reuse old
classes, simulator binaries, fixture receipts, or test outputs as new evidence.

The six preserved SV files are not Scala Compile inputs. No weights, numerical
payloads, ELF files, simulator products, or downloaded tools belong in this
candidate directory. Any control-simulation receipt must keep owner completion
mocking, no arithmetic execution, and no full-block numerical acceptance explicit.

## Explicit control RTL run

The runner defaults to `NOT_EXECUTED` without creating output or invoking tools:

```sh
python candidates/qwen2_public21_binding/run_control.py
```

Only the explicit flag runs the two suites. For an already fetched toolchain:

```sh
source work/chisel_toolchain/env.sh
python candidates/qwen2_public21_binding/run_control.py --run-rtl \
  --out "$PWD/work/public21_binding_control" \
  --toolchain-root "$PWD/work/chisel_toolchain" \
  --hardfloat-source "$HARDFLOAT_SOURCE"
```

The runner verifies the existing fixed tool archives and all 20 HardFloat pins;
its sbt project is offline and cannot repair an incomplete dependency setup.
The caller must provision missing tools/dependencies before a fresh retry. It
creates a private project and target below its new output, verifies the actual
91 Compile/two Test source sets in sbt, and runs one process group with a
600-second watchdog plus a 15-second termination grace. Acceptance requires
exactly two tests, zero skipped/canceled/pending tests, 22 expected markers
(including all 14 distinct candidate fault cases), immutable sources/metadata/
tool inputs, and fresh generated artifacts from both suites.

The fresh fixture gate and all six command/descriptor metadata tables are
hashed before and after. Testbench data consists of metadata and controlled
mock backend arithmetic returns. The actual parser, reduction coordinator, and
bridge are instantiated. Two FIR/SV pairs are copied from that run's own fresh
project into `rtl/HostBlockCommands/` and `rtl/Public21DispatchHarness/` beneath
the output. No previous run's artifact is linked or credited to the new pass.
Cold tests generate metadata only and exercise the runner guards; they never
invoke Scala, a compiler, or a simulator. An RTL receipt must be produced by a
separate explicit run; this package carries no inherited RTL PASS.
