# Uniform failed-native context, SOURCE only

Every failed call_phase child now attempts the same bounded, finite-redacted native.log context collection. All 34 full-job and 16 build-only stages are covered, including acquisition, Python preparation, Java/FIRRTL, Verilator/C++, and short execution. No phase whitelist is introduced.

Prior run 39195434991 completed tool build and tiny qualification, then Host class compilation, and failed CHIRRTL with native exit 1 after 14.112065 seconds, timeout false and cleanup true. Its original three JSON files contain no CHIRRTL log context. The cause remains unknown; this candidate adds observation. Original evidence and validators are preserved.

The existing collector reads only the fixed native.log last at most 1 MiB after supervision. It retains a consecutive suffix of at most 80 lines, at most 512 visible ASCII characters each, within the existing 16 KiB canonical diagnostics-object limit. The original finite path, URL, credential, auth-header, long-token and private-key redactions and control escaping are unchanged. This bounded fixed-source job loads no weights. Perfect generic secret removal is not claimed. Environment values and private traceback files are never directly collected.

Failed stages require AVAILABLE, READ_ERROR (including missing log), or SANITIZER_ERROR. Successful phases retain NOT_COLLECTED, including when a later component postflight rejects. Existing native exit, timeout, cleanup and safe summary contract labels remain unchanged. stage-exits advances to v4; summary-v3 and source-hashes-v2 remain unchanged. Old v3 evidence requires its original pinned validator.

Only run.py and raw-byte-bound test_run_cold.py change. Commands, cwd, JVM limits, resource budgets, shared 6600-second deadline, phase order/count, source pin chain, sanitizer and original supervisor are unchanged. A static historical comparison found no blocking JVM argv or limit mismatch. Java installation, cwd, locale, permissions and fresh class differences do not establish a cause.

Final normal and -O cold suites each pass: coordinator 101; toolchain 118; header 26; transport 7; support 41; regressions 7; sanitizer 463 structured plus 727 context checks. These are source/synthetic checks, not actual native qualifications. Earlier missing --repo invocation errors and the v4 fixture migration are documented separately.

New actual: NOT_EXECUTED. Independent SOURCE review is GO for this context-only delta. Parent exclusively owns publication and the next authorized actual.

Frozen SOURCE manifest: 7100 bytes / 564f7f266fe454aa0d78ae2720c733d1170147b09efbbf16a64f8cbf9ea9af92.
Independent SOURCE GO: review_ci_all_stage_context_source_20261019T0353; MANIFEST 1119 B / 828226c4965ec6032700cca6104b7d5109c829ca94afd9b6f3ef5dc53e54f0ca; SUMMARY 3054 B / 517b26c29bf5d0a1ee4a6e8b0d9a87e946fef724d6ddd58413461330f85478e7. Verdict: SOURCE_GO_UNIFORM_BOUNDED_FAILED_STAGE_CONTEXT_ONLY.
