#!/usr/bin/env python3
"""Bounded synthetic-expression codegen only; no production/numerical acceptance."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import time

VERILATOR_ELF_SHA256 = '619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703'


def source(explicit_lanes=False):
    ports = [f'input logic [31:0] x{i}' for i in range(4096)]
    ports += ['input logic [3:0] row', 'input logic [2:0] beat', 'output logic [1023:0] y']
    head = 'module Probe(\n' + ',\n'.join(ports) + '\n);\n'
    if not explicit_lanes:
        return head + 'wire [131071:0] packed_tile = {' + ', '.join(
            f'x{i}' for i in reversed(range(4096))) + \
            "};\nassign y=packed_tile[{row,beat,10'b0} +: 1024];\nendmodule\n"
    body = []
    for lane in range(32):
        expr = "32'b0"
        for row in reversed(range(16)):
            selected = "32'b0"
            for beat in reversed(range(8)):
                selected = f"(beat == 3'd{beat} ? x{row*256+beat*32+lane} : {selected})"
            expr = f"(row == 4'd{row} ? {selected} : {expr})"
        body.append(f'wire [31:0] lane{lane} = {expr};')
    return head + '\n'.join(body) + '\nassign y = {' + ', '.join(
        f'lane{i}' for i in reversed(range(32))) + '};\nendmodule\n'


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verilator-bin', type=Path, required=True)
    p.add_argument('--runtime-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if hashlib.sha256(a.verilator_bin.read_bytes()).hexdigest() != VERILATOR_ELF_SHA256:
        raise ValueError('requires the actual frozen Verilator ELF')
    if a.output.exists() or a.output.is_symlink():
        raise ValueError('requires a fresh output directory')
    a.output.mkdir(parents=True)
    report = dict(scope='synthetic same-shape expression, not emitted production Scala',
                  numerical_acceptance=False, cpp_compilation=False, results=[])
    for label, threshold, explicit in [('expand64', 64, False),
                                       ('expand4096', 4096, False),
                                       ('explicit_lanes', 64, True)]:
        rtl = a.output / (label + '.sv')
        rtl.write_text(source(explicit))
        build = a.output / label
        command = [str(a.verilator_bin.resolve()), '--cc', '--top-module', 'Probe',
                   '--Mdir', str(build.resolve()), '--comp-limit-parens', '16',
                   '--output-split', '3000', '--output-split-cfuncs', '200',
                   '--expand-limit', str(threshold), str(rtl.resolve())]
        started = time.monotonic()
        with (a.output / (label + '.log')).open('w') as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                    timeout=100, preexec_fn=limits,
                    env=dict(os.environ, VERILATOR_ROOT=str(a.runtime_root.resolve())))
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 'TIMEOUT'
        files = sorted(build.glob('*.cpp'))
        report['results'].append(dict(label=label, returncode=code,
            elapsed_seconds=time.monotonic() - started, cpp_files=len(files),
            cpp_bytes=sum(x.stat().st_size for x in files),
            concat_wwi_calls=sum(len(re.findall(r'VL_CONCAT_WWI\(', x.read_text())) for x in files),
            argv=command, rlimit_as_bytes=2*1024**3, timeout_seconds=100,
            sv_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest()))
        (a.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        # Failure is preserved as a negative observation, never called a PASS.
        # The subsequent independent selector expression still has the same cap.
        print(json.dumps(report['results'][-1]), flush=True)


if __name__ == '__main__':
    main()
