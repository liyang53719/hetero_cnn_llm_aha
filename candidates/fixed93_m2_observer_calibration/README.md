# M2 calibration: portable source-review bundle

This is a small, source-only snapshot of the frozen 0417 calibration code. The
14 files in `source/` are byte-for-byte originals, verified against the frozen
source manifest. Relative paths in `MANIFEST.json` and `SHA256SUMS` make source
validation independent of the original machine. These hashes establish internal
integrity and source correspondence, not an external signature or run receipt.

## The only supported command in this bundle

From this directory, using Python 3.10 or newer:

    python -I -S -B verify_sources.py --self-test

This stdlib-only checker verifies the allowlisted relative file inventory,
lengths and SHA-256 hashes; scans the captured sources for private absolute path
literals; and compiles Python to memory without importing or executing any
captured module. Its small self-tests operate on synthetic values in memory.
It does not write bytecode or files, load a model/native library, start a child
process, import the DUT, or run an actual calibration. A passing result is only
`PASS_SOURCE_COMPILE_HASH_ONLY`.

## Contents and deliberate omissions

- `source/`: exact original harness, authority/supervision/IO boundaries,
  observer, native adapter, comparison and bounded-check source for inspection.
- `MANIFEST.json`: relative source and document pins; frozen manifest digest.
- `SHA256SUMS`: hashes including `MANIFEST.json` (not self-referential).
- `SCOPE.json`: descriptive review scope, expressly not an executable budget.
- `SUMMARY.md`: limited, source-bound observations and final independent review scope.

Original `tests.py`, the two preflight programs, and every original execution
entry point are included as source to inspect, not as portable test commands.
Do not run them as part of source validation. In particular, their dependencies,
authority expectations and environment assumptions have not been supplied.

No original manifests containing machine paths, original budget/policy files,
ADMISSION or lease, raw logs, routes, arrays, payloads, weights, runtime trees,
ELF files or original run evidence are included. No authority is generated here.

## Before any actual execution

A caller must separately supply and review the exact baseline/dependency source,
runtime and native-library identities; a machine-specific budget and IO/read
projection; independent qualification receipts; a fresh output namespace; and
explicit new execution authority bound to those exact inputs. Rebuild and review
all required manifests in the target environment. Merely placing files beside
this bundle or changing paths does not make a runnable or authorized package.
No old admission, run permission or numerical acceptance is inherited.

The historical two-arm scope was one shared 120-second envelope: 105 seconds
work, 5 seconds cleanup, 10 seconds post-processing; one CPU; 2 GiB sampled
group RSS/address-space caps; and 80 MiB total owned output. Old then new ran in
fresh processes. These limits describe that scope, not a grant to repeat it,
a timing promise, or the resource requirement of this tiny checker.

## Path review

The 14 originals were scanned in full text and parsed string literals. No private
machine workspace/home/native-library paths were found. Byte-for-byte source
preservation retains generic Linux proc/tool paths, the `/root` authority
principal string, and explicitly synthetic test paths. These are not supplied
runtime paths or transferable permissions. The checker is a bounded static
sanity check, not proof that arbitrary future edits cannot construct a path.
