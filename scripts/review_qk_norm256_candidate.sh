#!/usr/bin/env bash
# Independent analytical adversarial checks and original-core cycle miter.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-work/qk_norm256_independent_review}
V=${VERILATOR_BIN:-work/rope_hardware_oracle/bin/verilator}
GENERATED=${GENERATED_RTL:-work/generated/qk_norm256_candidate/HeteroRoPEHardwarePrimitives.sv}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
python3 - "$OUT" <<'PY'
import hashlib,pathlib,sys
source=pathlib.Path('tests/fixtures/qk_norm256_legacy/fp32_rmsnorm256_chunked.sv').read_bytes()
if hashlib.sha256(source).hexdigest() != 'e866318664e96dcf1eb9f1a7bf6e544ead95096ec1114e4373077a7ba3e3df12':
    raise SystemExit('original core hash drift')
text=source.decode().replace('module fp32_rmsnorm256_chunked(', 'module fp32_rmsnorm256_chunked_legacy_review(')
(pathlib.Path(sys.argv[1])/'legacy_review.sv').write_text(text)
PY
COMMON=("$GENERATED" rtl/sfu/fp32_reduce16.sv rtl/sfu/fp32_rsqrt_nr.sv rtl/sfu/fp32_rmsnorm256_chunked.sv)
"$V" --binary --timing -Wno-fatal -j "${JOBS:-1}" -CFLAGS -O0 --top-module tb_independent_qk_adversarial --Mdir "$OUT/obj_adversarial" -o tb "${COMMON[@]}" rtl/sfu/fp32_to_bf16_rne_candidate.sv rtl/sfu/qk_norm256_bf16_candidate.sv tb/qk_norm256_review/tb_independent_qk_adversarial.sv > "$OUT/adversarial_build.log" 2>&1
"$OUT/obj_adversarial/tb" > "$OUT/adversarial_run.log" 2>&1
"$V" --binary --timing -Wno-fatal -j "${JOBS:-1}" -CFLAGS -O0 --top-module tb_independent_legacy_miter --Mdir "$OUT/obj_legacy" -o tb "${COMMON[@]}" "$OUT/legacy_review.sv" tb/qk_norm256_review/tb_independent_legacy_miter.sv > "$OUT/legacy_build.log" 2>&1
"$OUT/obj_legacy/tb" > "$OUT/legacy_run.log" 2>&1
cat "$OUT/adversarial_run.log" "$OUT/legacy_run.log"
grep -q '^INDEPENDENT_QK_ADVERSARIAL_PASS checked=60 reset_flushes=10$' "$OUT/adversarial_run.log"
grep -q '^INDEPENDENT_DEFAULT_LEGACY_MITER_PASS transactions=64 cycles=20573$' "$OUT/legacy_run.log"
