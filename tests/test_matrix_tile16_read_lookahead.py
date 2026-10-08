"""Direct real-payload owner/operand protocol checks, without Matrix arithmetic claims."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
    'rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv',
    'tb/tb_qwen2_matrix_tile16_read_lookahead.sv',
)
FIELDS = ('lookahead', 'cases', 'rejections', 'resets', 'prefetched', 'before',
          'same', 'after', 'held', 'cross', 'request_stalls', 'matrix_stalls', 'write_stalls')
TERMINAL = ('MATRIX_TILE16_READ_LOOKAHEAD_PASS actual_payload=1 strict_owner=1 '
            'operand_sequence=1 matrix_arithmetic_claimed=0')


def verify_log(text):
    """Fail closed on missing/duplicate modes, missing corner coverage or overclaims."""
    terminal = re.findall(r'^MATRIX_TILE16_READ_LOOKAHEAD_PASS.*$', text, re.MULTILINE)
    if terminal != [TERMINAL]:
        raise ValueError('missing, duplicated or inaccurate terminal acceptance')
    records = re.findall(r'^MATRIX_TILE16_READ_LOOKAHEAD_MODE_PASS (.*)$', text, re.MULTILINE)
    if len(records) != 2:
        raise ValueError('need exactly one baseline and one candidate mode')
    modes = {}
    pattern = ' '.join(rf'{field}=(\d+)' for field in FIELDS)
    for record in records:
        match = re.fullmatch(pattern, record)
        if not match:
            raise ValueError('malformed mode inventory')
        values = dict(zip(FIELDS, map(int, match.groups())))
        mode = values.pop('lookahead')
        if mode not in (0, 1) or mode in modes:
            raise ValueError('invalid or duplicated mode')
        if tuple(values[name] for name in ('cases', 'rejections', 'resets')) != (50, 14, 5):
            raise ValueError('directed case/rejection/reset coverage drift')
        if any(values[name] == 0 for name in ('request_stalls', 'matrix_stalls', 'write_stalls')):
            raise ValueError('missing backpressure coverage')
        lookahead_counts = [values[name] for name in ('prefetched', 'before', 'same', 'after', 'held', 'cross')]
        if mode == 0 and any(lookahead_counts):
            raise ValueError('baseline performed lookahead')
        if mode == 1 and not all(lookahead_counts):
            raise ValueError('missing candidate protocol corner coverage')
        if values['prefetched'] != values['before'] + values['same']:
            raise ValueError('inconsistent request admission counts')
        if values['after'] != values['cross']:
            raise ValueError('held request did not traverse MQ to ARQ once')
        modes[mode] = values
    return modes


def marker():
    return ('MATRIX_TILE16_READ_LOOKAHEAD_MODE_PASS lookahead=1 cases=50 rejections=14 resets=5 '
            'prefetched=136 before=93 same=43 after=39 held=320 cross=39 '
            'request_stalls=289 matrix_stalls=698 write_stalls=397\n'
            'MATRIX_TILE16_READ_LOOKAHEAD_MODE_PASS lookahead=0 cases=50 rejections=14 resets=5 '
            'prefetched=0 before=0 same=0 after=0 held=0 cross=0 '
            'request_stalls=158 matrix_stalls=697 write_stalls=407\n' + TERMINAL + '\n')


def test_complete_owner_protocol_inventory():
    modes = verify_log(marker())
    assert set(modes) == {0, 1}
    assert modes[1]['cases'] == 50


@pytest.mark.parametrize('old,new', [
    ('cases=50', 'cases=49'), ('rejections=14', 'rejections=13'), ('resets=5', 'resets=4'),
    ('prefetched=136', 'prefetched=0'), ('before=93', 'before=0'), ('same=43', 'same=0'),
    ('after=39', 'after=0'), ('held=320', 'held=0'), ('cross=39', 'cross=0'),
    ('request_stalls=289', 'request_stalls=0'), ('matrix_stalls=698', 'matrix_stalls=0'),
    ('write_stalls=397', 'write_stalls=0'), ('prefetched=0', 'prefetched=1'),
    ('lookahead=0', 'lookahead=1'), ('lookahead=0', 'lookahead=2'),
    ('actual_payload=1', 'actual_payload=0'), ('strict_owner=1', 'strict_owner=0'),
    ('operand_sequence=1', 'operand_sequence=0'),
    ('matrix_arithmetic_claimed=0', 'matrix_arithmetic_claimed=1'),
])
def test_missing_or_misrepresented_coverage_rejected(old, new):
    with pytest.raises(ValueError):
        verify_log(marker().replace(old, new))


@pytest.mark.parametrize('text', ['', marker() + marker(), '\n'.join(marker().splitlines()[1:])])
def test_truncated_duplicate_empty_inventory_rejected(text):
    with pytest.raises(ValueError):
        verify_log(text)


def test_actual_payload_baseline_and_lookahead(tmp_path):
    verilator = os.environ.get('VERILATOR_BIN') or shutil.which('verilator')
    if not verilator:
        fallback = ROOT / 'work/rope_hardware_oracle/bin/verilator'
        if fallback.is_file():
            verilator = str(fallback)
    if not verilator:
        pytest.skip('Verilator unavailable; set VERILATOR_BIN')
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    command = [verilator, '--binary', '--timing', '-Wno-fatal', '-j', '2',
               '--top-module', 'tb_qwen2_matrix_tile16_read_lookahead',
               '--Mdir', str(tmp_path / 'obj'), '-o', 'tb']
    command += [str(ROOT / p) for p in SOURCES]
    with (tmp_path / 'build.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    assert result.returncode == 0, (tmp_path / 'build.log').read_text()[-12000:]
    result = subprocess.run([str(tmp_path / 'obj/tb')], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (tmp_path / 'run.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout
    modes = verify_log(result.stdout)
    assert modes[1]['before'] >= 35 and modes[1]['same'] >= 35 and modes[1]['after'] >= 35
    assert hashes == {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
