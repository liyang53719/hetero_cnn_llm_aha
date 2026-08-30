# Local-agent handoff v6.4

State: Revision 8B-A is closed as `TRIGGER_REVISION8B_B`; Revision 8B-B
5-stage/5-context is active. Do not tune 4/4 again.

## Revision 8B-A evidence

```text
broadcast functional             100,000 PASS
Rev8A-vs-8B-A full-top           120,000 cycles PASS
dependent/random E1              1,000,000 II=1 / 10,000 PASS
adversarial E1                   50,000 PASS
broadcast mapped compare         100,000, mismatch/unknown 0/0
broadcast DC                     WNS +0.302272 ns, trans/cap 0/0
operand functional               10,000 PASS
operand DC high                  WNS +0.379584 ns, trans/cap 0/0
H3                               WNS -1.3073 ns
H3 trans/cap/unmapped/unresolved 0/0/0/0
H3 area                          1360153.527546
```

The remaining 2.08 ns path is `context_i -> scheduler -> mapped broadcast ->
lane metadata/HardFloat Pre -> pre_meta_q`; DRC is clean. Activation evidence:
`reports/L5_2_REVISION8B_B_ACTIVATION.md`.

## Active Revision 8B-B

- Add one cluster-local registered input/Pre boundary.
- 5-stage pipeline, five physical contexts, 3-bit internal context tags.
- Keep 16x32/512 lanes, 1 GHz, generated HardFloat and public 128-bit command.
- Revalidate source/value equivalence with one-cycle latency shift, 1M II=1,
  10k random, 50k adversarial, mapped equivalence and H3.
- L5.3/L5.4 remain parallel; L5.5 is the join.

## Unique next action

Implement candidate-only scheduler5/tag5/lane5 source and unit tests under
`rtl/matrix/candidates/rev8b_b/`. Do not edit canonical/generated RTL or the two
untracked user runtime scripts.
