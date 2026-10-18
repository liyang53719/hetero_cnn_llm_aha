# Host93 static CHIRRTL structure reproduction

This source-only package preserves the final reviewed v4 checker and bounded read-only wrapper byte-for-byte, together with their positive/negative synthetic tests. It includes no generated FIR, SystemVerilog, classes, JARs, runtime logs, local tool inventory or machine-specific argv. All four Python source files are exact copies; no unpublished earlier checker code is needed to run them.

## Run cold tests

From this directory, use the four commands in INSTALL_MAP.json. Run the Python scripts directly with `-I -S -B`, and repeat with `-O` as shown. The test entrypoints load fixed-SHA raw source bytes with compile/exec; they do not use project importlib or cached bytecode. The checker tests use synthetic fixtures, and wrapper tests use seven-byte buffers and mocks. The reviewed source candidates passed22 checker groups and14 wrapper tests in each mode; this projection is byte-identity checked, not another actual FIR check.

The source-only preflight command loads the fixed checker without reading FIR or setting process limits. Actual read-only checking requires the explicit execution flag, the exact pinned FIR, a new empty output location and separate approval. See INSTALL_MAP.json for the relative command template. Neither the checker nor wrapper reads EXPECTED_SHAPES.json or EXPECTED_SOURCE_EVIDENCE.json during execution; the expectations are embedded. Those sidecars preserve project-relative source evidence only. The historical HostBlockTop SV declaration is an ABI oracle, with no inherited model identity or qualification.

## Fixed scope and bounds

The checker verifies the common HostBlockCollection namespace with HostBlockTop plus four FMA siblings; exact83 public Host ports; required internal metadata reader/module paths;8 matrix endpoints,8 clock gates and1 external iDMA backend in the Host subtree;8 fixed metadata request/response routes; and9 declared observation bundles/2604 bits from3 tapped source files. Definition, whole-collection instance and Host-subtree instance counts are separate.

Metadata direct-driver checks project only a requested fixed leaf through equal declared bundle/vector schemas. Relative flip parity determines direction. The projected ground type and sink/source directions must match; a single unconditional driver is required. Ground connects do not reverse. Dynamic aliases, unknown related types, schema/flip/width mismatches, invalidates and duplicate or conditional overriding drivers reject. The typed-descriptor default payload mux is topology evidence only. No arbitrary expression evaluation or generic dataflow equivalence is attempted.

Input is capped48MiB, definitions768, expanded hierarchy paths20,000, hierarchy/expression depth128, type depth32, flattened leaves32,768 and line tokens262,144. Only the observed bounded inline DontTouch JSON framing is admitted. Unknown syntax rejects and preserves the same FIR.

Wrapper limits are total90s, preflight10s, check at most70s and no later than entry+80s, with all postflight and best-effort failure recording inside entry+90s. It fixes one CPU, RLIMIT_CPU80s, RLIMIT_AS1GiB, no core dump, per-report2MiB soft cap and RLIMIT_FSIZE2MiB. No child or native tool is launched. These limits do not guarantee completion. Whole-process CPU and peak RSS may include preflight/check/postflight; peak is not a difference. OS hard termination may prevent a report.

The wrapper verifies the exact checker source buffer before compile/exec and the exact FIR byte buffer before check_bytes. It rechecks original FIR size/SHA/file identity and checker SHA afterwards. Every success file is non-terminal evidence: original outer exit0, actual elapsed within90s and independent actual static-structure review are all still required. A leftover file alone is never success. There is no retry or regeneration.

## Preserved outcomes and claim boundary

SAFE_HISTORY.json retains both original INCOMPLETE attempts and the third observed internal PASS with outer exit0. The third actual independent review is intentionally PENDING in this frozen source projection. The earlier failures remain failures. The observed third-run counts are699 definitions/699 collection instances and690 Host instances; these scopes must not be conflated.

No arithmetic, numerical result, metadata protocol behavior, tap event semantics, C++ binding/tap survival, combinational acyclicity, RTL qualification, Host execution or full-block qualification is granted. This is the new Host-only93-source derivation, not a recovered historical95 identity. SOURCE_PROVENANCE.json binds the exact reviewed source and sidecars; MANIFEST.json describes only the files included here.
