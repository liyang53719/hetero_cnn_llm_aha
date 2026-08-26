# L3 production client arbiter and queued event frontend

Four logical read clients now arbitrate onto the existing physical 2R Shared-L2
ports and two logical writes onto 1W. Request owner/address/data are registered
until downstream acceptance; response owner remains locked until consumption.
Each logical read permits one outstanding transfer. Round-robin fairness is
augmented by one descriptor promotion after eight waiting cycles.

Behavioral-fabric randomized result: PASS, 100005 transactions, 55993 reads,
44012 writes, 55993 correctly routed responses and 650 descriptor promotions.
Every read/write client made progress; stalled valid/payload remained stable;
counter, memory and ownership mismatches are zero. Production arbiter
Verilator `-Wall` lint is clean.

The real 4096x128 Control SRAM scoreboard is now wrapped by independent
depth-16 command and completion FIFOs. Host ready remains low until all SRAM
rows initialize. The real-macro two-reset-epoch test passes 100000 commands,
100000 successful completions, 23 error completions and zero macro errors in
1257883 cycles.

These are production L3 subgates. Direct-stream engine endpoint integration
and a combined 100k all-subsystem transaction test remain before L3 PASS.
