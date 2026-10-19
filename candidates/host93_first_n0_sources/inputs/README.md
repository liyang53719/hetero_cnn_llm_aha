# TEMP_SOURCE: current raw13 receipt to unchanged provider14 transforms

This finite source successor binds the existing provider converter to the deterministic successful receipt of the currently published fixed raw acquirer. No tensor payload, network acquisition, provider conversion or numeric execution occurred here.

The published acquirer pins acquisition plan `7af00f7b…` and serializes that identity in `ACQUIRED.json`. The old converter instead pins historical plan `b8635eaf…` and historical receipt `557f2c0a…`; directly composing the current sources therefore rejects the metadata before conversion. The derived spec changes only the receipt's expected SHA256 and plan SHA256. Its size remains 4,335 bytes. The new expected receipt SHA256 is `0b319b9dc84a4c3942f3068b397e01f0e3493515b542ddf726d7d0677e01b6fa`. This is a source-derived expected identity, not a new actual acquisition receipt. No historical receipt is fabricated or renamed.

All 13 raw identities, all 14 provider identities, geometry/order, 94,382,080 raw bytes, 94,916,608 provider bytes and every converter function remain unchanged. The converter changes only its fixed spec SHA constant; PLAN_BYTES remains 17,884. BINDING.json records base/derived full identities. Existing conversion resource limits remain 120 wall seconds, 60 CPU seconds and 256 MiB address space. A future coordinator must also enforce its original shared deadline.

Cold checks: the original 18 converter methods ran in normal and optimized modes against the derived source, with only the expected receipt SHA changed. Eight additional checks in each mode evaluate the exact report-assignment AST from the verified current acquirer; accept that serialization, show the old consumer rejects it, show the new consumer rejects the old serialization, reject altered order/tensor identity/truncation/trailing bytes, and prove all converter functions and non-receipt spec fields byte-identical. Only synthetic receipt metadata and existing public source were read. The initial new-test harness named the source function incorrectly and failed before receipt evaluation; correcting it to the actual `collect_fixed` function produced the recorded final 8+8 passes. No converter production code changed for this harness correction.

Portable cold entry points, with an absolute checkout path:
- `python3 -I -B test_cold.py --repo /absolute/checkout -v`
- `python3 -I -O -B test_cold.py --repo /absolute/checkout -v`
- `python3 -I -B test_receipt_binding_cold.py --repo /absolute/checkout -v`
- `python3 -I -O -B test_receipt_binding_cold.py --repo /absolute/checkout -v`

The new receipt test hard-pins and executes the same checked source buffers, including current acquirer and base/derived converter. The existing converter test retains its fixed adjacent PROJECT_SOURCE_HASHES.json contract. This source does not grant runtime/RTL/numerical qualification and does not schedule a job.
