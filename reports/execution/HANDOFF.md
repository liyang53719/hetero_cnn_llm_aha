# Local-agent handoff v6.4

State: Revision 8B-A approved; implementation not started. Revision 8A remains
non-canonical after H3 WNS `-10537.7 ns`, 53,455 transition violations and 10
capacitance violations.

## Binding architecture decision

- Policy: `config/l5_revision8b_a_policy.json`.
- Approval: `reports/L5_2_REVISION8B_A_APPROVAL.md`.
- Revision 8B-A first: cycle-neutral mapped combinational fanout tree.
- Topology: front -> 1-to-4 -> four 1-to-8 branches -> 32 cluster leaves.
- Keep 4-stage FMA, four contexts, four-cycle feedback, 16x32/512 lanes,
  1.0 ns, public command behavior and generated HardFloat.
- Do not add an FMA stage during Revision 8B-A.

The mapped tree must distribute all front-to-cluster control/context signals.
Inventory every H3 transition/capacitance root and include violating A/B
operand-distribution nets. Pure RTL `assign` hierarchy without mapped buffer
and H3 DRC evidence is not accepted.

## Revision 8B-A gates

1. Static policy/source contract.
2. Revision8A-vs-8B-A compare >=120,000 cycles.
3. Broadcast component DC and mapped comparison.
4. 1,000,000 dependent steps at II=1 plus 10,000 random steps.
5. 50,000 adversarial operations.
6. H3: 32 clusters/512 lanes, zero unresolved/unmapped, transition=0, cap=0,
   WNS >=0 at 1.0 ns.
7. Post-map E1 and area/power delta.

One normal and one high-effort attempt are allowed, each <=600 seconds.

## Automatic Revision 8B-B fallback

After both attempts, if transition/cap/unmapped/unresolved are all zero and a
non-fanout-dominated H3 path still has WNS <0, stop tuning 4/4 and switch to
5-stage/5-context with a 3-bit internal context tag. Public 128-bit commands
remain unchanged. Revalidate scheduler, scoreboard, tags, banks, equivalence,
one-million-step II=1 and H3.

## Parallel branches

- L5.3 real stream E1/E2 may proceed against the frozen Matrix transaction
  contract, without claiming canonical Matrix integration.
- L5.4 fused SiLU E1/E4 may proceed independently.
- L5.5 remains the join gate and waits for L5.2, L5.3 and L5.4 PASS.

## Unique next action

Create candidate-only Revision8B-A broadcast/top RTL and its independent
test/DC flows. Do not modify generated RTL, canonical RTL, or the two untracked
user runtime scripts.
