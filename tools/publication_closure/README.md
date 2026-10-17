# Offline publication closure checker

This stdlib-only checker compares every expected repository path against saved
GitHub commit/tree evidence and locally reviewed bytes. It performs no network
requests, Git commands, source imports, package installation, or audited-code
execution. A local dependency map does not establish remote publication.

Use explicit commit and tree identities for every new candidate:

```sh
python -I -B tools/publication_closure/check_publication.py \
  --source-root REVIEWED_SOURCE_ROOT \
  --expected-map reports/execution/QWEN2_SAME_HOST_M16_PUBLICATION_REPAIR_20261017/REPAIRED_SOURCE_HASHES.json \
  --commit-json CANDIDATE_COMMIT_JSON \
  --tree-json CANDIDATE_TREE_PROOF_JSON \
  --expected-commit ACTUAL_CANDIDATE_COMMIT \
  --expected-tree ACTUAL_CANDIDATE_TREE \
  --out CANDIDATE_PUBLICATION_REPORT_JSON
```

Require exit zero, status PASS, all 379 expected paths present and zero missing,
mismatch, incomplete, local-invalid, or global errors. The candidate commit and
root tree must come from authenticated GitHub reads. The checker verifies saved
tree-object integrity and root binding, not the transport that obtained them or
whether the expected map describes every dependency. It defaults to the original
failed commit only when explicit candidate pins are omitted.

The tree input may be a complete recursive response or a required-prefix proof:

```json
{"schema":1,"profile":"github-required-prefix-tree-proof-v1","root_sha":"ACTUAL_TREE_SHA","trees":{"TREE_SHA":"complete nonrecursive GitHub response object"}}
```

The value shown as a string above is an explanatory placeholder; the actual
value must be the JSON response object, including sha, tree and truncated=false.
Fetch each required ancestor tree once and memoize it by SHA. Unrelated subtrees
may remain opaque; a missing required response is incomplete evidence, never
proof of file absence. Reuse an old response only when its tree SHA is unchanged
and its content hash verifies. GitHub transport failures are not absence proofs.

Run the portable tests from the repository root:

```sh
python -I -B -c 'import sys,unittest; sys.path.insert(0,"tools/publication_closure"); r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName("test_check_publication")); raise SystemExit(not r.wasSuccessful())'
```

Repeat with -O for optimized-mode validation. There are 35 portable tests plus
one original-evidence regression. The latter skips when the original saved
commit/tree proof and complete local freeze are not installed beside the test;
it is not silently replaced by a synthetic PASS. All 36 tests ran with zero
skips in both modes against the retained original evidence.

## Preserved first failure and minimal repair

The first run was 38997454218, attempt 1, at commit
96b0548f7241b4a4c98c44601ccdcc62fe9e9989. FAILURE.json records its sanitized error
and original job-log digest. It failed during source preflight before producer
setup, package installation, native execution, or full M16/M128 execution.

OLD_PUBLICATION_AUDIT.json records the independently verified 84-tree,
379-path audit: 378 exact matches and only one absent file,
candidates/qwen2_resident_matrix/portable_official_producer/gate.py.
The complete original log and transport responses remain retained separately;
this publication contains no tensor payload, credentials, or infrastructure log.

The runtime repair adds the exact previously reviewed gate, changes one workflow
comment to create a fresh commit-bound attempt, and rebinds that workflow hash
in input-contract.json. REPAIRED_SOURCE_HASHES.json is the reviewed 379-file
candidate map. Parent 45, worker 22, and workflow 10 cold tests passed normally
and optimized. Three isolated process entry probes passed without unittest or
numerical imports. The unchanged 357-file M16 composition was rechecked with a
fresh fixture-commit contract. None of those cold results is a producer or full
M16 numerical PASS.

Before updating the launch branch, audit the actual intended candidate Git
commit and tree with this checker. The old FAIL report and a repaired local
source directory do not establish publication completeness for a new commit.
The three-file runtime map contains a self-triggering workflow: moving the
branch is a launch action requiring the separate launch gate. Runtime source
contracts must bind the actual trigger commit rather than a fixture commit.
