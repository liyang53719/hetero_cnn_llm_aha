# L5 target QKV bias and six-way GQA

Status: PASS as a target-shape boundary subgate; L5 remains `IN_PROGRESS`.

One physical 16-lane FP32 adder applies Q/K/V projection bias. Q has 96 chunks
and emits once per input beat. K and V each have 16 chunks and emit six copies
per beat, mapping query heads 0-5 to KV head 0 and heads 6-11 to KV head 1.
Every output preserves role, input chunk and tag and derives query head, KV
head, head chunk and per-head `last`. Invalid role or range emits one illegal
beat and is never multicast.

The deterministic gate accepted 10,000 inputs and produced 43,000 outputs,
including 100 illegal inputs. Bias values, mapping, sidebands and backpressure
are bit-exact; measured cycles are 60,465 and output-data FNV64 is
`adbdd99efd632cc8`. Input/expected SHA256 values are respectively
`ac83615e538540110a881358b0e6099c3b1883bfa14c33f656d52e2990752d0b`
and `dd0180d855468f0dd2e5da76ea15cfc037edfd09bb5819cc9fe687be9e082888`.
Build allocation was about 311 MB and simulation 11 MB under the 10 GiB cap.
