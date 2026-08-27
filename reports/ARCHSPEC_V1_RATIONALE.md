# Archspec v1 rationale

`configs/arch_v1.yaml` is the canonical planning archspec. `arch_v0.yaml` is
retained only for the existing functional-model regression and is not the
performance/PPA authority.

The main changes are:

- separate retained-Gemmini INT8/CNN and clean-room BF16/LLM Matrix paths;
- fixed-function performance-critical Attention/Norm/SFU path;
- legal 4x4 ratio-2 AHA sidecar plus wrapper SRAM instead of an impossible
  16-Lake-plus-compute 4x4 topology;
- universal block128 attention and parameterized Matrix contexts;
- descriptor v3, 64-bit counters/addresses, and explicit capability fallback;
- hard wall-clock utilization and q1024 performance gates.

Every DSE point must be emitted as a complete archspec derived from this file,
not as an undocumented RTL parameter change.
