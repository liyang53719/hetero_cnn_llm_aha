# Bounded M128 v2: exact original Scalar initialization admission

Status: NOT_EXECUTED. A new independent parent go is required. Only the parent
starts the one fresh v2 model run. V1's entire 178-source closure, FREEZE.json,
failed RESULT, progress, and parent launch receipts remain unchanged.

V1 failed during tool_hashes_and_fresh_setup, before any producer or seal:
the new narrow native gate rejected the original ScalarService._check_environment
call to ctypes.CDLL(None). That call checks fegetround on the current process.
The unchanged constructor also executes five fixed NumPy signed-zero/subnormal
environment probes. The fix must retain that constructor inside the audit gate.

## Minimal new version

- gates.py inherits every v1 payload, native artifact, source, input, and oracle
  rule. It permits a current-process handle only once, before the output seal,
  from the exact original ScalarService.__init__ -> _check_environment ->
  ctypes.CDLL.__init__ call chain.
- Admission verifies pinned Scalar source bytes, source-compiled code equality,
  actual loaded method code-object identity, original module globals, exact
  constructor instance type, and pinned ctypes runtime source/code. A matching
  filename or method name alone does not grant permission.
- Current-process symbol lookup is restricted to that handle, fegetround, and
  the same source-bound original environment/constructor frames. Direct None
  loads, static environment calls, same-named substituted methods, and unknown
  file libraries remain denied.
- runner.py and launch.py are v1 entry copies with corrected subpackage root,
  v2 gate/entry imports, and explicit environment-audit receipt fields only.
  The unchanged v1 telemetry, driver, native ELF verification, arithmetic,
  observer, physical/Host identities, oracle gates, and numerical checks remain.
- A new source closure includes all 178 v1 sources plus only this v2 package.
  V1's FAILED result is not resumed or inherited.

## Real audit-hook control test

environment_probe.py --environment-only installs the actual sys.addaudithook
and constructs the original ScalarService. This is real numeric-module import
and five fixed primitive environment probes, not a stdlib-only or zero-floating-
point test. No model inputs are loaded, no ScalarService.op is called, no model
chain runs, no Matrix library is loaded, and no Matrix FMA or compiler executes.

The original method is restored after a negative monkeypatch control before the
positive constructor is called. The gate then observes one admitted None load
and one fegetround lookup. Twenty-five negative controls cover direct/arbitrary
callers, constructor bypass, substituted same-name code, unknown native paths,
early oracle reads, native writes, and unrelated old-work ELF reads.

Cold regression runs combine the 18 unchanged v1 tests and 4 v2 tests, both
normal Python and optimized Python. Each v2 suite invokes the real environment
probe in its own bounded subprocess. Actual model execution continues to use
the original nonoptimized CPython 3.12 observer requirement.

## Unchanged budget and acceptance boundary

900 seconds inner and 930 seconds total supervisor budget still apply, including
setup, hashes, environment initialization, model execution, observation, output
seal, post-seal oracle comparison, final hashes/receipts, and bounded cleanup.
Supervisor TERM remains at 924 seconds, latest KILL at 927, reaping stops at 929,
and the last second is reserved for the supervisor receipt. Incomplete cleanup
or timeouts cannot yield acceptance. See the immutable v1 README for the full
stage budget and extrapolation risks: 25% linear allowance leaves about 9 seconds
for unmeasured tail cost, so successful completion is not guaranteed.

The only proposed new model output is:
work/qwen2_live_attention_numeric_m128_bounded_20261014/m128_pv32_bounded_actual_v2

All nine inputs must load fresh. No old QKV/session is reused. att stays
unpublished and pc12 completion held. No finalfence, fullblock, RTL, or hardware
acceptance is claimed. FREEZE.json records the exact newly reviewed command and
closure; it does not itself grant permission to execute.
