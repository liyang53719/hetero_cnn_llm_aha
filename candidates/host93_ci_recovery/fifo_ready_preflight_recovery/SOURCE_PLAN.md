# Source plan

Parent commit: 664a7bfda94b577c2a998f20c1fcf11f830b6a7a.
Status: TEMP_SOURCE; actual NOT_EXECUTED; independent whole-source review GO (review_fifo_ready_whole_source_20261019T0847; manifest b8980bdc7114e4848d11092757aac00d04b5d57641cc55b8832e3578e3a42e69; summary b6a1b784b5301dc410478ecc07077e2c3432452047f0b4f451873d096571d61e).

1. Preserve original source identities and derive only the FIFO member from 4411 to 4536 to 4662 bytes. Verify the exact ready assignment removal/insertion and existing width-warning anchors.
2. Run the existing FIFO case matrix against the original reference and new derived equation block. Keep the old reference and cases byte-identical. Four expected case counts are 1294, 1294, 1296, 1296.
3. For host-generation-diagnostic only, call icarus_acquire (120 total/90 work/40 CPU seconds), fifo_compile and fifo_run (30 total/10 work/10 CPU each). All use AS 512 MiB, file cap 4 MiB and log cap 64 KiB. Acquisition tree cap is 16 MiB; fixture tree cap is 8 MiB. All phases consume the existing shared deadline, with first failure stopping continuation.
4. Bind an AVAILABLE FIFO observation to the exact tool identities and three clean native rows. Bind finite parent contract labels to the observed FIFO stage prefix. Record successful native rows even when a following parent check fails.
5. After FIFO qualification, run the previous six early Scala/CHIRRTL stages. Require the exact historical FIR before continuing the existing toolchain and generation-only path. The old full34, build16 and CHIRRTL-frontloaded34 modes retain their previous sequences.
6. Record root-header read codes/size and conditional retry, retaining the old fixed-form parser. Do not infer 256 handles from source count. Keep library rules separate from compiled archives and static call sites separate from dynamic call counts.

Execution remains the publisher's responsibility after independent source/content review. No native execution or network operation is performed by this source worker. Old component metadata files describe their historical versions; this recovery plan and the exact new ENTRY/RUN_PINS chain define the opt-in successor.
