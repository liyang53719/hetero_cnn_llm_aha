# Source-only regression reproduction

Published entry: `candidates/model_candidate_build_20261101/check_finite_long_regression.py`.

Dependency: a separate materialized source tree from fixed commit `75b9fc21e6d8a4a13bb82307969d9a0d9a953a79`, containing its exact SOURCE_PINS catalog and all 926 pinned source files. No tensors, generated SV, jars, simulator, or compiler are needed. The entry checks the hardcoded baseline catalog SHA and every pinned source hash/size before importing baseline code. It never fetches the baseline itself.

From the published candidate repository:

```
FINITE_LONG_BASELINE_REPO=/absolute/path/to/fixed75b9_source python -B candidates/model_candidate_build_20261101/check_finite_long_regression.py
FINITE_LONG_BASELINE_REPO=/absolute/path/to/fixed75b9_source python -B -O candidates/model_candidate_build_20261101/check_finite_long_regression.py
```

Each run enforces 64 MiB address space and 10 CPU seconds, executes 22 synthetic source/branch tests and prints results. It uses temporary fixtures only and writes no catalog, approval, budget or result file in the source tree. The synthetic compilation-proof boundary is explicit and grants no actual artifact authority. `-B` avoids bytecode files. Linux Python 3.11+ standard library is sufficient. Legacy existing tests use the new test-only inverse helper and its JSON; both are in SOURCE_PINS.

The independent candidate preparation scripts and large regression logs are audit materials, not required production inputs. This source-only revision includes the 34 reviewed source/test files and a precise TEMP plan and regression summary; it contains no running artifacts and makes no new readiness claim.
