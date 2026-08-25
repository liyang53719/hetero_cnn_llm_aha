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

The next wrapper piece is a 512-bit to 64-bit proc-packet writer. It must use
the `design_meta.json` IO tile addresses and the official packet address
translation, not assume that a CGRA lane number is a physical Global Buffer
address.
