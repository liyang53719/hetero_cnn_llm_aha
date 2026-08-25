# L2 AHA/Garnet control-plane audit

The pinned generated macro is the `Garnet` top, not the nested
`Interconnect`. It exposes a 13-bit AXI write interface and a 64-bit
`proc_packet` interface to its official Global Buffer/Controller.

The official AHA `test_app` flow is preserved in this order:

1. Write bitstream entries as 64-bit proc packets, incrementing the address by
   eight bytes.
2. Write bitstream and kernel Global Buffer configurations via AXI.
3. Write `GLC_PC_START_PULSE_R` (`0x1c`) to start parallel configuration and
   wait for its official interrupt.
4. Write `GLC_STREAM_START_PULSE_R` (`0x18`) to start G2F/F2G streaming.

`aha_garnet_axi_config_loader.sv` implements only one AXI configuration write
at a time and retains the upstream-required `AW -> W -> B` ordering. It has no
bitstream interpretation, no invented global-buffer address mapping, and no
completion claim for the full application. Its directed randomized-ready test
passes for a parallel-config pulse and a stream-start pulse, including a
non-OKAY response path.

`aha_garnet_proc_packet_writer.sv` independently splits one project 512-bit
beat into eight consecutive 64-bit packet writes, low 64-bit word first, with
the matching eight byte-enable slices. It accepts a resolved 18-bit packet
address; the higher-level descriptor/Gaussian metadata loader owns any Global
Buffer address translation. Its eight-write ordering and byte enables pass a
directed test.

The next wrapper piece connects both primitives into a command/run FSM and
feeds it with `design_meta.json` IO tile addresses and the official packet
address translation. It must not assume that a CGRA lane number is a physical
Global Buffer address.

`aha_garnet_microsequencer.sv` now provides that strictly ordered primitive
composition. It accepts only three already-lowered operations: 512-bit packet
write, AXI configuration write, and wait-for-official-Garnet-interrupt. Its
test checks a packet operation, a `0x1c` parallel-configuration AXI write, and
an interrupt wait in sequence. It is not yet a full Gaussian descriptor
frontend or a macro numerical-equivalence result.

The exported Gaussian `gaussian.bs` has 519 exact `{address,data}` entries.
`aha_garnet_trace.py` packs them losslessly into 65 project-side 512-bit packet
beats at official bitstream base `0x00000`; the final beat has seven valid
64-bit words and byte-enable `0x00ffffffffffffff`. The script records only
control facts independently confirmed by the L1 test log (`0x01c=1` parallel
config start and `0x018=0x00030003` stream start). The remaining AXI BS/Kernel
register table is explicitly not yet reconstructed.

The table is now reconstructed by compiling and running the pinned upstream
`parser.c`, `map.c`, and `gen.c` with mechanically converted headers from the
same generated AHA closure. For the frozen 4x16 Gaussian app it yields five
`bs_cfg` writes, 39 `kernel_cfg` writes, parallel-config start `0x01c=1`, and
stream start `0x018=0x00030003`. The exported `control_table.json` is an input
to the project transcript; it is not hand-authored configuration data.

The same extractor emits the required pre-PCFG interrupt-enable sequence:
`0x02c=7`, `0x028=1`, `0x024=3`, and `0x020=3`.

The same transcript now reconstructs the official default Gaussian input split:
the 25,344-byte 16-bit raw input is deinterleaved exactly as test_app does,
with tile 0 taking source element `2*k` and tile 1 element `2*k+1`. Each tile
receives 12,672 bytes (198 project packet beats) at packet bases `0x00000` and
`0x20000`, respectively.

`tb_aha_garnet_gaussian_transcript.sv` wires the project microsequencer to the
actual 33-port generated `Garnet` top and consumes this transcript. Verilator
successfully elaborates all 644 modules and builds a 33 MiB executable with the
system `ar` workaround for the isolated conda toolchain. The PCFG-only runtime
probe PASSes in 2253 cycles: it completes the interrupt-enable writes, 65
bitstream packets containing all 519 entries, BS/kernel configuration writes,
PCFG start, and the official Garnet interrupt. The harness explicitly drives
`reset_in` from 0 to 1 before deasserting it; declaration-time `1` did not
trigger the generated asynchronous AXI-controller reset branch in Verilator,
leaving `AWREADY` low. This establishes control-plane acceptance only. Proc
readback and byte-for-byte comparison of Gaussian output against upstream
golden data are still required for AHA L2 numerical equivalence.

The current numerical harness uses the exact upstream `ProcDriver_read_data`
continuous-read pattern for each output block: 1,519 consecutive 64-bit
addresses, `rd_data_valid` waiting, and the upstream Verilator one-clock-late
sample point. This is required because the generated Global Buffer gates its
proc-read clock with delayed `rd_en`; isolated one-word pulses can stop the
response pipeline before its data is sampled. Its full numerical rerun is
pending the resource admission guard; no output-equivalence PASS is claimed.

Golden output data is loaded with the same 16-bit big-endian file semantics as
the upstream `$fread` into `bit [15:0]`: raw bytes `00 70` mean numeric
`16'h0070`. Proc readback then packs four numeric lanes low-word first. This
normalization is separate from input packet byte preservation and prevents a
false byte-swapped mismatch in the L2 comparison.
