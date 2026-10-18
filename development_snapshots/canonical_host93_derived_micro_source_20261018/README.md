# Derived Verilator tiny SOURCE gate

This is a 14-file, SOURCE-only snapshot. Every local actual binding is PENDING at freeze. It does not grant native execution or certify the large Host93 block. The same handwritten 938-byte SV and 4269-byte C++ fixtures exercise a parameterized protected leaf, TOP DPI exports and two independently scoped model handles.

## Install and cold inspection

Place the package at the suggested path in INSTALL_MAP.json. Three already published support Python files are required at the exact repository-relative paths and size/SHA pins listed there. They are referenced, not duplicated. No extra core-build PLAN is loaded by this gate.

Run the real cold entrypoints with an explicit absolute repository root:

    python3 -I -S -B test_micro_gate_cold.py --repo /absolute/repository
    python3 -I -S -B -O test_micro_gate_cold.py --repo /absolute/repository
    python3 -I -S -B test_init_contract.py
    python3 -I -S -B -O test_init_contract.py

The micro suite retains 62 bounded source/synthetic cases; the scoped initializer suite has 29. Both reject unsafe local loads through fixed byte length and SHA-256 before compiling the same checked buffer. Tests require -I -S -B before local project loading; -O does not remove any required check. The --repo option resolves only the three source dependencies for cold inspection. It never supplies actual tool/build or prior-stage evidence. There is no cold shell wrapper.

The loader also pins the runner buffer. A future executable identity successor must provide an outer launcher that pins this loader and records total wall/outer exit. Direct run_micro_gate.py is refused. With this package's untouched PLAN, --execute-reviewed fails at PENDING before loading support, enumerating source, creating output or launching processes. The default source-inspection loader path still points to /UNBOUND support files and therefore refuses until a reviewed local identity projection exists. Cold tests are the portable inspection entrypoint.

## What the gate checks

The four fixed phases are version, generate, compile and run. Generation itself invokes owned-group make, Perl and child Verilator processes. The respective total limits are 30/120/300/30 seconds; absolute work-stop offsets are 20/110/280/20 seconds, not a late-spawn allowance. Existing WNOWAIT cleanup and observer function bytes are reused. CPU/AS/FSIZE limits are per process/file; aggregate tree/log limits are postflight soft ceilings. Leader measurements are not subtree CPU/RSS, and RUSAGE_CHILDREN maxrss is a cumulative peak rather than a difference.

A real hierarchy requires the specialized child argument file, protected wrapper, top make inclusion, independent child generation and boundary calls. Compile acceptance additionally requires nonempty separate child and combined archives plus actual child compile/top-link evidence; an @-silent archiver need not echo. A future archive path alone proves no compiled library. TOP export routing and two-handle lifetime/state checks are separate evidence. Direct arbitrary leaf-memory DPI routing is outside scope.

The finite initialization contract checks the target class, long long field, constructor and unique m_seqnum{0} in the same exact known class body. It is not a general C++ parser or a blanket undefined-behavior clearance. The test negative is explicitly handwritten synthetic text. Actual old generated C++ is excluded from this package.

## Provenance and later binding

SOURCE_PROVENANCE.json records the official commit/tree and source pins, the separately derived source identity, and reviewed SOURCE provenance. SAFE_HISTORY.json preserves the original generation failure, readonly static comparison and uninitialized-state risk. Original failed generation native exit 0/outer exit 1 was never relabeled as success; readonly outer exit 0 did not authorize old compile/runtime. No old archive or object existed in that comparison.

All production functions and init_contract.py are byte-identical to the reviewed source basis; only constants, PLAN and raw pins are projected. Tests separately project repository resolution and replace the local actual negative with clearly synthetic text. SOURCE_INPUT_MANIFEST.json lists only independent fixed inputs to avoid a PLAN/runner/manifest cycle; MANIFEST.json covers the final full package.

Future use requires a new reviewed identity-only successor with exact source qualification, derived patch/build/binary/runtime/host identities and accepted prior-stage evidence. INSTALL_MAP.json lists those obligations. Public files contain no actual runtime inventories, machine paths, LOCAL argv/logs, generated artifacts or binaries.
