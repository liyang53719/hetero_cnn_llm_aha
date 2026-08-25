# Canonical stage reporting

`reports/ARCHITECTURE_AND_EXECUTION_PLAN.md` owns the L0-L11 names. The
longer `stages.yaml` list is an internal decomposition and must never be
reported as if its L11 were the architecture-sweep L11.

| Canonical stage | Internal gates |
|---|---|
| L0 | L0 |
| L1 | L1-L4 |
| L2 | L5 |
| L3 | L6 |
| L4 | L7 |
| L5 | L8 |
| L6 | L9 W8/W4-storage |
| L7 | L10 |
| L8 | L9 native-W4 dual-dot |
| L9 | L11 integrated RTL/model |
| L10 | L12 DC/SRAM |
| L11 | L13 architecture sweep |
