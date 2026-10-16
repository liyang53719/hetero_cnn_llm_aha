# Public M128: two CPU-unsuitable placements

This is a failed-run evidence checkpoint. Both placements of run
[38963767257](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38963767257)
at commit `be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5` stopped with
`CPU_UNSUITABLE` in `cpu_qualification`, before clone, setup, or numerical work.
No Public numerical acceptance, native backend qualification, full-29-node
acceptance, Scala execution, or RTL execution is established.

- Placement 1: job `117185037810`, artifact `12074126444`, elapsed `0.124065` seconds.
  Four processor records; required `avx512_bf16` absent.
- Placement 2: job `117185359078`, artifact `12073288607`, elapsed `0.099335` seconds.
  Four processor records; required `avx512_bf16`, `avx512bw`, `avx512dq`,
  `avx512f`, and `avx512vl` absent.
- Both report `fma=true`; all three excluded AMX flags are false.
  These are the original CPU-flag eligibility summaries, not backend dispatch tests.

## Provenance and source boundary

Only these two artifacts were downloaded through the connected GitHub artifact
tool. Their ZIP identities were checked before reading their exact allowlisted
three members:

- Placement 1: 15,365 bytes, SHA256
  `3b4c54aa75890bb2679df92dc53c8dd3875e993b250a8737c514f5375b34736a`
- Placement 2: 15,364 bytes, SHA256
  `ab1e1cbe2c58a58438185d53c34afbe79aafe42fcfeff94b81360abcb373a698`

Each placement directory preserves the original `summary.json`, `progress.json`,
and `source_hashes.json` bytes unchanged. No weights, numerical arrays, private
logs, or ZIP archives are committed. The three diagnostic frames are fixed
source/line metadata. `checkpoint.json` records exact hashes, sizes, identities,
and the narrow failed-run interpretation. IDs are supplied provenance; offline
SHA256 validation confirms the supplied byte identity rather than independently
authenticating GitHub origin.

The source manifests are byte-identical and bind 285 original source identities,
12 expected generated identities, and launch-contract SHA256
`b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b`.
All 285 source hashes were checked against immutable Git blobs at the named
commit, tree `07cdd8b1bc7508da7b587fc8465d4e8026f67731`. The 12 generated hashes
match the pinned contract; neither failed placement reached clone/composition.
The source-order check confirms CPU qualification precedes private clone/setup.
No source-only proof or historical successful run is promoted to new numerical
acceptance. The newly added numeric-progress diagnostics were never reached.

This archive is outside that 285-source closure. It changes no frozen evidence,
source contracts, workflows, runtime, arithmetic, dispatch, or acceptance gates.

## Cold verification

From the repository root:

```sh
D=candidates/qwen2_resident_matrix/raw_kv_public_recipe_cpu_unsuitable
python3 -B "$D/validate_evidence.py"
python3 -B -m unittest discover -s "$D" -p 'test_*.py' -v
python3 -B -O -m unittest discover -s "$D" -p 'test_*.py' -v
python3 -B -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_cpu_unsuitable.test_evidence -v
python3 -B -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_cpu_unsuitable.test_evidence -v
```

Optional original ZIPs and clean historical source bytes can be verified too:

```sh
python3 -B "$D/validate_evidence.py" \
  --zip-1 /path/to/public-m128-job117185037810.zip \
  --zip-2 /path/to/public-m128-job117185359078.zip \
  --source-tree /path/to/clean-be00-source-tree
```

The optional source-tree check reads and hashes all 285 source files and checks
the generated-hash map against the pinned contract. It executes none of their
code and does not itself authenticate the tree's Git commit. A composed tree
with 12 generated overlays will correctly fail the original-source hash check.
The check has 2 MiB per-file and 32 MiB total source limits.

Validation uses only Python's standard library. It rejects changed member bytes,
missing/unknown fields, duplicate keys, non-finite values, boolean/number type
confusion, oversized/deep JSON, unsafe source paths, changed source identities,
ZIP extras/duplicates/links, filesystem links/special files, extra archive files,
and synthetic PASS/acceptance claims. Enforcement survives `python -O`.
Cold success reports `CPU_UNSUITABLE` with `numerical_acceptance=false`.
It never installs packages, reruns CI, imports numerical/native modules, runs
setup, uses the network/Git/subprocesses, or executes Scala/RTL.

Tests copy exactly the ten intended files into a temporary fixture, allowing
ordinary unittest package/discovery use even when Python creates `__pycache__`.
The archive validator deliberately rejects caches and every other extra entry;
use `-B` and publish only the ten intended files.
