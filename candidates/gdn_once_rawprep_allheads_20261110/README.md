# One RawPrep, same-instance head scheduling

`python run.py --jar-dir <pinned-jars> --verilator-dir <bin-dir> --heads 2 --cycles 16000000 --wall-seconds 600` reproduces the verified two-head run. Heads are runtime configuration, not elaboration. RawPrep executes once for fixed16head layout; the same owners and physical scalar/bank are reused without reset. Full16 run requires the longer separately recorded CPU/wall limits; do not infer full16 from heads2. See Chinese plan/SUMMARY for numeric scope and static final-line counter-label erratum.
