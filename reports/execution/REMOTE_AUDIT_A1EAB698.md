# Remote audit of local-agent commit a1eab698

## Accepted

- Balanced 8×8 Attention SFU E1/E4 passes.
- Composed production-boundary E3 passes at 321.869395 token/s with zero score/probability DDR materialization.
- The 28-layer count/trace E3 passes at 320.791599 token/s within 4 MiB SRAM.
- Official-revision reference checkpoints, 160 bit-exact LM-head columns and a reduced four-layer cross-RTL replay pass.
- Refined rsqrt passes standalone 1 GHz DC and the reduced replay is 7,840/7,840 BF16 bit-exact.

## Corrected claim boundary

The latest reports explicitly say that the full trace is not a 28-layer payload numerical simulation and that reference hidden snapshots anchor the reduced four-layer replay. Therefore the audit accepts L5.6a/L5.6b/L5.6c, but keeps L5.6d continuous full-payload RTL open.

L10 early PPA may proceed in parallel. This audit does not reopen the accepted performance result; it prevents a reduced numerical result from being overstated as full-payload closure.

## Control-plane defect corrected

At a1eab698, `control_plane.json` and `MASTER_LEDGER.json` moved to L10 while `local_agent/stages.yaml` remained at the old L5.5/L5.6 wait state, and `final_validation.json` still listed the full-model gate. v6.14 aligns these files and makes the parallel/open boundary explicit.
