# L2 Gemmini descriptor-v2 coverage closeout

Result: PASS for the Matrix portion of L2.

Dedicated retained-Rocket programs cover no-bias LOOP_WS and 1x1 Conv in
addition to the prior single/multi OS, biased WS and 3x3 Conv/requant cases.
Each executes official macros and raw commands in one unmodified
GemminiRocketConfig and compares every output to CPU golden.

- no-bias 17x18x19 LOOP_WS: 11 CUSTOM_3 commands/path, checksum
  `11502680990709447940`;
- 1x1 Conv 1x4x4x3 -> 4 channels: 9 CUSTOM_3 commands/path, checksum
  `7716209159022866879`;
- official/raw differ only at the intentional output destination;
- non-address payloads match generated schema-v2 vectors;
- canonical Chipyard/Gemmini worktrees remain clean.

Production RTL emits 85 legal OS/WS/1x1/3x3 Conv operations and rejects four
malformed/fetch/ReLU6 cases before legal issue. ReLU6 compiler expansion is
Matrix raw output followed by SFU activation. Python 60 PASS and open-RTL PASS.

Evidence: `work/results/l2_gemmini_v2_coverage/` and
`work/results/l2_descriptor_v2_pipeline/`.

This closes the Matrix portion, not canonical L2: basic KV/iDMA production
append/read/free, BF16 staging and address/write/event traces remain.
