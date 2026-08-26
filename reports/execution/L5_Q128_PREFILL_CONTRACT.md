# L5 q128 prefill operation contract

Status: PASS for shape and operation-count lock only; q128 RTL payload and
cycle measurements remain pending.

The workload is batch1/sequence128 with the pinned target dimensions and a
causal stream order of query token, head, then causal KV token. The physical
16-row array uses eight row batches. Exact Matrix-step counts are Q 589,824;
K/V 98,304 each; O 589,824; gate/up/down 3,440,640 each; total 11,698,176.

The causal prefix sum is 8,256 tokens per head and 99,072 head-token updates
over 12 heads. Therefore q128 requires 99,072 streamed dot128 and online
updates, 1,536 reciprocals and 12,288 O/L chunks. Q/K RoPE requires
98,304/16,384 pairs. No score matrix or full-score writeback is permitted.

This receipt contains no measured cycle value. It is an operation-count
contract that must be followed by an RTL controller count gate and restartable
numerical payload measurements.
