# Connected original RawPrep / cold / two-chunk / export numerical regression

See PLAN_CN.md and SUMMARY.json for exact partial PASS scope. This is a testbench sequential scheduler, not production resource authority or full 4096-MAC hardware. Original upstream source bytes are pinned.

Run `python run.py --jar-dir <pinned-jars> --verilator-dir <existing-verilator-bin> --head 0 --cycles 11000000 --wall-seconds 600`. Dependencies may span repeated --jar-dir arguments. Runtime fixture generation uses independent pinned Python references, never hardware output as oracle; actual accepted writes populate DUT memory. Data files stay local. --head 1..15 supported but not yet validated.

The first 240-second joined run reached chunk1 phase4 then timed out and was reaped. Re-run completed on the exact same generated hardware hash; only test runtime head selection / resource budget changed. No full-block/RTL/MAC-utilization claim.
