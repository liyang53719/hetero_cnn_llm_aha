# Portable verification

Run from any working directory, pointing at the extracted package:

    python3 candidate_attention_frame_routing_public_20261021T0634/check_portable.py

The default mode checks the exact relative file inventory, file lengths and
SHA-256 hashes, then compiles every Python file in memory. It does not import or
execute candidate or test code, write bytecode, read baseline inputs, run tests,
load models, call native code, or access the network. Python 3.10 or later is
recommended. The manifest does not authenticate itself; supply its separately
trusted SHA-256 with `--manifest-sha256 SHA256` for an external trust anchor.

`README.md`, `POLICY.json`, both overlays, both patches and both test programs
are exact frozen bytes. The original README describes source provenance and
validation boundaries, not the portable entry point. Use this file for portable
commands. All operational input names in the portable manifest are relative.
The two baseline files are deliberately not distributed in this excerpt.

## Optional fresh synthetic test preparation

This is not required for default verification. It creates a previously
nonexistent stage outside this package and never runs a behavioral test:

    python3 candidate_attention_frame_routing_public_20261021T0634/check_portable.py --prepare-tests fresh_synthetic_stage

The stage contains exact `tests.py`, `generator_controls.py`, both overlay files
and a newly generated `SOURCE_MANIFEST.json`. It does not copy baseline files.
The new manifest is marked synthetic restaging only; it is not the original
frozen source manifest or a receipt/admission. Its file keys are relative and
the external input pins are `baseline/cached_wholeblock.py` and
`baseline/narrow_fullblock_attention.py`. The checker prints the new manifest's
SHA-256, for use with the supplemental program.

If separately authorized to run synthetic tests, provide a baseline directory
containing the exact two files whose hashes and sizes are in
`MANIFEST.json:test_inputs`. The frozen test CLIs accept that directory explicitly:

    python3 fresh_synthetic_stage/tests.py --baseline BASELINE_DIRECTORY
    python3 fresh_synthetic_stage/generator_controls.py --baseline BASELINE_DIRECTORY --manifest-sha256 STAGE_MANIFEST_SHA256

Replace the uppercase placeholders with the baseline directory and the stage
manifest SHA-256 printed by preparation. The tests pin baseline contents before
source compilation. New runs are new synthetic evidence, not replacements for
the original cold records. None of these commands authorizes an actual model
run. Packaging did not rerun the behavioral tests.
