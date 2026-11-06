# TEMP: unrun portable native build description

This package describes the original Matrix/ICG and iDMA build stages from the preserved source. It does not execute them. The original hardware, including eight 512-MAC Matrix leaves (4096 MACs), is unchanged.

The fixed source basis is commit `db6fd29aac11a2b70b0c60b3e09106db9256df26`. The recipe adds source catalogs and descriptions; it does not change the existing Scala source selection or native bridge sources.

## Read-only commands

From the repository root:

```sh
python3 -I -B candidates/chisel_hybrid_host_20261106/native/build_recipe/recipe.py
python3 -I -B candidates/chisel_hybrid_host_20261106/native/build_recipe/recipe.py --check-repository
python3 -I -B candidates/chisel_hybrid_host_20261106/native/build_recipe/recipe.py --describe
python3 -I -B candidates/chisel_hybrid_host_20261106/native/build_recipe/recipe.py --render
python3 -I -B candidates/chisel_hybrid_host_20261106/native/build_recipe/test_recipe.py
python3 -I -B -O candidates/chisel_hybrid_host_20261106/native/build_recipe/test_recipe.py
```

`--check-repository` hashes the declared repository source files. `--describe` prints the contracts. `--render` prints the ordered, tokenized command templates without substituting paths or invoking programs. All output is written to stdout. These commands do not install tools, create build directories or file lists, emit RTL, compile native code, load libraries or run models.

The loader checks a fixed manifest digest before importing its exact source buffers. Each component also binds its complete canonical description, including stage order, arguments, source identities, prerequisites and unresolved conditions. The tests exercise those source contracts and reject tampering. They do not establish a successful native build.

## Contents and historical scope

- `matrix_icg.py`: 213 descriptive stages, including the original provider reconstruction, separate HardFloat helper compilation/emission, Matrix/ICG generation, ordered 193/7 generated-unit compilations and archives, and bridge/direct/C-ABI links. The generated-unit flags retain the prior settings; the recipe does not add a C++ language flag to those units.
- `idma_recipe.py` and `idma_source_contract.json`: 10 descriptive stages and identities for 296 ordered RTL units and 18 include headers. The catalog records wrapper parameters and diagnostic source sites. It contains identities and source metadata, not RTL payloads or vectors.
- `idma_without_pch.mk` and `adapter_without_pch.mk`: exact handwritten no-PCH make fragments used with the prior generated makefiles. The generated makefiles and model outputs are not included.
- `FRAGMENTS.json`: selected component and test identities. The component tests are executed from verified buffers by `test_recipe.py`.

Prior library/output identities are comparison targets from completed local builds. Earlier finite observations remain limited to the scopes in [the native source README](../README.md), including Matrix/ICG direct/C-ABI traces and the retained iDMA leaf/adapter cases. Those results do not qualify this new portable description or provide a complete replay package. The ABI assertion translation units were syntax-checked; that is distinct from linking or running them.

## Prerequisites still unresolved

This is a command sequence conditional on external prerequisites, not a ready build executor. In particular:

1. A future owner must establish exact tools, runtime/ELF dependencies, system headers, Java/Python identities and sanitized environment. Historical tool hashes are not proof that those tools are available on a new machine.
2. It must create fresh, non-clobbering output directories, ordered source lists and source/provider materialization. The existing Matrix reconstruction helper hashes its compose source before importing it through a separate read. A future execution owner must compile and execute the already-verified source buffer, or establish immutable source ownership together with exclusion or separate verification of every bytecode cache the loader may execute. Python -B prevents cache writes, not cache reads. This checker does not resolve that boundary.
3. The published 204-source Scala compiler describes `original162/`, `modulecache/`, `graph/`, `helpers/` and ordered Maven dependencies. `PhysicalFmaStageLibrary.scala` needs its own compilation/emission against the original source dependencies. The portable recipe has not run that producer. The original iDMA adapter emitter and exact class/provider route also remain an explicit prerequisite.
4. Full diagnostic-byte comparison, ABI/dependency checks, ordered archive checks, process ownership and loaded-library mapping checks need a separately reviewed build owner. A warning-site catalog alone does not satisfy the diagnostic gate.
5. Matrix/ICG links propose the literal relative rpath `$ORIGIN/../lib` in place of a historical machine-local rpath. This is an unexecuted relocation requiring fresh link/load qualification. The accepted iDMA link descriptions contain no rpath flag, and none is added here.

Exact original provider/FMA/header bytes can be compared where specified. Relocated generated metadata and ELF/rpath outputs may depend on build paths; matching historical output hashes is not promised by this description.

All fragments retain `UNRUN_PORTABLE_BUILD_RECIPE`, unresolved prerequisites and `execution_authority: false`. CI checks source hashes, descriptions and pure tests, then runs the existing Scala compile-only job. It does not invoke these native command templates, elaborate Verilator models, run numerical profiles or upload generated artifacts. Full Host construction, hybrid numerical acceptance and same-RTL replay remain separate, unpassed gates.
