# FIFO ready split and generation-only preflight

TEMP_SOURCE. Actual execution of this successor is NOT_EXECUTED; source review is GO (review_fifo_ready_whole_source_20261019T0847; manifest b8980bdc7114e4848d11092757aac00d04b5d57641cc55b8832e3578e3a42e69; summary b6a1b784b5301dc410478ecc07077e2c3432452047f0b4f451873d096571d61e).

The previous run 39220292509 remains INCOMPLETE: its complete bounded generation log contains one UNOPTFLAT warning and all nine Example locations. The source-level cone contains a procedural aggregation edge: the FIFO block reads valid_i while assigning ready_o, although the ready_o equations do not use valid_i. This is a finite source finding, not a whole-design SCC proof or a prediction that the next run will be warning-free.

The opt-in FIFO successor moves the original procedural flush branch and both ready_o assignments into a separate combinational block. It retains the existing separate valid_o block. Both expressions, SameCycleRW's real ready_i dependency, state updates, iDMA atomic gating and arithmetic RTL stay unchanged. The original 4,411-byte member and 927-member source table remain historical inputs. The 4,536-byte intermediate is verified before deriving the 4,662-byte member; selected319 totals 3,072,451 bytes. Only the two existing WIDTHEXPAND coordinates move, 81→98 and 100→114, with exact original text anchors and no new warning exemption.

Only host-generation-diagnostic adds three early phases: fixed Icarus acquisition, FIFO compile and FIFO run. The unchanged four-state cases must report exactly four cases and 5,180 comparisons before the existing 32 stages begin. This tests extracted combinational equations with manually supplied state, including X/Z and backpressure cases. It does not certify flop/reset/delta-cycle equivalence, complete four-state simulator semantics or production numeric behavior. The previous 5,180 pass is not reused for the new split.

The three new phases reuse the fixed package, 39-member selection, 21-ELF and target-library/VPI checks from the reviewed micro runner. No paired Host model is rerun. Acquisition alone receives the platform proxy/CA variables; native fixtures use a clean environment. The shared 6,600-second deadline and prior phase limits are unchanged. Generation remains warning-fatal and stops before Host C++ compile/run.

Root-header observation now records fixed read-failure labels and fstat byte lengths. Only SIZE_LIMIT at 4 MiB with observed size at most 16 MiB permits a bounded 16 MiB retry. Regular-file, no-follow, descriptor/name/directory stability remain checked; the parser is unchanged. Above 16 MiB stays unknown. Prior actual root_header CONTRACT_ERROR and 256-handle count remain unresolved; this successor does not fill them from source expectations.

Only the three validated safe JSON documents may be uploaded. Packages, raw logs, generated source, target-library identities and machine paths remain private.
