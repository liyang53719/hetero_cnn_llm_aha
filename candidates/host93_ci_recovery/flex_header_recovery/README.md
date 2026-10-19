# Pinned FlexLexer.h recovery source

Status: SOURCE_GO_FIXED_FLEX_HEADER_SAME_JOB_HOST_RECOVERY_ONLY. Independent SOURCE review is complete. No new network acquisition, native header compilation, tool build, or Host actual has run from this candidate.

## Observed gap

Run 39191780530 reached flex 2.6.4 generation, then naturally failed make with exit 2: V3ParseLex.cpp:30 included generated V3Lexer_pregen.yy.cpp:369, which could not find FlexLexer.h. The receipt reports no timeout and confirmed cleanup. This identifies only that run's failure; the two earlier failures retain their original evidence and unestablished causes. Parent baseline is c00255a68fcc3eab80b6038e9dfd764d4e22ab87.

The historical five-package inventory selected usr/include/FlexLexer.h (6,893 bytes), but the current CI component does not materialize that staging tree. Its configure command also explicitly cleared CPPFLAGS. This successor supplies the missing selected header and wires its include directory into configure.

## Small runtime change

1. After the ten existing host-tool qualification probes, flex_header_acquire fetches only the fixed 85,600-byte Debian libfl-dev package. The original package/member pins and pure validate_package parser validate the same retained bytes, including ar framing, control identity, bounded data expansion, full member table, and the exact single selected header. The old unbound five-package staging entry is never called. There is no package installation, downloaded-code execution, or whole toolchain reinstall.
2. flex_header_compile invokes /usr/bin/g++ with the clean native environment and the one staged include path. It really compiles a C++ source that includes FlexLexer.h and requires complete FlexLexer/yyFlexLexer types. A nonempty object and an exact MMD dependency witness are required. Nothing is linked or executed by this probe.
3. Configure receives that identical explicit CPPFLAGS=-I path. A finite src/Makefile_obj substitution witness must preserve it before make; the header hash/mode is checked before and after each build phase.

Acquisition uses existing platform proxy/CA only in the networking phase, one HTTPS URL, no redirects, no retries, no direct-network fallback, at most 85,601 response bytes, and a 90-second inner deadline. The original supervisor enforces 120 total/90 work seconds, CPU 40 seconds, AS 512 MiB, FSIZE 4 MiB, and log 64 KiB. The compile probe is 30 total/10 work and CPU seconds with the same memory/file/log caps. Both consume the original shared 6,600-second job budget. All original phase caps, process cleanup, WNOWAIT semantics, and evidence contracts remain unchanged.

Default full mode now has 34 stages: successful header probe/build/tiny continues in the same job through the existing finite Host generation and short reset-launch. Build-only mode has 16 stages and stops after fresh_make. Every first failure stops subsequent work. A passing probe would establish only this small real header compilation; full build and Host outcomes still require their own successful actual stages.

## Evidence and cold checks

SOURCE_PLAN.json records the fixed package/member identities, contracts, budgets, and modes. RUN_PINS.json and toolchain/SOURCE_PINS.json bind the production chain. COLD_RESULT.json distinguishes synthetic checks from future actuals. The frozen SOURCE manifest is 6,046 bytes, SHA-256 8f7a33a6b8a76a62e0455af44b9d34cea79bd98a63cd14d931d1ef252b5a717b. Normal and optimized Python runs both pass: coordinator 82, toolchain 58, single-header acquisition 26, transport 7, support 41, support regressions 7, and sanitizer 463 structured + 727 context checks. All effects in these tests are mocked; no real header was acquired or compiled. One initial support-suite invocation omitted required --repo and exited 2; its private log is retained, and the corrected complete dual-mode runs pass with unchanged source.

The existing bounded sanitized compiler-log tail remains unchanged. Its finite clean-public-build redaction contract does not guarantee perfect removal of arbitrary secrets. Only the already constrained three evidence JSON files are publishable from a future actual. Raw logs, package bytes, local inventories, and generated tool/Host output stay private.

Parent owns source review acceptance, publication, the one Host-workflow trigger, and actual execution. The build-only workflow is not changed. This SOURCE checkpoint supplies no actual PASS, numeric inference, or weights-loaded claim.

SOURCE review: SOURCE_GO_FIXED_FLEX_HEADER_SAME_JOB_HOST_RECOVERY_ONLY; review manifest 1999 bytes / 44303c275d27457eff82fd5f99191553d54aadcb3cd528355d17f22ad0dd8476; summary 5092 bytes / 87ddb3dfc2e5e39f3eb645639a4e6470c67ee5754e3dc193e3d0d87f23b8d42e. This is SOURCE acceptance only; new actual remains NOT_EXECUTED.
