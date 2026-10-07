# Standalone RoPE hardware arithmetic emission

This project compiles the unchanged production classes from
`integration/gemmini/EmitHeteroFP32Alu.scala` and
`integration/gemmini/EmitHeteroFP32Pipelines.scala`, together with pinned Berkeley
HardFloat, without requiring Chipyard. It emits synthesizable integer/bit RTL;
it does not replace floating-point arithmetic with a host-language model or DPI.

From the repository root:

```sh
scripts/generate_rope_hardware_primitives.sh
python3 chisel/rope_hardware_oracle/manifest.py verify "$PWD" \
  "$PWD/work/generated/rope_hardware_oracle"
```

The generated file is
`work/generated/rope_hardware_oracle/HeteroRoPEHardwarePrimitives.sv`.
It contains `HeteroFP32Alu`, `HeteroFP32MulPipeTag12`,
`HeteroFP32AddPipeTag12`, `HeteroFP32MulPipeBit1`, and
`HeteroFP32AddPipeBit1`. A live-input harness prevents specialization from
constant inputs; the existing arithmetic and elastic pipeline classes remain
unchanged. The historical dummy pipeline emitter is not used.

The script freshly compiles and emits the RTL, checks expected modules, and runs
Verilator lint before writing `manifest.json`. The manifest records source,
upstream, downloaded archive, Maven dependency, emitted RTL, and log hashes, plus
tool versions. `manifest.py verify` checks these against the current files and
checks both the Maven cache and sbt boot JAR copies against `maven-lock.json`.
Integrity checking is not remote attestation: regression runners must invoke the
generator freshly, then verify its manifest, rather than accept an arbitrary
pre-existing RTL/manifest pair as evidence of emission.

## Frozen toolchain

- Berkeley HardFloat: `c1105e6ac6a0dd90fc80893efc4830ab609005d3`
- sbt: 1.10.2; Scala: 2.13.16; Chisel: 6.7.0
- CIRCT firtool: 1.62.1, Linux x86-64 Maven binary
- Verilator: Debian `5.032-1+b2`, extracted locally on Linux x86-64
- All bootstrap downloads have literal SHA-256 pins in the generator.
- Maven POMs and JARs are pinned by SHA-256 in `maven-lock.json`.

Prerequisites: Linux x86-64, Java 17 or later, Python 3, curl, GNU tar,
`sha256sum`, `dpkg-deb`, Perl, and a C++ compiler/make for subsequent simulations.
Java 21 and g++ 14 were used for the initial local gate. The downloaded Debian
Verilator binary also requires a compatible host glibc; set `VERILATOR_BIN` for
an existing installation otherwise. The pinned firtool binary remains Linux
x86-64 specific.

`JAVA_BIN`, `PYTHON_BIN`, `VERILATOR_BIN`, and output directory `OUT` can be
selected explicitly. `VERILATOR_BIN` is a front-end command path; the generated
wrapper clears Verilator's unrelated internal variable of the same name.
The default command is `work/rope_hardware_oracle/bin/verilator`.
HTTP CONNECT proxy settings are read from the current environment.
The emitter uses 4 JVM processors and a 4 GiB heap limit.

Upstream sources, caches, binaries, generated RTL, and license/copyright files
stay below ignored `work/`. No third-party source or generated HardFloat RTL is
vendored in Git. The source archive retains the Berkeley license headers and
upstream `LICENSE` file. Preserve these licenses when redistributing generated
hardware or binaries.

Emission and lint are not an equivalence or physical timing result. The separate
RoPE hardware oracle testbench must simulate these emitted classes and check its
own production inputs, numerical results, IEEE exception flags, reset, and
backpressure behavior.
