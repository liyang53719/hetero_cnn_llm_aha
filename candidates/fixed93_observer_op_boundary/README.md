# Fixed93 no-evidence operation callback policy

This small overlay changes one observer branch. It is not a model, a full-block
runner or execution admission. Apply only to the exact baseline hash in
SOURCE_PINS.json. The original full identity implementation, numerical source,
shared dispatcher and other observer remain unchanged.

POLICY.json and OBSERVATION_CONTRACT.md specify the deliberate integrity sampling
change: normal `_op` call/return callbacks with no direct `_attention` caller have
no evidence consumer, so retain code/thread/owner checks but skip the full
ABI/profile inventory check. Exceptions and all evidence-producing routes retain
original checks. A transient mutation restored between these omitted checks is
not guaranteed detected. This is a new contract, not old anti-tamper equivalence.

Run the synthetic check using Python 3.12 with the pinned baseline checkout:

    python -I -S -B tests.py --baseline /path/to/pinned/baseline

The test limits itself to one CPU, 15 CPU seconds and 256 MiB address space. It
executes exact compiled observer/dispatcher code against synthetic fixtures, not
DUT arithmetic. It rejects native/process/network/DUT-import attempts. The real
whole-block callback runs only for MOCK public/support descriptors; a separate
test-only listener counts `_op` events. It does not claim that production
whole-block anchors observe `_op`.

Author outcome: natural exit 0, 0.165 s wall, 22,468 KiB peak RSS. Raw bytes stayed
pinned. Previous wrapper exit127 (missing optional timing executable, test never
started) and fixture argument-name TypeError are retained separately; the final
fix changed only the test helper parameter name. No failed record is relabeled.

Independent same-ctypes synthetic timing measured active-dispatcher normal
call+return pair median 164.979 us old versus 9.000 us new, about 18.33x. This is
not a full-run forecast: no real arithmetic, arrays, codec, I/O, prefix or tail
was timed, and per-line identity checks remain. The current full candidate is not
authorized to run by this bundle. A separate source-bound policy integration,
limited real M2 calibration and new root admission remain pending.

Public scope: source, patch, relative pins, policy, synthetic test and safe
summary only. Do not publish author raw logs, machine paths, payloads or run
permissions. Existing failed/unknown runs and their evidence remain untouched.
