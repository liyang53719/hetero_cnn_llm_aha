# Lightweight source and synthetic controls

Status at handoff: prepared but NOT EXECUTED. No Python test invocation, Scala compilation, RTL generation, native code, model construction, tensor/weight read, actual handshake, or active Qwen2 candidate access was performed to prepare these files.

## Review and execution boundary

Only after the parent completes source/test review, run this exact target-runtime command:

    /opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python -I -S -B tests.py --base-source <fixed-commit-checkout>/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala --overlay overlay/GdnInputPrepOwner.scala

Run from this package directory and provide both source paths explicitly. No private checkout path or local HEAD is assumed. Raw input size/SHA is checked before source text inspection. The harness refuses another executable, any version except CPython 3.12.14, source bytes that do not match the fixed pins, or missing isolation/no-site/no-bytecode flags. It uses only standard-library modules, one process pinned to one available CPU, no worker threads, and no subprocess or network calls. It caps address space at 256 MiB, limits CPU to 4 seconds soft / 5 seconds hard, and checks a 4.5-second cooperative wall deadline. No large matrices or frameworks are involved. An external watchdog may additionally bound wall time when execution is eventually authorized. Stdout is one JSON result; individual unittest details go to stderr.

Read set is restricted to the pinned baseline Scala file, this candidate's CONTRACT.md, overlay/GdnInputPrepOwner.scala, and GdnInputPrepOwner.patch. No generated files or application state are written by the tests. The parent owns permission to execute; preparing this harness is not that execution permission.

## What is checked

- Exact baseline (13,048 B / 86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe), overlay (15,119 B / 863801ca0ea2d33ef767bc70061ffa62e9cc83dff2cc2d4f18ba2bb71398181d), and contract (5,455 B / e4ac02b4410d65d4bc3954787c4e15ae1fcb2e4fcbaf7ff88d98c0ac95f34db7) pins.
- Full-file equality to an explicit reviewed literal edit recipe, plus exact unified diff. Every byte outside documentation, constructor limit, token register/initialization, address offsets, packed admission, and final-gate token transition is thereby preserved. Independent exact block comparisons name Bundle/enums, scalar requests/results/arithmetic and numerical rejection, memory request/response failure paths, gates' zero padding, original M1 span/overlap checks, and terminal/lock behavior.
- Default maxTokens=1 rejects M2. M1 separated pointers, read/read alias allowance, small heads, and both recurrentMode values retain the original integer admission and address formulas. M>1 is accepted only for 16 heads, exact packed relations and recurrentMode=false; tokens 0/129, over-limit tokens, bad offsets, wrong heads, and wrapped pointers are rejected.
- Complete Conv/AB/ALog/dtBias/Prep allocations: wide mathematical bounds, 64-byte alignment, endpoint equality, and Prep-versus-read alias rejection. Negative cases include token-0 output destroying a later Conv token, later AB alias, and later Prep alias. Read/read overlap is intentionally not forbidden. Tests do not multiply old per-role spans to stand in for packed allocations.
- Exhaustive synthetic beat addresses for M=2/16/128. Every Conv read beat and Prep write beat has unique logical coordinates and exact complete byte coverage. Parameter order is AB/ALog/dtBias for every token; AB advances by 64 B, ALog/dtBias remain fixed. First/final accesses, including token 127, stay inside the checked allocations.
- Synthetic control events only: stalls do not advance token/counters, only a matching error-free final-head gate ACK advances token or completes, wrong tag/error does not count success, terminal holds under done backpressure, and failed completion locks. Per-token locals reset while sequence/bytes/cycles accumulate. At most 128 gate-boundary events are exercised per case; there is no full 76k-event handshake simulation. Pre-boundary sequence/byte values are explicit specification inputs, not hardware observations. M128 ends at token 127 without a narrow-counter wrap.
- H16 synthetic totals: 195 reads + 400 writes = 595 memory transactions per token. M128: 24,960 reads, 51,200 writes, 76,160 acknowledged transactions, 3,276,800 output bytes. These are InputPrep-only counts, not full-block denominators. Synthetic cycles only count the oracle's calls, not hardware cycle latency.

## What a passing result would NOT establish

The Python admission and event classes are specification oracles, not a Scala interpreter or a real owner testbench. Source pinning and literal inspection do not validate Chisel elaboration/type widths, synthesized timing, scalar floating-point outputs, transport behavior, real stalls/handshakes, resource mapping, or throughput. No public Command128, chunk64, complete prefill, later blocks, RTL, or 80%/90% utilization claim follows.

Real owner/RTL qualification still needs original scalar/memory fire traces, full intermediate Q/K/V/g/beta outputs, stall/error/terminal tests, joint reset/drain behavior, M1 regression, and cross-token sentinels. This preparation performs none of those. A changed overlay must be independently reviewed, then its pin and exact edit recipe updated; the harness never learns an expected result from the candidate automatically.
