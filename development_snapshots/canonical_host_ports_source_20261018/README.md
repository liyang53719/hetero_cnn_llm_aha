# Partial HostPins source v2

The C++ header is byte-identical to v1: 54 published input-zero assignments and eight direct result/hub reads. No launch, RAM, loader, generated-model substitute, native compile, or EDA is supplied.

V2 fixes only the cold-entry/source-identity issues:

1. The test entry reads `cold_check.py` once, checks its fixed SHA-256, and compiles/executes that same byte buffer using the published `test_recovery.py` pattern. It never imports this helper through sys.path or a source/bytecode loader.
2. Source provenance uses actual published commit `6bde92d43d2ea9a78e951c0062e133aecf8b091e`, tree `9f743cd7ff48b820ac65ce2bb15024864b37d4e9`, relative repository paths and checked Git blob identities. All seven upstream byte lengths/hashes and `host_ports.hpp` bytes are unchanged. The v1 commit/path association was incorrect for the newly published recovery snapshot.
3. Source location is supplied with `--repo`; no absolute host path is packaged. Each upstream byte hash remains mandatory.

Run from any directory, substituting actual paths:

    python -I -S -B /path/to/test_host_ports_source.py --repo /path/to/repository -v
    python -I -S -B -O /path/to/test_host_ports_source.py --repo /path/to/repository -v

The 13 prior source tests remain. Two new cases reject changed checker source and ignore a valid-timestamp poisoned `.pyc` beside authentic source. Normal and optimized modes are tested separately. These are source checks, not C++ template instantiation or actual generated-port ABI verification.

Metadata JSON remains exploratory source-derived evidence. It does not qualify the target resident/QKV-reduction/QK16 profile, permit Gate/Up DDR writes, recover stream framing, or complete Host launch. Initial exploratory imports also loaded NumPy through the original package initializer; no numeric owner/payload was run. The reusable metadata replay prototype remains excluded pending narrow-import review. Source recovery is not native qualification.

V1 is preserved unchanged. No repository files, published snapshots, thresholds or RTL were edited; no commit, push or upload was performed.
