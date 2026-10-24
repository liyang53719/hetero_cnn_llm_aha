# Public startup probe source excerpt

This is a small source-and-summary distribution, not an executable candidate,
complete assembly package, review decision, admission, or actual result.
It does not replace the original complete source package whose manifest is
3561 bytes, SHA256 63c127f2727cfe541558db64c3535cf40613bd745d6150bca67aeb1d5a5797d0.

## Included unchanged

- prepare_probe.py, byte-for-byte the original portable builder.
- Twelve Python overlay files, byte-for-byte the original production/test source.
- PUBLIC_PINS.json, relative logical names and exact before/after identities for
  all fourteen original overlays, plus identities of omitted metadata.
- SUMMARY.md and a small public source/AST checker.

No original logs, payloads, weights, reference files, runtime binaries, actual
authorization documents, private machine roots, or original DELTA are included.
The original budget, prefix binding and overlay-pins documents are omitted
because they bind machine-specific paths. Their exact hashes are retained;
there is no template, path rewrite, hydration step or weakened identity gate.
Standard platform paths and the existing root-authority identifier in unchanged
source are protocol constants, not a disclosed private machine location.

## Builder boundary

The unchanged builder requires all of these explicit arguments:

python -I -S -B prepare_probe.py --predecessor BASE --package COMPLETE_SOURCE_PACKAGE --package-manifest-sha 63c127f2727cfe541558db64c3535cf40613bd745d6150bca67aeb1d5a5797d0 --output FRESH_OUTPUT

BASE, COMPLETE_SOURCE_PACKAGE and FRESH_OUTPUT are placeholders, not defaults.
BASE must match the fixed predecessor receipt, and COMPLETE_SOURCE_PACKAGE must
be the complete original package with every exact pinned file, including the
omitted metadata. This public directory cannot be passed as that package.
The builder only assembles bounded source/metadata, never preflight or actual.
Nothing in this distribution authorizes running even that preparation command.
Separate permissions and the original fail-closed gates continue to apply.

## Public check

check_public_sources.py takes explicit --package and --manifest-sha values.
It checks the relative public inventory, hashes, unchanged copied-file pins,
no private machine-root literals, and selected production AST structures.
It never imports or executes a production module, the builder, startup probe,
preflight, native code, Git, model jobs or advance calls. Its result is only a
public-source structural check, not the original 38-case internal cold result,
independent review, or an actual semantic PASS. The original internal synthetic
harness is intentionally omitted rather than advertised as self-contained.
