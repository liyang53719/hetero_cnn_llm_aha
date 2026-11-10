# Prepared connected phase2 → phase3/4 Chisel harness

Status: connected original phase2→phase3/4 native simulation PASS. One authorized run, no failed attempts or reruns. Compile13.91s; full native stage36.34s; simulation loop1.211s. Phase2 handoff occurred atcycle66583 with3681reads/2816writes. Finalcycle70679 had4705reads/3840writes, all61440 output words compared bitwise, original receipts/decay identity checked and terminal result held stable.

The test-only DerivedTransposeChain instantiates the existing actual phase2 wrapper (original DerivedAndPairV2Owner, original BlockScalarFloatPolicyV2 and original UnifiedVectorElement32BankV4 with32 source ALU lanes; this unit uses low16 and ties upper16 inputs to+0, so unused lanes may be optimized away) plus original GdnRuntimeChunkTransposeV2Owner. All original source bytes are preserved.

The complete actual phase2 done result handshakes directly into the transpose job in hardware. Context/layout/head/chunk come from its actual retained decay metadata, numeric policy from its actual result, and phase2Ready is the entire actual result. The same result is latched only for observation. No software-generated phase2 receipt or counter bypass is supplied.

A sequential test-only memory-port mux switches on that handshake. One testbench memory map stores actual accepted writes and remains intact across phases. It is not reloaded from an oracle or replaced. The test checks that the handoff follows3681 reads and2816 writes with no pending response. It tracks512 actual KE writes and checks every later KE read has that provenance.

The independent scalar oracle generates expected phase2 writes and K/KE transposes. Expected transpose values are compared only; they are never used to populate runtime memory. Measured total connected traffic is4705 reads and3840 writes. Transpose added1024 reads and1024 writes over4096 cycles after the phase2 handoff, with no arithmetic service calls. The native stage included compilation of the phase2 bank plus original1024-byte transpose tile.

Phase1 remains an explicit synthetic oracle-generated prerequisite. K values originate there. KE values originate in actual accepted phase2 writes. This is not a phase1→phase4 producer chain, full prefill, full block, production scheduler or4096-MAC resource qualification. Full-block acceptance remains0/5.

The portable runner uses the verified native backend and a build-only MAKEFLAGS override VK_PCH_I_FAST= VK_PCH_I_SLOW= to avoid the observed larger-model precompiled-header incompatibility. It does not edit generated hardware or original sources. The integrated launch was authorized after the phase2 baseline passed. The dedicated simulation process group had a240-second wall limit and completed normally.

Reproduction in a fresh directory, preserving the archived results:

    python run.py --jar-dir /path/to/jars --verilator-dir /path/to/verilator-wrapper --cycles 150000

Generated TSV input/expected/memory data, jars/classes, circuit files and raw logs are local-only and excluded from delivery. SOURCE_PINS.json binds38 Scala inputs, including the existing exact receipt-class compilation adapter. FIXTURE_SUMMARY.json records hashes; phase2 input/expected bytes were checked identical to the baseline. Only the transpose source and test-only wrapper/oracle extensions are new.

Architecture targets remain4096 MACs/8x512/Vector32. Source lane count in this unit is not evidence of a preserved physical allocation.
