# AHA Verilator 5.028 toolchain lock

## Immutable inputs

- AHA image: `stanfordaha/garnet@sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b`
- Verilator release tag: `v5.028`
- Verilator source commit: `8ca45df9c75c611989ae5bfc4112a32212c3dacf`
- Source checkout: `work/toolchain/src/verilator-5.028`
- ABI-compatible install: `work/toolchain/verilator-5.028-aha`

## Build contract

The source was fetched via GitHub SSH after the Docker Hub image-layer pull
repeatedly reached EOF. It was built inside the pinned AHA Ubuntu 20.04 image,
using image-local dependencies `autoconf`, `flex`, `libfl-dev`, `help2man`, and
`bison`. The installed binary reports:

```text
Verilator 5.028 2024-08-21 rev v5.028
```

The install is verified executable when mounted back into the same AHA image.
The host-built 5.028 binary is intentionally not used because it requires
GLIBC 2.32--2.35 while the AHA image provides GLIBC 2.31.

## Timing-model compiler contract

Verilator 5.028 `--timing` requires a coroutine-capable C++ compiler. The AHA
image's default GCC 9 lacks `<coroutine>`. `scripts/reproduce_aha.sh` therefore
supports the explicit opt-in:

```bash
AHA_TOOL=VERILATOR \
VERILATOR_ROOT=$PWD/work/toolchain/verilator-5.028-aha \
AHA_VERILATOR_CXX=g++-10
```

For this mode it installs `g++-10` only in the ephemeral container and passes
`-std=gnu++2a -fcoroutines` to Verilator. The generated Makefile is overridden
via `MAKEFLAGS=-j6 CXX=g++-10`; no upstream AHA source or testbench is changed.
