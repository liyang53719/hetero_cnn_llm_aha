# New portable Host execution component

TEMP_SOURCE only. This candidate is a new identity after rollback. No old execution, generated ABI, protected-library suffix, linker forwarder, runtime-handle result, or review is inherited. The frozen 4VLT candidate is unchanged.

## Coordinator interface

`run(repo, work, call_phase, toolchain, host_emission, idma, retained, configuration)`

All roots are absolute, whitespace-free CI paths. `work` must not exist and must be disjoint from the repository, candidate, toolchain, and all input roots. `idma/sources/` is the fresh 319-file source export; `retained/source/` is the fresh 13-file retained RTL output; `configuration/` contains exactly the four VLT files and their manifest.

`toolchain` supplies `backend={path,bytes,sha256,mode}`, `verilator_root`, `host_programs` keyed by invoked paths and storing resolved executable identities, and `configured_runtime={path,bytes,sha256}` referencing its same-job include/wrapper inventory. `host_emission` supplies fresh `fir` and `sv` identities. No prior local review path is consulted.

The only native execution entry is the caller's `call_phase(name, argv, cwd, environment, limits)`, returning `record={exit_code,cleanup_confirmed}`, `raw_log` bytes, `usage`, and `evidence_root`. A nonzero exit or unconfirmed cleanup fails. Exceptions propagate after bounded private failure evidence is attempted. The parent owns the shared 6600-second deadline, process-tree supervision, one-CPU affinity, and preflight MemAvailable >= 8 GiB / free disk >= 3 GiB admission checks. There are no direct subprocess or network calls in this component.

The three fixed phases are:

1. `host93_cpp_generate`: 600-second total, 540-second work/CPU, 6 GiB AS, 128 MiB file limit, 512 MiB soft output-tree acceptance, 4 MiB log.
2. `host93_cpp_compile`: 1800-second total, 1740-second work/CPU, 6 GiB AS, 512 MiB file limit, 2 GiB soft output-tree acceptance, 4 MiB log.
3. `host93_reset_launch`: 30-second total, 10-second work/CPU, 2 GiB AS, 8 MiB new-write file limit, 1 MiB log. Existing build artifacts are still inventoried up to the prior 512 MiB per-file / 2 GiB tree caps; the 8 MiB runtime write limit does not invalidate an already-built larger executable.

The limits dictionary includes the requested total/work/CPU/AS/file/log/sample keys plus tree/file-count/entry-count acceptance bounds. Trees are inventoried after each phase, including failure when safely possible. Tree limits are acceptance/observer soft limits, not a claimed filesystem quota.

## Build contract

The ordered compilation list has exactly 307 sources: the original 294 iDMA filelist, excluding only `deps/axi_stream/src/axi_stream_cut.sv` and `deps/axi_stream/src/axi_stream_multicut.sv`, followed by the 13 pinned retained sources, the pinned clock implementation, and the fresh same-SV Host output. There are exactly eight include directories and four fixed target defines.

Generation uses the new same-job backend with --cc, --hierarchical, --exe, HostBlockTop/VHostBlockTop, one thread/build/verilation job, parenthesis limit 16, split 3000/200, --no-std, --relative-includes, and 1ns/1ps. It does not pass --build or -Wno-fatal. Compilation is a later supervised make phase. The newly generated top makefile must include its newly generated hierarchy makefile, whose library graph names the new child archive. No old archive or forwarder is supplied.

Before compilation, finite checks inspect only newly generated files: actual child hierarchy arguments determine its specialized endpoint name; the actual wrapper container must contain its sole scoped constructor with `m_seqnum{0}`; the top generated root header must declare eight separate protected chandle-storage members for leaves_0 through leaves_7; and the new public top header must expose exactly the 83 known port names, directions, and widths. The chandle-storage check is a generated-declaration witness, not a measurement of eight live runtime handles. It deliberately fails closed on an unknown generated layout. It does not require registered VerilatedScope objects, which protected-library imports need not generate.

Generated C++/header/make/argument/SV configuration source files are frozen after generation and checked unchanged before and after subsequent phases. Input RTL/configuration trees, fixed repository source inputs, the new FIR/SV, backend, host tools and configured runtime are checked again around each phase. The ELF is hashed before and after the short run and must retain the same identity.

## Short consumer boundary

`short_launch.cpp` uses only the new `VHostBlockTop.h`, the configured Verilator runtime, and the pinned original `canonical_launch.hpp`. All 39 Host input ports are initialized explicitly. AXI response valid/data and request ready inputs remain zero. It drives four real reset high edges and four released-reset high edges, applies the fixed canonical M128 launch payload, and waits at most 16 further high edges. It stops immediately after the first real high edge whose preceding settled low state had launch valid && ready, with no subsequent eval or final call. Ordinary C++ destruction follows.

Only three exact markers qualify: reset edges completed, one launch handshake completed, and the limited short-pass marker. There is no RAM model, payload loading, weight loading, memory response, N0 numerical claim, block-completion claim, generated-ABI compatibility claim, or eight-live-handle claim.

## Source validation and loading

Use Python -I -S -B before loading any project source. SOURCE_PINS.json binds the fixed filesystem support, lexical helper, host port contract, canonical launch payload, retained13 plan, and new C++ source. The component itself must be loaded by exact size/SHA verification followed by compile of those same bytes, as recorded in ENTRY.json. A direct script invocation is rejected.

`python -I -S -B test_cold.py --repo ABSOLUTE_REPO` and the same with `-O` run source/tiny mocks only. The tests read a few pinned small source files, construct tiny synthetic generated headers/wrappers/makefiles, and use a fake three-phase callback. They do not execute a generated program, invoke a compiler, access the network, read real large SV, or generate actual Host C++.
