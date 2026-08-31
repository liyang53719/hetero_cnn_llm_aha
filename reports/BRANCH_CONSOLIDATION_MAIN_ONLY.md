# Branch consolidation and main-only policy

## Remote inventory

The complete remote branch enumeration on 2026-08-31 returned exactly one
branch, `main`; the continuation page was empty. No remote merge or branch
deletion is required.

`eba24625350d14fe3f9d760929736dcf5872fabd` is the accepted L5.2 closeout and is
an ancestor of the current main line. At the audit point main was 34 commits
ahead and zero behind it.

## Revision attempts are not Git branches

Revision 6, Revision 7, Revision 8A, Revision 8B-A and Revision 8B-B are
hardware implementation experiments recorded in linear main history.

| Attempt | Result | Conclusion |
|---|---|---|
| Revision 6 | Independent HardFloat DDC boundaries left negative lane timing | Boundary prevented useful accumulator-mux/Pre optimization |
| Revision 7 | Lane/equivalence/E1 passed; 512-lane H3 failed | Lane-local remap was insufficient |
| Revision 8A | Functional/components passed; H3 exposed severe global fanout | Retain as functional baseline, not canonical hardware |
| Revision 8B-A | Fanout DRC removed; H3 remained negative | Authorized 5-stage/5-context fallback was required |
| Revision 8B-B | E1, mapped comparison, components and H3 passed | Canonical L5.2 Matrix boundary; keep ultra-low margin as L10 risk |

L5.3 Attention and L5.4 SiLU are parallel workstreams, not Git branches. Their
commits and evidence must be serialized directly on main.

## Enforced policy

```text
allowed local branch   = main
allowed remote branch  = main
push                    = fast-forward only
force push              = forbidden
new branch / PR branch  = forbidden unless explicitly approved by the user
```

The executable gate is `scripts/check_main_only_workflow.sh`; the machine-
readable policy is `config/git_workflow_policy.json`.
