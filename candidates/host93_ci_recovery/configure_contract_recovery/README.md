# CPPFLAGS substitution and safe contract diagnostics

Status: SOURCE_GO_FIXED_CPPFLAGS_AND_SAFE_CONTRACT_LABELS_ONLY. Independent SOURCE review is complete. New actual: NOT_EXECUTED. Parent: 89f8a9aa9378d341242dc0b0a03750070fba756f.

## Keep the actual boundary honest

Run 39193914902 preserved 15 native stages with exit 0 and confirmed cleanup, including the fixed header acquisition, real g++ header compile probe, autoconf, and configure. It ended INPUT_OR_CONTRACT before any fresh_make START. The published three JSON files do not identify the private postflight exception. This successor does not rewrite that result or assign it a specific failed gate. The earlier three failed runs are also preserved.

## Independently reproduced SOURCE defect

The pinned official configure.ac line 229 appends a space to CPPFLAGS. Its lines 275–289 can also append an include directory beside the selected flex executable. The old witness demanded exact equality with a no-trailing-space assignment and therefore rejected valid substitutions in Python-only counterexamples. This proves a SOURCE defect; the actual configured Makefile was not recovered. The pinned official Makefile_obj.in propagates CPPFLAGS through CPPFLAGSPARSER to parser compile recipes at lines 420, 423, 426, and 429.

The narrow replacement inspects only CPPFLAGS += assignments with ASCII space/tab tokenization. The exact staged -I must occur once in exactly one such assignment. Accepted values are that token alone, or that token followed by the one sibling include directory derived from the already verified selected flex realpath. The staged header remains first. Unknown flags, unrelated optional directories, duplicate tokens/assignments, reversed include order, controls, and the MSYSTEM -idirafter form are rejected. MSYSTEM is not forwarded into the existing clean native environment. This is a fixed Linux contract, not a general Make or shell parser. No make -n or new native phase is added.

## Safe failure evidence

summary.json advances to host93-ci-summary-v3 with the strict two-field contract_failure object: boundary and code. Both are fixed allowlisted constants. Build-loop header/source/configuration/HOME/ccache checks, phase postflight, required outputs, the CPPFLAGS witness, objcache witness, and private tree-receipt checks carry their precise fixed boundary. Known literal failures map to fixed codes; invalid JSON/encoding and missing fixed fields have constant codes. Arbitrary exception text, paths, arguments, and traceback never become public values. Uninstrumented older contracts explicitly report UNREPORTED / UNMAPPED_CONTRACT.

A postflight refusal leaves successful native stage rows as exit 0 and cleanup true. It does not fabricate a native failure. Raw exception traceback remains private. Only the existing three evidence JSON files are publishable. Historical summary-v2 evidence remains untouched and is validated with its original pinned validator.

## Bounds and validation

The fixed package/header bytes, real header compile probe, phase order, same-buffer pins, supervision/cleanup, and sanitizer are unchanged. Full mode remains 34 stages; build-only remains 16. Both retain the shared 6600 seconds and all existing resource caps. Full mode proceeds to the existing tool build/tiny and finite Host short reset-launch in the same job only after each earlier stage and contract succeeds.

Normal and -O cold reruns pass: coordinator 90, toolchain 118, header 26, transport 7, support 41, support regressions 7, and diagnostics 463 structured + 727 context checks per mode. Effects are synthetic. A separate fixed-template substitution proof shows the old rejection and new acceptance for trailing whitespace and the official Linux optional include, while preserving rejection of unsupported/reordered forms. No new network, native compilation, build, Host, numeric result, or weights-loaded result was executed for this source.

SOURCE_PLAN.json, DELTA.json, and COLD_RESULT.json record the finite scope and distinct evidence states. Parent alone owns publication, one Host-workflow trigger, and actual execution.

Frozen SOURCE manifest: 6029 bytes / d8695b6bc1cd54c724fb3f589e7cc068b0c787c3c1efe490bfee4f0c8a8a48e3. The preserved latest failure is recorded separately under development_snapshots/host93_ci_flex_header_failure_39193914902/.

SOURCE review: SOURCE_GO_FIXED_CPPFLAGS_AND_SAFE_CONTRACT_LABELS_ONLY. Review manifest: 2096 bytes / 07d6a2539856f5a1d037d2bec4751d9714b2b44ad51acb1372fe94d326f2c633; summary: 3108 bytes / cbdc2da60afb685bcb201e9a123a6a020c68335ac0dbe08a5768f27e4579063c. New actual remains NOT_EXECUTED; the prior actual precise gate remains UNKNOWN.
