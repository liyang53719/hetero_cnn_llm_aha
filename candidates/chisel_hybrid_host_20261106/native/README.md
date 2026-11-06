# TEMP: handwritten native bridge and finite endpoint sources

This directory preserves sixteen exact C/C++ and header files used in prior
compilation or compiler syntax checks against the original generated Matrix,
ICG and iDMA models. It adds no hardware
implementation and changes no Scala source or selected hardware.

`SOURCES.json` records relative filenames, byte counts, SHA-256 identities and
ordered quoted include names. The source files are unchanged. The directories
keep each local quoted header beside its consumers.

## Preserved scope

- `matrix_icg/`: Matrix and clock-gate C ABI bridges, direct/C ABI trace runners,
  trace parsing and Linux process-map observation. Prior finite direct/C ABI
  checks covered 377 Matrix frames and 20 ICG frames. These runners use their
  explicit settle-then-clock sequence; they do not establish Host single-eval
  scheduling or the original eight-way service contract.
- `idma/`: leaf C ABI bridge, direct trace runner, leaf ABI assertions, original
  adapter RTL frame endpoint and adapter ABI assertions. Prior finite evidence
  covered aligned copies of 1/2/63/64/65/96 bytes and the 1 KiB backpressure case,
  plus the original adapter's 64-byte read and two-beat/read-reuse sequences.
  This does not cover all channels, faults, live-debt resets or full Host traffic.
  The two ABI assertion `.cpp` files were compiler syntax-checked, not linked
  runtime units.

The bridges map the original generated ports to the existing transport ABI.
They do not replace the Matrix or iDMA arithmetic/transaction implementation.
The separate Scala source compilation and finite historical tests do not imply
a full Host numerical pass or final same-RTL replay.

## Checks in this commit

From the repository root:

```sh
python3 -I -B candidates/chisel_hybrid_host_20261106/native/check_source_only.py
python3 -I -B candidates/chisel_hybrid_host_20261106/native/test_source_only.py
python3 -I -B -O candidates/chisel_hybrid_host_20261106/native/test_source_only.py
```

These checks verify the sixteen source identities, complete local source set,
quoted include order and declared external header names. Negative tests reject
changed identities, missing/duplicate sources, changed include order, omitted
external dependencies and path escapes. They do not compile C/C++, parse model
semantics, validate a new ABI binary, execute a trace or load a native library.
The existing CI also recompiles its unchanged Scala selection. That result is
Scala compilation only, not a fresh native build.

## Portable native build recipe: pending

The following headers are intentionally absent:

- `Vqwen2_matrix_command_endpoint.h`
- `Vtc_clk_gating.h`
- `Vidma_backend_rw_axi_flat_wrap.h`
- `VOriginalIdmaAdapterProbe.h`
- `verilated.h`

They must come from the matching original model generation and Verilator runtime.
The repository already contains the original iDMA wrapper RTL and original
provider/reconstruction sources. This directory does not package generated
providers or establish a complete relative build route for the adapter model.

A portable native recipe still needs a reviewed toolchain and source closure,
original provider/model generation, exact Verilator partition/options, generated
model/port checks, compiler/linker flags, library dependencies and rpath policy.
The passive observation helper additionally depends on Linux `/proc`, process
identity and file-map behavior. Its output needs an owning verifier; reading
maps alone is not a runtime-provenance acceptance.

Generated RTL/FIR/AST and Verilator output, binaries, vectors, tensors, weights,
references, local owner plans/receipts, Python drivers with local imports and
unrun witness drafts are excluded. Runtime gates and shared-resource holds remain
separate from this source-preservation batch.
