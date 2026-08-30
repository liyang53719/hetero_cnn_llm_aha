# L5.2 Revision 8B-B activation

Status: **ACTIVE**. The pre-authorized fallback in
`config/l5_revision8b_a_policy.json` has triggered.

Revision 8B-A closed every functional and distribution gate:

```text
broadcast functional vectors       100,000 PASS
Revision8A-vs-8B-A cycles          120,000 PASS
dependent E1                       1,000,000 at II=1 PASS
random-backpressure E1             10,000 PASS
adversarial E1                     50,000 PASS
broadcast mapped comparison        100,000, zero mismatch/unknown
broadcast DC                       WNS +0.302272 ns, transition/cap 0/0
operand distribution DC            WNS +0.379584 ns, transition/cap 0/0
H3 unresolved/unmapped             0/0
H3 transition/cap                  0/0
H3 WNS                             -1.3073 ns
```

The remaining path is `context_i -> scheduler -> mapped broadcast tree ->
lane metadata/HardFloat Pre -> pre_meta_q`. It is 2.08 ns at the frozen corner;
the mapped distribution contributes about 1.18 ns. This is not an unfixed DRC
path. Revision 8B-A therefore cannot reach 1 GHz without another pipeline
boundary.

No further 4-stage/4-context timing tuning is authorized. Revision 8B-B shall:

- add one cluster-local registered input/Pre boundary;
- use a 5-stage arithmetic/metadata pipeline;
- use five physical accumulator contexts and 3-bit internal tags;
- preserve the public 128-bit command and generated HardFloat;
- revalidate 120k source compare, 1M dependent II=1, 10k random, 50k
  adversarial, mapped equivalence and structural H3 at 1 GHz.

L5.3 and L5.4 remain authorized in parallel. L5.5 remains the mandatory join.
