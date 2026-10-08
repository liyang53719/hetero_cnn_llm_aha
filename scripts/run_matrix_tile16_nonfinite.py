#!/usr/bin/env python3
"""Run the actual payload/converter multirow guard, without Matrix arithmetic claims."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
    'rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv',
    'tb/tb_qwen2_matrix_tile16_nonfinite.sv',
)
EXPECTED = {0: (31, 0, 1), 1: (32, 18, 2)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_log(text):
    terminal = re.findall(r'^MATRIX_TILE16_NONFINITE_PASS (.*)$', text, flags=re.MULTILINE)
    require(terminal == ['actual_payload=1 actual_converter=1 matrix_arithmetic_claimed=0'],
            'missing, duplicated, or inaccurate payload acceptance marker')
    modes = re.findall(r'^MATRIX_TILE16_NONFINITE_MODE_PASS (.*)$', text, flags=re.MULTILINE)
    require(len(modes) == 2, 'missing or duplicated candidate/legacy inventory')
    result = {}
    for mode in modes:
        match = re.fullmatch(r'candidate=([01]) cases=(\d+) rejections=(\d+) resets=(\d+) write_stalls=(\d+)', mode)
        require(match is not None, 'malformed mode record')
        candidate, cases, rejections, resets, stalls = map(int, match.groups())
        require(candidate not in result, 'duplicated mode')
        require((cases, rejections, resets) == EXPECTED[candidate], 'directed case coverage drift')
        require(stalls > 0, 'write backpressure was not exercised')
        result[candidate] = dict(cases=cases, rejections=rejections, resets=resets, write_stalls=stalls)
    require(set(result) == set(EXPECTED), 'candidate/legacy coverage missing')
    return result


def find_verilator(explicit=None):
    selected = explicit or os.environ.get('VERILATOR_BIN') or shutil.which('verilator')
    if selected is None:
        fallback = ROOT / 'work/rope_hardware_oracle/bin/verilator'
        selected = str(fallback) if fallback.is_file() else None
    require(selected is not None, 'Verilator is unavailable; specify --verilator')
    resolved = shutil.which(str(selected))
    require(resolved is not None, 'selected Verilator is not executable')
    return str(Path(resolved).resolve())


def run(output, verilator=None):
    output = Path(output).resolve()
    require(not output.exists() or not any(output.iterdir()), 'output must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    executable = find_verilator(verilator)
    command = [executable, '--binary', '--timing', '-Wno-fatal', '-j', '2',
               '--top-module', 'tb_qwen2_matrix_tile16_nonfinite', '--Mdir', str(output / 'obj'), '-o', 'tb']
    command += [str(ROOT / p) for p in SOURCES]
    with (output / 'build.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    with (output / 'run.log').open('w') as log:
        subprocess.run([str(output / 'obj/tb')], check=True, stdout=log,
                       stderr=subprocess.STDOUT, timeout=30)
    inventory = verify_log((output / 'run.log').read_text())
    require(hashes == {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
            'payload sources changed during verification')
    result = dict(status='PASS_MATRIX_TILE16_NONFINITE_GUARD', modes=inventory,
                  source_sha256=hashes, build_command=command,
                  matrix_arithmetic_verified=False, full_chain_verified=False)
    (output / 'summary.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verilator')
    args = parser.parse_args()
    print(run(args.output, args.verilator)['status'])
