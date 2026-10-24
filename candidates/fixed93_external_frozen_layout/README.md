# Read-only external frozen-input routing

This small source overlay preserves the real assembly preflight and runtime
reference boundary while separating stable logical names from physical frozen
input locations. It does not grant actual execution authority.

## Included scope

Six Python sources: one resolver plus the existing assembly preflight, admission,
recipe, OracleGate and runner routing edits. The patch applies to the exact
predecessor pins in SOURCE_BASE_PINS.json. No weights, reference tensors, runtime
ELF, generated private-path manifests, or old run outputs belong in this bundle.

The external declaration must be separately pinned by the new assembly manifest.
It lists exactly the original 76 files and two absolute canonical roots. Files
must be regular, nlink=1 and unaliased. Stable logical keys remain unchanged.
Reads use one FD for data, hash and before/after identity verification; roots and
all named files are checked across the batch. Unknown paths are not admitted by
root prefix. Reference payloads are stat-only before the original postseal gate.

The permanent Python audit guard denies writes/mutations affecting either frozen
root, including ancestor mutations, links, relative write-open and dir_fd cases.
It is not a native/OS sandbox and cannot protect arbitrary native syscalls or
preexisting writable descriptors. Output still belongs only to the new assembly.

The loader compiles the pinned resolver bytes directly, ignoring bytecode caches.
It rejects foreign module reuse and snapshots code, globals, class members and
copied defaults/kwdefaults; current source functions must remain closure-free.
This is a bounded module identity check, not a transitive standard-library proof.

## Synthetic checks

Run each command once with a new absolute output directory:

    python -I -S -B tests/resolver_controls.py --output /absolute/new/resolver-test
    python -I -S -B tests/routing_controls.py --output /absolute/new/routing-test

The resolver batch has 14 groups. The routing batch has five groups and exercises
the raw loader plus original recipe/path/OracleGate CodeTypes with explicitly
synthetic state. It does not run the real OracleGate constructor, recipe module
top level, DUT, native library, model, or real-input preflight. Failed earlier
test harness evidence remains separate; only the current bounded results apply.
The routing batch specifically verifies preseal reference rejection and the
unchanged original seal predicates, not actual producer/schedule acceptance.

## Real preflight remains a separate action

The strong preflight still checks 321 assembly entries, all preparation pins,
1,638 runtime files, 46 frozen-file hashes and 30 reference-payload stats.
Before this overlay the source estimate was 851,576,080 hashed/read bytes, with
652,445,376 runtime bytes and 189,998,063 frozen-file bytes. The new small source
and metadata delta must be added after assembly; reference bytes remain unread.
A proposed 120-second, one-CPU, 256-MiB source-only process cap is not a measured
performance result. No new assembly, real preflight, native task or M128 result
is implied by these synthetic checks. Materialization and admission are separate.
