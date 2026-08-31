# Branch consolidation and main-only policy

## Remote inventory

The complete remote branch enumeration on 2026-08-31 returned exactly one
branch:

```text
main
```

The continuation page was empty. No remote merge or branch deletion is needed.
The accepted local-agent closeout commit
`eba24625350d14fe3f9d760929736dcf5872fabd` is an ancestor of `main`; at the
audit point, `main` was 33 commits ahead and zero commits behind it.

## Important distinction

Revision 6, Revision 7, Revision 8A, Revision 8B-A and Revision 8B-B are
hardware implementation attempts recorded in the linear `main` history. They
are not active Git branches.

## Matrix implementation attempts and conclusions

| Attempt | Purpose | Result | Final conclusion |
|---|---|---|---|
| Revision 6 | Preserve separately compiled HardFloat leaf DDCs | Lane timing remained negative | The DDC boundary blocked useful accumulator-mux/Pre optimization |
| Revision 7 | Remap one four-context lane from source | Lane and functional gates passed; structural H3 failed | A lane-local fix was insufficient for the 512-lane top |
| Revision 8A | Early context-bank commit while retaining 4 stages/4 contexts | Functional/component gates passed; H3 exposed severe control fanout | Preserve as functional evidence, not canonical hardware |
| Revision 8B-A | Add bounded combinational fanout distribution | Transition/capacitance violations were eliminated; H3 timing still failed | Fanout was real but not the only 1 GHz limitation; activate the authorized fallback |
| Revision 8B-B | Five-stage FMA, five contexts, 3-bit internal tag, depth-5 completion buffering | E1, mapped comparison, components and H3 passed | Canonical L5.2 Matrix boundary; retain ultra-low timing margin as an L10 risk |

Current accepted Matrix result:

```text
16x32 / 512 BF16 MAC lanes
5 stages / 5 contexts
1 GHz component/H3 WNS +0.00490451 ns
transition/cap/unmapped/unresolved 0/0/0/0
```

## Parallel workstreams are not Git branches

L5.3 Blocked Attention and L5.4 fused SiLU are parallel engineering workstreams,
not repository branches. Their commits, evidence and control-plane updates must
be serialized directly on `main`. L5.5 remains their mandatory join.

## Main-only rule

From this point forward:

```text
allowed local branch   = main
allowed remote branch  = main
push                    = fast-forward only
force push              = forbidden
new branch / PR branch  = forbidden unless the user explicitly approves it
```

The executable check is `scripts/check_main_only_workflow.sh`; the machine-
readable policy is `config/git_workflow_policy.json`.
