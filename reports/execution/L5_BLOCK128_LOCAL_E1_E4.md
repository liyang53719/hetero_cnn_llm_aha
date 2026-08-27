# L5.1 Block128 local E1/E4

Status: IN_PROGRESS. E1 passes; E4 timing does not yet pass.

The pulled v4 source initially failed RTL case 94 because its Python/C++ PWL
tables differed from the committed RTL table by one ULP in 21 coefficients.
The coefficient generator now emits the SystemVerilog, Python and C++ tables
from one NumPy operation order. All three 256-entry tables match exactly.

Real Verilator E1 evidence:

- 132/132 M/L/O arithmetic vectors pass bit-exactly.
- Deterministic random header and beat backpressure passes.
- One complete 128-lane summary passes as 32 ordered 4-lane beats.
- Output payload and `last` remain stable under stall.
- Binary SHA256: `3ef76de9dfb92d3de50a51f78a5bf724b39a8aaee0cab7596864e3564a30ba30`.

Early CLN22UL DC at 1.0 ns links with zero unmapped cells. Real pipeline stages
were added between O multiplies/add, exp2 floor/multiply/add, and M/L
subtract/scale/multiply/add. WNS improved from `-2.20967 ns` to
`-0.555804 ns`; the remaining critical path is one combinational HardFloat
FP32 multiply from a registered exp result to a registered L product.

Latest early PPA: 40,846.9885 square library units, 82,453 leaf cells, 1,305
sequential cells, zero macros and zero unmapped cells. These numbers are early
logic-only PPA, not final integrated PPA.

Next action is an internally pipelined HardFloat raw-multiply/round primitive.
No false path, frequency reduction or multicycle exception is authorized.
