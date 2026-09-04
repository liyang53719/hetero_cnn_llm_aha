#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROJECT="$ROOT/chisel/three_model_operator_primitives"
OUT="$ROOT/work/generated/three_model_operator_primitives"
RESULTS="$ROOT/work/results/three_model_operator_primitives"
REPORT="$ROOT/reports/execution/OPERATOR_PRIMITIVE_COVERAGE_V3.json"
SBT_LAUNCH_JAR=${SBT_LAUNCH_JAR:-"$ROOT/work/toolchain/sbt-launch-1.10.2.jar"}

mkdir -p "$OUT" "$RESULTS" "$(dirname "$SBT_LAUNCH_JAR")" "$(dirname "$REPORT")"

if [[ ! -f "$SBT_LAUNCH_JAR" ]]; then
  curl -fL --retry 4 --retry-delay 2 \
    https://repo1.maven.org/maven2/org/scala-sbt/sbt-launch/1.10.2/sbt-launch-1.10.2.jar \
    -o "$SBT_LAUNCH_JAR"
fi

python3 "$ROOT/scripts/audit_three_model_operator_primitives.py" \
  > "$RESULTS/source_audit.log"
python3 -m pytest -q "$ROOT/tests/test_three_model_operator_primitives.py" \
  > "$RESULTS/python_tests.log"

pushd "$PROJECT" >/dev/null
java -Xmx4g -jar "$SBT_LAUNCH_JAR" clean compile test \
  > "$RESULTS/chisel_test.log" 2>&1
java -Xmx4g -jar "$SBT_LAUNCH_JAR" \
  "runMain heteronpu.operator.OperatorProgramChecks" \
  > "$RESULTS/program_checks.log" 2>&1
java -Xmx4g -jar "$SBT_LAUNCH_JAR" \
  "runMain heteronpu.operator.EmitOperatorPrimitives $OUT" \
  > "$RESULTS/emitter.log" 2>&1
popd >/dev/null

python3 "$ROOT/scripts/audit_three_model_operator_primitives.py" \
  --generated "$OUT" --output "$REPORT" \
  > "$RESULTS/generated_audit.log"

sv_count=$(find "$OUT" -maxdepth 1 -type f -name '*.sv' | wc -l | tr -d ' ')
[[ "$sv_count" == "18" ]]

git -C "$ROOT" diff --check
python3 - <<'PY'
from pathlib import Path
import hashlib, json, os
root = Path(os.environ.get("ROOT_FOR_RESULT", ".")).resolve()
if not (root / "chisel").is_dir():
    root = Path(__file__).resolve() if "__file__" in globals() else Path.cwd()
    while root != root.parent and not (root / "chisel").is_dir():
        root = root.parent
out = root / "work/generated/three_model_operator_primitives"
result = root / "work/results/three_model_operator_primitives/result.json"
sv = sorted(out.glob("*.sv"))
payload = {
    "schema_version": 3,
    "status": "PASS_SANDBOX_CHISEL_COMPILE_TEST_EMIT",
    "target_clock_hz": 800000000,
    "target_period_ns": 1.25,
    "generated_sv_count": len(sv),
    "generated_sv": [p.name for p in sv],
    "manifest_sha256": hashlib.sha256((out / "MANIFEST.txt").read_bytes()).hexdigest(),
    "coverage_sha256": hashlib.sha256((out / "OPERATOR_COVERAGE.csv").read_bytes()).hexdigest(),
}
result.parent.mkdir(parents=True, exist_ok=True)
result.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, indent=2, sort_keys=True))
PY

echo "PASS_THREE_MODEL_OPERATOR_PRIMITIVES target=800MHz roots=18 report=$REPORT"
