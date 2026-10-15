# Canonical observation-shape retention view

This candidate fixes one representation mismatch: the original PV32 observer
returns tuple shapes, while its saved JSON contains lists. The wrapper accepts
only the exact ten original fields and their fixed M16 or M128 dimensions.
Every dimension must be a native integer; booleans, other row counts, altered
shapes, missing fields and unknown fields are refused.

Only these ten shape containers are converted to lists in a separate report
view. The caller's report, capture and tensors are unchanged. The wrapper then
calls the existing retention seal implementation, preserving its actual and
observer byte/hash comparisons, original 21/17/1 terminal gate, closed-capture
requirements and private-only receipt. Non-shape mismatches still fail. This
is not a general JSON normalization or a relaxed evidence gate.

Cold tests reproduce the original tuple/list failure and exercise both allowed
geometries, source-report nonmutation and rejected evidence changes. Their
payloads and terminal records are synthetic and do not constitute a model run.
The earlier M16 FAIL and independent posthoc recovery remain immutable. A new
runner must explicitly select this wrapper and independently satisfy its own
source, runtime, input, terminal and numerical checks. No M128 result is claimed.
