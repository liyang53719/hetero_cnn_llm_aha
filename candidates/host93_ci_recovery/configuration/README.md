# Relocatable Host 4VLT source candidate, 2026-10-19

Status: TEMP_SOURCE. This is a newly rebuilt source identity after workspace rollback. No prior review or execution result is inherited. Independent cold review is required before actual configuration generation in CI.

## Scope

The generator accepts exactly `--repo ABSOLUTE_REPO --sv ABSOLUTE_SAME_SV --idma-root ABSOLUTE_EXTRACTED_IDMA_EXPORT --out ABSOLUTE_FRESH_OUTPUT`. All four switches are required. It writes only four VLT configuration files and a manifest to a new directory outside the input/repository/candidate trees. No download, native tool, shell process, generated C++, runtime, model, full SV checker, or production chain change is performed.

Read `ENTRY.json` for the exact isolated same-buffer launcher. Replace its source argument with the installed generator path and append the four CLI arguments. Do not execute the generator as a normal script or import it from a search path. The `-I -S -B` flags are mandatory, and `-O` is safe. The launcher verifies regular-file type, exact byte length, SHA-256, descriptor/path identity, and no symlink components before compiling exactly the verified buffer. It gives the generator the verified source identity.

The generator reads five pinned repository data inputs, not executable repository code. Their exact bytes are enforced independently of the checkout location or commit. The repository audit context is commit `18e757084e4812fe2496ba8321438a468e17b646`; later source-only publication commits can contain the same pinned inputs without changing this contract. The SV must be the fresh same-SV CI output: 76,366,612 bytes and SHA-256 `2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61`. The iDMA root is the export root containing `SHA256SUMS.json`, `SOURCE_CLOSURE.json`, `idma/`, and `deps/`, not its parent extraction directory. Both metadata files and all six WIDTH-warning source files are verified before output.

## Four outputs

- `hierarchy.vlt`: exactly one `hier_block`, naming `qwen2_matrix_command_endpoint`.
- `readonly.vlt`: exactly 610 exact `public_flat_rd -module ... -var ...` directives. No wildcard, global visibility flag, or read-write access is generated. The union is 468 binding members, then 546 after the 81 N0 members, then 601 after the 75 contract taps, then 610 after nine MatrixPipelineService fields. Overlapping fields must agree in width.
- `dma_hints.vlt`: the 591 original full-profile bytes, SHA-256 `476e42bac40bd8eb43423cb898339300be4c1ff88dfc77ef9ae5d539cc318aca`. Five `isolate_assignments` directives have no effect in Verilator 5.053; three `split_var` directives have supported grammar. Neither statement establishes an optimization result.
- `precision_warnings.vlt`: exactly 21 unique WIDTH rule/file/line directives from the 24-row original warning inventory. The sole PINMISSING row is never suppressed. Duplicate diagnostic columns collapse only when rule, source path, line, and source SHA agree. Paths are rebound to the supplied iDMA export root; no old workspace path enters the output.

`MANIFEST.json` is written last after the four VLT files, with each file read back before success. It records declarations, source origins, input hashes, output hashes, and explicit non-qualification boundaries. A failed write may leave an incomplete fresh directory; never reuse it.

## Narrow declaration check

This source deliberately does not implement a general SystemVerilog parser. It recognizes the already observed emitted forms: `module Name(`, ANSI input/output declarations with literal descending `[N:0]` ranges and one declarator per line, comma continuation inheriting width, wire/reg declarations with optional initialization, and unparameterized selected hierarchy instance headers. Comments and quoted text cannot supply declarations. It validates all 610 widths and the 14 required selected hierarchy edges across 15 module definitions, and rejects missing/duplicate declarations, missing/duplicate/unknown selected edges, and unsupported requested declaration shapes. Unknown source bytes are rejected by the whole-SV pin before scanning. Unrelated behavior, syntax, and sibling hierarchy are outside this declaration check and remain the responsibility of the separate same-SV qualification gate.

## Tiny validation

Run `python -I -S -B test_tiny.py --repo ABSOLUTE_REPO` and again with `-O`. The test script loads the generator from an exact SHA-checked buffer, reads only the five small pinned repository data inputs, and uses a synthetic sub-40-KiB declaration fixture. It never reads the real SV or runs actual generation. Tests cover field-set derivation, overlap, malformed/extra inputs, widths, missing and duplicate declarations, hierarchy mutations, ANSI continuation, comment/string decoys, warning deduplication and source agreement, scoped rendering, symlink rejection, fresh outputs, readback, and unsafe paths.

No claim is made about current generated ABI compatibility, eight retained handles, native build success, optimization effectiveness, numerical behavior, or runtime correctness. These are separate future gates.
