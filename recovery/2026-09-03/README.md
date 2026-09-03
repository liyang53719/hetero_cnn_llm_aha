# Recovered Chisel artifacts — UNTESTED

**Status: `RECOVERED_UNTESTED`.**

These artifacts were recovered from prior sandbox/session residue after the original temporary workspace was reclaimed. They are preserved only for provenance and loss prevention.

No Chisel compile, elaboration, emitted-RTL simulation, numerical regression, or Design Compiler run was re-executed for these recovered copies in the current environment. Do not use the presence of these files as evidence of functional, performance, numerical, or timing closure.

Contents:

- `recovered_operator_primitives_raw_20260903.tar.gz`: five recovered original/merged Scala artifacts: `HeteroOperatorPrimitiveCommon.scala`, `HeteroModelBlockPrimitives.scala`, `HeteroQsaPleVisionPrimitives.scala`, `HeteroGdnMoePrimitives.scala`, and `EmitHeteroModelOperatorPrimitives.scala`.
- `split_snapshot/`: seven recovered split Scala snapshots corresponding to the reconstruction path used for the active `integration/gemmini/*.scala` candidates.
- `MANIFEST.json`: byte counts, SHA-256 provenance, archive contents, and explicit `RECOVERED_UNTESTED` status.

Three independent base64 backups survived for `HeteroOperatorPrimitiveCommon.scala`, `HeteroModelBlockPrimitives.scala`, and `HeteroQsaPleVisionPrimitives.scala`; they decode byte-for-byte to the recovered raw originals. The redundant base64 wrappers are intentionally not committed.

The active `integration/gemmini/*.scala` sources remain separate from this recovery directory. They should also be treated as **not re-tested in the current sandbox** until the local-agent Chisel/Gemmini build and regression gates are rerun.