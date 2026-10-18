# Host93 single-SV generation reproduction template

This is a source-only, explicitly unbound template for converting the fixed Host93 CHIRRTL to one SystemVerilog file. It includes no FIR, SV, binary, logs, absolute machine paths or system inventory. The reviewed execution logic is unchanged: only its fixed plan SHA differs. The cold entrypoint changes only its matching raw-source SHA. SOURCE_DELTA and SOURCE_PROVENANCE identify the exact projection.

## Source checks and local binding

Use INSTALL_MAP.json for all project-relative dependencies and direct `python -I -S -B` cold/preflight commands, with the cold tests repeated under `-O`. The source and helper loaders verify fixed raw bytes before compile/exec; no project bytecode/importlib route is introduced. The listed class-stage descriptors are read solely to reproduce the already-reviewed supervisor projection; no class compilation, Java, JAR loading or elaboration occurs.

The template cannot be used directly to start firtool. Machine-specific FIR/review paths and new firtool acquisition receipt/review slots are explicit PENDING. The official member SHA and its known25,009,456-byte size, same42,417,256-byte FIR SHA, structure-review provenance and budgets remain fixed. The firtool actual precondition refuses before creating the real output directory.

BINDING_REQUIREMENTS.json describes the required separate local successor: verify the exact same FIR, acquire and independently review the official member, bind new local original receipts/review identities and paths, recompute plan/source/cold pins, cold-test and freeze for independent SOURCE review. Rebinding does not grant permission to change tool/FIR identity, flags or limits. A different local structure-review record likewise needs a real same-FIR review and reviewed identity update; no copied claim is sufficient.

## Fixed native stage

After separate authorization and binding, the gate creates fresh private FIR and tool snapshots, retains the original tool0600 and sets only the new snapshot0700. It runs fixed firtool1.62.1 once with -format=fir, a single HostBlockCollection.sv output, unprocessed-annotation warnings, an optional circt.anno.json and the original --preserve-values=all, -disable-all-randomization, --verbose-pass-executions flags. It does not elaborate Java again or require iDMA provider source or Verilator.

Budgets are180s total,10s preflight, tool at most150s and no later than entry+160s, original cleanup at most5s, all postflight/final writing before entry+180s. Native CPU affinity1, CPU limit150s, AS2GiB and FSIZE128MiB are child limits. Tree256MiB/log2MiB/annotation32MiB are postflight soft acceptance checks; finite inventory admits at most64 entries/32 files. The original WNOWAIT ownership, kill-before-reap cleanup, fixed leader PID/starttime one-second CPU/RSS/HWM sampling and whole-child RUSAGE metrics remain. The only lifecycle projection difference from the established calibration source is FSIZE48→128MiB; native AS is explicitly2GiB.

Original inputs and fresh snapshots are hashed before and after execution. Unknown output files, invalid input/review binding, timeout or resource failure retain the same attempt and do not retry. Output hashing explicitly excludes the inventory itself and final RESULT; independent actual review must inventory all final files. Every RESULT remains non-terminal evidence requiring original outer exit0, elapsed within180s, complete postflight and independent actual review.

## Claim boundary

This stage grants only real RTL generation and complete inventory. It leaves Host83 ports, Host-subtree resource counts and tap reverse-projection to a separate bounded read-only check of this same generated SV. It does not prove arithmetic, protocol behavior, C++tap bindings, simulation, Host execution or a numerical result. The new Host93 identity never inherits the lost historical95 or an old Kernel model identity. SAFE_HISTORY.json records the original actual stage outcome and its review state at the final source freeze.
