#!/usr/bin/env python3
"""Extend a frozen real pinned-iDMA probe with alignment and masked-write tests.

Rebuild only the AXI test driver, not the Chisel DUT. Never overwrite existing
outputs. These are protocol/data tests, not Matrix MAC or full-model timing.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(out: Path) -> dict:
    require((out / 'simulation.exit').read_text().strip() == '0', 'simulator failed')
    raw = (out / 'run.log').read_bytes()
    text = raw.decode()
    lines = [x for x in text.splitlines() if x.startswith('IDMA_WEIGHT_BURST_EDGES_PASS ')]
    require(len(lines) == 1 and not re.search(r'FAIL|%Error|Fatal', text), 'incomplete edge run')
    values = dict(re.findall(r'(\w+)=(\d+)', lines[0]))
    expected = {'cases': 599, 'read_alignment_tail_cases': 528, 'prefix_write_cases': 64,
                'invalid_mask_cases': 5, 'compared_u32': 145984, 'alignment_read_beats': 8976,
                'alignment_transfers': 1326, 'data_mismatches': 0, 'real_pinned_idma': 1,
                'frozen_dut': 1}
    require(set(values) == set(expected) and all(int(values[k]) == v for k, v in expected.items()),
            'wrong edge coverage/counts')
    return {'schema': 1, 'status': 'PASS_REAL_IDMA_WEIGHT_BURST_EDGE_MATRIX',
            'counters': expected, 'log_sha256': hashlib.sha256(raw).hexdigest(),
            'rtl_rerun': True, 'full_model_inference': False, 'dc_timing': False}


def run(repo: Path, base: Path, out: Path) -> dict:
    require(not out.exists() and not out.is_symlink(), 'output must be new')
    require((base/'gate.exit').read_text().strip() == '0' and
            (base/'simulation.exit').read_text().strip() == '0', 'base probe did not pass')
    proof = json.loads((base/'RESULT.json').read_text())
    require(proof['status'] == 'PASS_REAL_IDMA_WEIGHT_BURST_PROBE', 'wrong base proof')
    paths = json.loads((base/'sources.sha256.json').read_text())
    require(len(paths) > 100, 'missing source identities')
    for name, value in paths.items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts and digest(repo/p) == value,
                'source changed: ' + name)
    project = repo/'chisel/continuous_prefill'
    runtime = Path(os.environ.get('VERILATOR_ROOT', str(base/'verilator-runtime')))
    libraries = [base/'obj/VIdmaWeightBurstProbe__ALL.a', base/'obj/verilated.o',
                 base/'obj/verilated_threads.o']
    source = project/'tests/idma_weight_burst_edges.cpp'
    files = libraries + [source, project/'tests/idma_weight_burst.cpp',
                         base/'generated/IdmaWeightBurstProbe.sv', Path(__file__).resolve()]
    before = {str(p): digest(p) for p in files}
    out.mkdir(parents=True)
    (out/'INPUTS_SHA256.json').write_text(json.dumps(before, indent=2)+'\n')
    command = ['g++', '-O3', '-std=c++17']
    for p in (base/'obj', runtime/'include', runtime/'include/vltstd', project/'tests'):
        command += ['-I'+str(p)]
    command += [str(source)] + list(map(str, libraries)) + ['-pthread', '-latomic', '-o', str(out/'VWeightBurstEdges')]
    (out/'BUILD_COMMAND.json').write_text(json.dumps(command, indent=2)+'\n')
    try:
        with (out/'build.log').open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        with (out/'run.log').open('xb') as log:
            process = subprocess.run([str(out/'VWeightBurstEdges')], stdout=log,
                                     stderr=subprocess.STDOUT, timeout=300)
        (out/'simulation.exit').write_text(str(process.returncode)+'\n')
        result = verify(out)
        require(before == {name: digest(Path(name)) for name in before}, 'test input mutated')
        result.update(source_files_verified=len(paths), inputs_sha256=before)
        (out/'RESULT.json').write_text(json.dumps(result, indent=2)+'\n')
        (out/'gate.exit').write_text('0\n')
        return result
    except Exception:
        (out/'gate.exit').write_text('1\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.repo.resolve(), args.base.resolve(), args.output.resolve()), indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise SystemExit('WEIGHT_BURST_EDGES_REJECTED: '+str(exc))
