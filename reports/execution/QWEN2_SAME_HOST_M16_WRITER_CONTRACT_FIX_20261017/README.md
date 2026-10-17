# Full-M16 writer-contract failure and narrow repair

Run [39003509172](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/39003509172)
on commit `46f57663bda24176c496c2c45440d230d9501362` ended with an owned
full-M16 child exit of 1 and completed cleanup. The producer again qualified in
79.354785 seconds. The combined attempt lasted 744.020100 seconds.

The failure-only diagnostic observed all public PCs 0 through 20 completed,
17 jobs, 21 completion handshakes and no reset request. The child's existing
summary reported `PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES`, with numerical elapsed
time 643.242548 seconds. These are diagnostic observations, not terminal acceptance.
The full-M16 terminal validator had not run, so this attempt remains failed and
does not qualify M128 or full 29-node acceptance.

The pinned traceback reaches the returned/disk equality check in fresh
`attention_packed_m16_same_host/entry.py` at line 49. The unchanged original runner
saves `encoded(report)` and returns the same report. Its host report includes
integer-PC-keyed `validated_policy_jobs`. JSON converts these keys to strings.
Canonical sorting before and after that round trip orders the keys differently:
integer 2 sorts before integer 12, while string "12" sorts before string "2".
The new boundary incorrectly treated that serialization effect as data drift.

The proposed correction keeps the strict, bounded, hash-bound JSON reader and
compares the disk bytes directly with the original source-pinned writer's encoding
of the returned report. It retains all terminal validation, source/snapshot checks,
admission replay, deadlines and parent exit/cleanup requirements. It changes no
numerical operation, tolerance, producer, library, model or budget. The M128 entry
has the same check and needs the same source-only correction before publication.

The four files under `actual/` are exact original artifact bytes, verified against
artifact `12090039191` with SHA256
`962e63e2cf700414149441a172334c606e21e2df04195389ba6df04c5193b0cc`.
`ACTUAL_FAILURE_ARCHIVE.json` binds their hashes and records the distinction between
observed progress, the source-proven boundary defect and ungranted acceptance.
No raw private log, tensor, weight or full private summary is published here.

This finding does not establish the inner cause of the earlier run 39001176206.
Its diagnostic evidence was unavailable, so that cause remains unknown.
