# Fresh M128 PV32 actual v1: budget failure, no numerical acceptance

The sole authorized fresh process exited 1 after its existing 570-second inner deadline. Error: `ValueError('public FFN host budget exceeded')`. This was an orderly Python exception, not the 600-second external watchdog kill. No extension, continuation, second full run, threshold change or saved-QKV reload occurred.

- RESULT: `m128_pv32_actual_v1/RESULT.json`, SHA256 `137ce24887985b32e829eab72ce5014ced852b365e47412eb68255142af83787`
- Inner elapsed: 570.090650081 s; outer wall/user/system: 570.639 / 570.050 / 0.535 s
- Constraints: 2 GiB address-space ceiling, OMP/MKL/OpenBLAS threads=1, original reference affinity CPUs0..8
- Post-failure source/tool/input/evidence integrity: all equal; see `m128_pv32_actual_v1/POST_FAILURE_AUDIT.json`
- The original RESULT and all incomplete observer artifacts remain untouched. No oracle comparison occurred. The source control path threw inside Attention before the output seal and oracle opening. The failure handler did not persist the oracle read-list itself, so this conclusion is source/control-path evidence, not a saved per-read audit list.

## Actual live chain and accepted progress

Fresh pc0..8 finished at 76.890706 s. pc8 was genuinely retired in the same execution/host/physical/Matrix/Scalar objects. Fresh pc9 KV exactcopy finished at 77.861710 s, with 262,144 bytes, 4,096 distinct 64-byte coverage beats and 4,096 actual write-ACK events. These are independent quantities that happen to coincide for this run.

Attention then ran approximately 492.228940 seconds before the existing deadline:

| Observation | Actual at failure | Full candidate prediction |
|---|---:|---:|
| Normal Matrix steps/results/replies | 921,633 | 1,188,864 |
| Actual native C normal FMA | 471,876,096 | 608,698,368 |
| Step completion fraction | 77.5222% | 100% |
| Att written and ACKed bytes | 691,712 | 786,432 |
| Att ACK coverage fraction | 87.9557% | 100% |
| Att 64-byte write ACKs | 10,808 | 12,288 |
| Attention accepted read64 events | 1,239,364 | incomplete |
| Attention q / cached-KV read bytes | 692,224 / 78,627,072 | incomplete |
| Matrix Legacy functional ticks | 7,059,451 | incomplete |

The QKV Dense portion separately executed 98,304 wide steps and 402,653,184 actual C FMA. The normal profile0 still executes 512 FMA per step, using the fixed 5×16×256 =81,920-byte accumulator resource. None of these software counts is a hardware cycle or utilization measurement.

Host accepted 11 owner requests, 10 owner terminals, 10 public completions and no final result. Events are0..10. Matrix recorded29 acquisitions and28 releases, with82,245 normal groups but82,244 dones. Therefore Attention was unfinished and service obligations were not drained. Att remained unpublished and nonterminal. This is not held12, not fullblock, and not an Attention pass.

## Frozen observer evidence

Post-failure auditing reads the persisted presence masks and verifies their frozen hashes; it does not read official payloads.

- QK scores/dot/exp: 76,840 observed causal entries of99,072; latest completed head-row is token112/head7, all113 keys
- Probability: 76,732 distinct entries; token112/head7 contains only its first5 keys
- PV BF16/context:172,928 of196,608 words;1,351 complete head-rows, ending token112/head6
- No future positions were manufactured or counted as observed
- The readonly observer correctly reports INCOMPLETE and has no owner terminal/accepted retirement

The partial values have not been compared with the official18-node reference. Existing historical QKV bit-exact results are not transferred to this failed new chain.

## Receipt limitation

The successful runner path stores the newly added mutually exclusive owner-state counters, overlapping service-ownership counters, and memory wait counters. Its exception path stores execution/Matrix/Scalar/physical reports and partial observation, but omits `attention_owner.report()`. Thus the final owner-state breakdown, exact final owner state, Scalar ownership, pending-memory details and C state are unavailable after process exit. Failure peak RSS and runtime oracle read-list are also absent. These fields are null/missing, not reconstructed or guessed. A future candidate must fix its failure telemetry before another run; this sealed execution source and RESULT are preserved.

## Why the budget estimate was insufficient

The initial calibration used a synthetic M8 direct Harness and original profile0 owner. It did not include the real public Host/Dense-idle edges and PhysicalMemory path. The candidate also adds PV32 selected-lane checking, held-reply validation and functional state counters. Synthetic data can take different Scalar branches, and pair-scaling changes the proportion of row setup/output work. These are known scope differences, not a measured attribution of this run's extra time.

At this run's partial rate, a simple step-linear projection is634.95 seconds for Attention and712.81 seconds including the measured prefix/KV. This is an estimate, not an executed complete run or permission to enlarge the budget. Native C call time, Python owner/service time, public/physical-memory overhead, observer callback time and added counter overhead were not timed separately here.

The next useful budget gate would be a bounded, identical-input factorial trace: direct Harness versus real public/physical path, observer off/on, with original versus PV32 schedules held distinct. Preserve real event counts, original arithmetic/resources and source guards. Any reduction in simulator checking/dispatch overhead is a host-model speed improvement and cannot be called architectural throughput or utilization improvement. No such new measurement or second full run has been performed by this report.

## Earlier evidence and authorization

The original calibration, narrow native PV32 equivalence trace, 26-case small-owner gate (19 candidate negatives), 21 normal/21 optimized cold tests, and metadata/public publication-rejection probes remain separate passing evidence. They do not upgrade this full-run failure.

Only the candidate authorization bit changed before the run: `false→true`, old pin SHA `6bc67bf192fd1b1b8ec56e1bc8497b55fb615038f92e59eaa2942767fa63acbc`, new `f7835d1af4dd7011e44719ba029c01eaa0861746a0a825106eea3ffd76ebd386`. The169-source execution closure, tools and nine input identities were frozen before launch. The source snapshot's separate total count accidentally counted its already-included auxiliary Harness twice; `COUNT_ERRATUM.json` records the correct169 unique files without changing the original snapshot or bytes.

The authorization covered this one run only and is now consumed. The candidate remains default-off. Further execution requires a new authorization; none is implied by the persisted bit.
