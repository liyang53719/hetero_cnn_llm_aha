# Three-model Chisel RTL and 800 MHz DC closure plan

## Objective and evidence boundary

Starting from `main@b55ddcb`, reproduce the two committed Chisel source layers,
generate immutable authoritative RTL, bind every terminal operation to a real
hardware endpoint, run Qwen2/Qwen3.5/Qwen3.8/Vision RTL canaries, and close
per-module plus endpoint-bound combined-shell DC at 1.250 ns.

The repository contains Chisel/Scala, not Catapult HLS C++ or HLS reports. The
implementation origin is frozen as `Chisel`. Source coverage, elaboration, a
command echo, or an immediate completion stub is not numerical hardware closure.

## Stages

1. **G0 control-plane freeze**: keep `main` only; use the unversioned ledger,
   next-action and handoff as the only active state; preserve the two user
   runtime scripts without tracking or modifying them.
2. **G1 local source replay**: reproduce 18 model roots with Java 17/SBT
   1.10.2/Chisel 6.7.0 and 25 Gemmini-context primitive modules from pinned
   Chipyard/Gemmini. Require model inventory 30/93/150 and 58 bindings.
3. **G2 authoritative generation**: commit 18 root and 25 primitive SV files
   under `generated/operator_primitives_v3/` with source/tool/RTL hashes. Never
   edit generated RTL; fix Chisel and regenerate. Emit one collision-free
   combined hierarchy instead of concatenating duplicate helper modules.
4. **G3 protocol and endpoint closure**: keep the 18-root `ProgramPrimitive`
   protocol canonical. Bridge kind/flags/tag/phase to owner/opcode, aggregate
   expanded composite completion, and bind Control, DMA, Matrix, SFU, KV,
   State, Selection and Vision to real RTL. Tie-offs, output injection, CPU
   fallback and undeclared black boxes are forbidden.
5. **G4 numerical and integration canaries**: run at least 20 seeds and 100
   completed transactions per root with independent backpressure; differential
   test 25 primitives and all inventory entries; run Qwen2, Qwen3.5, Qwen3.8
   and Vision canaries with descriptor/L2 traffic and real owner stalls.
6. **G5 800 MHz DC**: synthesize 18 roots, 25 primitives, eight owner endpoints,
   then the endpoint-bound combined shell bottom-up. Include the existing 4 MiB
   SRAM macro DB set and keep DDR external.

## Canonical interfaces

- Public Command128, descriptor-v3, event IDs and 512-bit tensor streams do not
  change. Program selection is decoded from the approved descriptor encoding.
- Root micro-ops retain descriptor handles, dimensions, tag, phase, flags and
  mode. Completion returns only after the real endpoint completes all simple or
  expanded composite work.
- The generic sequencer/frontend in the 25-module package is a comparison and
  per-module DC top; it does not replace or duplicate the 18-root path in the
  functional combined shell.

## DC and resource contract

- Standard-cell DB:
  `/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db`.
- `dc/common_clock_800mhz.tcl` is the only active clock contract: period 1.250
  ns, setup uncertainty 0.080 ns, I/O budget 0.100 ns. No active 1.0 ns clock
  or synchronous-data false path is allowed.
- Every compile/test/simulation/DC command uses `taskset -c 8-23` and the memory
  guard. SBT uses Java 17, `-Xmx8g` and eight active CPUs; Verilator uses at most
  `-j4`; DC uses eight cores. Require MemAvailable above 10 GiB and free disk
  above 50 GB; use MemoryHigh 24G, MemoryMax 30G, one heavy process, blocking
  waits and a 600-second command bound.

## Evidence, Git and notification

Each stage writes a compact result JSON and updates the master ledger, unique
next action and a handoff under 200 lines. Raw logs/DDCs stay under `work/` and
committed reports bind their hashes. Every checkpoint is committed directly to
`main`, pushed immediately and compared with the remote SHA.

Completion requires 18/18 roots, 25/25 primitives, 58/58 real bindings, four
passing canaries, nonnegative per-module/owner/combined WNS and zero unresolved,
unmapped, latch, loop or unconstrained endpoints. A terminal external blocker
requires three consistent checks. On completion or terminal blockage, the
ready Feishu bot sends one idempotent direct message to `用户571625` with status,
SHA, coverage, combined WNS/area and closed gates or recovery action.
