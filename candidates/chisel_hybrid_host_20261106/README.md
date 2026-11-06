# TEMP: original-Host hybrid bridge, source compilation only

This candidate preserves exact, already compiled Scala source for the original
162-source Host and its Treadle/native bridge. It does **not** establish a full
Host construction, five-block numerical pass, pure-original-Chisel acceptance,
or replay on the final generated Host RTL.

## Build selection

`SOURCES.json` is the complete relative-path selection. It uses the existing
162 hardware files from the original model162 overlay, the existing two
module-cache and ten graph-helper files, and the thirty Scala files here.
The original hardware configuration remains 4096 Matrix MACs and Vector32.
No source glob or previously compiled class directory is a build input.

`MAVEN_INPUTS.json` pins all 107 public Maven roles (106 unique artifacts) by canonical artifact path,
length and SHA-256. The same plugin artifact has both classpath and plugin roles. This includes Scala 2.13.16, Chisel 6.7.0 and its compiler
plugin, chiseltest 6.0.0/Treadle, and JNA 5.14.0. Use JDK21 and Python3 on Linux.
The intentional repository `treadle2.executable.SymbolTable` replacement takes
precedence over the corresponding JAR class. Directory-root duplicates are
rejected. The thirty new helper sources compile together to preserve their
package-private and cross-family references.

Read-only source check, from the repository root:

```sh
python3 -I -B candidates/chisel_hybrid_host_20261106/compile_only.py --check-only
```

Compiler-only build, with a fresh output path outside the checkout:

```sh
python3 -I -B candidates/chisel_hybrid_host_20261106/compile_only.py \
  --java "$JAVA_HOME/bin/java" --output "$RUNNER_TEMP/hybrid-compile-only"
```

The command downloads only pinned Maven compiler inputs and invokes only
`scala.tools.nsc.Main`. Each of four compiler phases has a 300-second wall limit,
240-second CPU limit, 2 GiB Java heap, one active processor and bounded log files.
It does not invoke a hardware/helper main, discover tests, elaborate a model,
load native libraries, emit FIR/RTL, acquire weights/references or run profiles.
The CI workflow uploads no artifacts and runs against its exact triggering commit.
New CI classes are new build outputs, not the historical locally qualified binaries.

## What was checked before this TEMP source publication

- The nine production sources were compiled successfully. Forty-two unchanged
  companion classes retained their byte identity. The only changed prior class
  was the noninitializing `OriginalHostProfileProducer` object, plus five new
  observed-construction classes. Those two entrypoints have not run on the full Host.
- Seventeen native/helper sources were compiled into the corrected exclusive
  native closure. The ICG callback guard recognizes only the declared input and
  output clock names; it adds no clock/evaluation operation.
- The four lowering/rebinding sources passed compilation and eleven bounded
  tiny differential stages. Filename-only structured Info rebinding and omission
  of the final writer do not authorize a new full-Host identity or runtime.
- Local finite Matrix/ICG evidence covers direct/C-ABI/JNA tests, complete
  eighteen-frame bare/pair startup observations, and 500/539-frame scheduling
  assertions. The longer tests did not retain a full per-row trace. These scopes
  are not eight-way-service or full-Host acceptance.

The gate predicates, original annotation semantics, fresh 394 clock-init repair
checks, fixed original identity checks, session ownership and checked cleanup
remain in the source. Compilation does not satisfy any runtime predicate.

## Deliberately not packaged

This is a Scala bridge/source build, not a native-library build distribution.
Runtime use still needs independently qualified original Matrix/ICG/iDMA
libraries, actual owning admission/evidence, source-path provenance reconciliation
for the new checkout, and complete resource accounting. The original eight-way
service and broader iDMA finite witnesses, remaining facade negatives, full Host
construction/startup, profiles and final same-RTL replay are separate gates.

No local owner/admission plan, absolute-path catalog, private receipt, hardware
AST/FIR, generated RTL, native binary, weights, reference tensors or profile
outputs are published here. Unrun resource and logging drafts are excluded.
