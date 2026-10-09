"""Adversarial seven-command artifact audits with synthetic logs and DDR only.

These tests never instantiate a DUT, build a reference, run Scala/Verilator,
or claim numerical acceptance. Distinct stage bytes expose false preservation
and predecessor claims; raw physical snapshots independently carry the writes.
"""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import host_bf16_qkv_rope_fixture as fixture
import host_bf16_qkv_rope_execution as execution


PREFIX = 'HOST_QKV_ROPE_'
NAMES = ('q', 'k', 'v', 'norm_q', 'gate', 'norm_k', 'rope_q', 'rope_k')
WIDTHS = (4096, 512, 512, 2048, 2048, 512, 2048, 512)
PRODUCERS = {3: 0, 4: 1, 5: 3, 6: 4}


@pytest.fixture
def tmp_path():
    # The physical DDR image is deliberately complete. Reclaim each case's
    # sizeable snapshots immediately, including when an assertion fails.
    with tempfile.TemporaryDirectory(prefix='qkv_rope_unit_') as temporary:
        yield Path(temporary)


def bursts(begin, length):
    end = begin + length
    while begin < end:
        size = min(1024, end - begin, 4096 - begin % 4096)
        yield begin, size
        begin += size


def words(size, start):
    return (start + np.arange(size, dtype=np.uint16) % 32).astype('<u2')


def synthetic_fixture(path, case):
    """Use the public descriptor layout with explicitly artificial evidence."""
    first, position = (0, 0) if case == 'cold0' else (127, 255)
    arrays = {
        'packed_q': words(4096, 0x3F00), 'k': words(512, 0x3F40),
        'v': words(512, 0x3FC0), 'norm_q': words(2048, 0x4000),
        'norm_k': words(512, 0x4080),
    }
    arrays['gate'] = arrays['packed_q'].reshape(8, 512)[:, 256:].copy().ravel()
    for role, heads in (('q', 8), ('k', 2)):
        value = arrays['norm_' + role].reshape(heads, 256).copy()
        value[:, :64] += 1
        arrays['rope_' + role] = value.ravel()
        arrays['native_norm_' + role] = arrays['norm_' + role].copy()
        arrays['native_rope_' + role + '_prefix'] = value[:, :64].copy().ravel()
    arrays.update(q_gamma=words(256, 0x3C00), k_gamma=words(256, 0x3C40),
                  trig=words(64, 0x3E00))
    payload = {name + '.bf16le': value.tobytes() for name, value in arrays.items()}
    original = {'activation.bf16le': words(128 * 1024, 0x3F00).tobytes()}
    for role, width, name in zip('qkv', WIDTHS[:3], ('packed_q', 'k', 'v')):
        original['weight_' + role + '.bf16le'] = words(1024 * width, 0x3C00).tobytes()
        original['native_' + role + '.bf16le'] = np.tile(arrays[name], 128).tobytes()
    failures = {variant: {'gate_pass': False, 'status': 'BLOCKED_BF16_PRODUCER_GATE',
                           'failed_producers': [{'producer': 'synthetic-only', 'pass': False}]}
                for variant in ('baseline', 'avx2')}
    owner = dict(token_base=first, positionBase=position,
                 native_full_block_failures=failures, host_provenance={},
                 independent_reference={'status': 'SYNTHETIC_UNIT_TEST_ONLY'})
    with patch.object(fixture, 'retained', return_value=(owner, payload, original)), \
            patch.object(fixture, 'source_identity', return_value={'synthetic-only': '0' * 64}):
        files, receipt = fixture.contents(case)
    path.mkdir()
    for name, raw in files.items():
        (path / name).write_bytes(raw)
    (path / 'manifest.json').write_text(json.dumps(receipt))
    return path


def fake_artifacts(root, case='carried127', mode='pass'):
    """Forge a transparent unit-only transcript, never hardware evidence."""
    source = synthetic_fixture(root / 'fixture', case)
    h, commands, spans = fixture.layout(source)
    output = root / 'outputs'
    output.mkdir()
    lines, cycle = [], 0

    def event(kind, **fields):
        lines.append(PREFIX + kind + ' ' + ' '.join(f'{key}={value}' for key, value in fields.items()))

    for run, selected in enumerate((mode, 'pass') if mode == 'reset-recovery' else (mode,)):
        directory = output if run == 0 else output / 'recovery'
        directory.mkdir(exist_ok=True)
        memory = execution._initial(source, h, commands, spans, selected)
        references = {span['name']: (source / ('independent_' + span['name'] + '.bf16le')).read_bytes()
                      for span in spans}
        for name, raw in references.items():
            (directory / ('reference_' + name + '.bf16le')).write_bytes(raw)
        failed = 1 if selected == 'output-alias' else 0 if selected == 'reset-recovery' else 3 if selected == 'gate-write-error' else 6
        successful = 7 if selected == 'pass' else failed
        completions = 7 if selected == 'pass' else failed + 1
        fault_status = 9 if selected == 'output-alias' else 3
        ack_total = accepted_total = write_bursts = dependency_bytes = dependency_bursts = 0
        event('BEGIN', run=run, mode=selected, epoch=9 + run, commands=7)
        for pc in range(completions):
            command = commands[pc]
            selected_spans = spans[command['span_first']:command['span_first'] + command['span_count']]
            ok = pc < successful
            if pc >= 3:
                for address, size in bursts(command['input'], command['input_bytes']):
                    cycle += 1
                    event('READ_DEP', run=run, pc=pc, cycle=cycle, address=address, bytes=size, producer=PRODUCERS[pc])
                    dependency_bytes += size
                    dependency_bursts += 1
            ack = accepted = 0
            if ok or selected in ('last-write-error', 'gate-write-error'):
                total = sum(span['bytes'] for span in selected_spans)
                for span in selected_spans:
                    for address, size in bursts(span['begin'], span['bytes']):
                        accepted += size
                        final = int(accepted == total)
                        cycle += 1
                        event('WRITE_REQUEST', run=run, pc=pc, cycle=cycle, address=address, bytes=size, final=final)
                        cycle += 64
                        error = int(not ok and final)
                        event('WRITE_ACK', run=run, pc=pc, cycle=cycle, address=address, bytes=size, error=error, final=final)
                        write_bursts += 1
                        accepted_total += size
                        if not error:
                            offset, start = address - h['base'], address - span['begin']
                            memory[offset:offset + size] = references[span['name']][start:start + size]
                            ack += size
                            ack_total += size
            status = 0 if ok else fault_status
            word = pc | command['engine'] << 29 | status << 32 | (pc + 1) << 40
            for _ in range(11):
                cycle += 1
                event('HOLD', run=run, pc=pc, cycle=cycle, word=word)
            cycle += 1
            event('COMMAND', run=run, pc=pc, cycle=cycle, engine=command['engine'],
                  status=status, signal=pc + 1, ack_bytes=ack, published=int(ok))
            (directory / f'writable_after_command{pc}.bin').write_bytes(memory[h['scratch'] - h['base']:])
        (directory / 'ddr_after.bin').write_bytes(memory)
        for span in spans:
            start = span['begin'] - h['base']
            (directory / ('actual_' + span['name'] + '.bf16le')).write_bytes(memory[start:start + span['bytes']])
        for _ in range(7):
            cycle += 1
            event('RESULT_HOLD', run=run, cycle=cycle, epoch=9 + run, pc=completions - 1,
                  status=0 if selected == 'pass' else fault_status, completed=successful)
        metadata = sum(1 + command['records'] for command in commands[:completions])
        read_bursts = metadata + dependency_bursts
        read_beats = metadata + dependency_bytes // 64
        published = sum(span['bytes'] for span in spans if span['pc'] < successful)
        macs = sum(WIDTHS[:min(3, successful)]) * 1024
        event('END', run=run, status=0 if selected == 'pass' else fault_status, epoch=9 + run,
              result_pc=completions - 1, completions=completions, successful=successful,
              issued_jobs=1 if selected == 'output-alias' else completions,
              metadata_reads=metadata, read_beats=read_beats, read_ack_beats=read_beats,
              write_beats=accepted_total // 64, write_ack_beats=accepted_total // 64,
              ack_bytes=ack_total, published_bytes=published, useful_macs=macs,
              idma_transfers=read_bursts + write_bursts, read_bursts=read_bursts,
              write_bursts=write_bursts, reset_required=int(selected != 'pass'))
    if mode == 'reset-recovery':
        event('RECOVERY', same_dut=1, unchanged_ddr=1, reference_injection=0, commands=7)
    log = root / 'driver.log'
    log.write_text('\n'.join(lines) + '\n')
    return source, output, log, h, commands, spans


def audit(artifacts, mode='pass'):
    source, output, log, *_ = artifacts
    return execution.verify_execution(source, output, log, mode, admit=False)


def change_line(text, kind, *, pc=None, field, value):
    rows = text.splitlines()
    for i, row in enumerate(rows):
        if row.startswith(PREFIX + kind + ' ') and (pc is None or f'pc={pc}' in row.split()):
            rows[i] = ' '.join(f'{field}={value}' if word.startswith(field + '=') else word for word in row.split())
            return '\n'.join(rows) + '\n'
    raise AssertionError('test event not found')


@pytest.mark.parametrize('case', ['cold0', 'carried127'])
def test_pass_is_artifact_diagnostic_not_dut_or_numerical_evidence(tmp_path, case):
    artifacts = fake_artifacts(tmp_path, case)
    result = audit(artifacts)
    assert result['actual_dut_identity_verified'] is False
    assert result['numerical_acceptance_eligible'] is False
    assert result['full_block_supported'] is False
    assert all(not record['gate_pass'] for record in result['native_full_block_failures'].values())
    assert result['runs'][0]['successful_commands'] == 7
    assert result['runs'][0]['ack_bytes'] == result['runs'][0]['published_bytes'] == 24576
    h, commands, spans = artifacts[3:]
    assert h['first'] == (0 if case == 'cold0' else 127)
    assert h['position'] == (0 if case == 'cold0' else 255)
    assert sum(command['records'] for command in commands) == 114
    assert sum(1 + command['records'] for command in commands) == 121
    assert sum(span['bytes'] for span in spans) == 24576
    assert [span['name'] for span in spans] == list(NAMES)


@pytest.mark.parametrize('mode', ['last-write-error', 'activation-read-error', 'weight-read-error',
                                 'gate-write-error', 'output-alias', 'reset-recovery'])
def test_fault_artifacts_preserve_unpublished_and_prior_outputs(tmp_path, mode):
    artifacts = fake_artifacts(tmp_path, mode=mode)
    result = audit(artifacts, mode)
    assert result['actual_dut_identity_verified'] is False
    assert result['numerical_acceptance_eligible'] is False
    successful = 1 if mode == 'output-alias' else 0 if mode == 'reset-recovery' else 3 if mode == 'gate-write-error' else 6
    assert result['runs'][0]['successful_commands'] == successful
    if mode == 'gate-write-error':
        assert result['runs'][0]['published_bytes'] == 10240
        assert result['runs'][0]['ack_bytes'] > 10240
    if mode == 'reset-recovery':
        assert result['runs'][0]['ack_bytes'] == 0
        assert result['runs'][1]['successful_commands'] == 7
        assert result['runs'][1]['ack_bytes'] == 24576


def test_initial_memory_contains_no_reference_outputs_and_sparse_absolute_trig(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    source, _, _, h, commands, spans = artifacts
    memory = execution._initial(source, h, commands, spans, 'pass')
    sentinel = bytes.fromhex('3cc35aa5')
    for span in spans:
        start = span['allocation'] - h['base']
        assert memory[start:start + span['allocation_bytes']] == sentinel * (span['allocation_bytes'] // 4)
    start = h['trig'] - h['base']
    assert memory[start:start + 255 * 128] == sentinel * (255 * 32)
    assert memory[start + 255 * 128:start + 256 * 128] == (source / 'trig.bf16le').read_bytes()


def test_event_inventory_identity_and_accounting_tampering_rejected(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    log = artifacts[2]
    original = log.read_text()
    command = next(row for row in original.splitlines() if row.startswith(PREFIX + 'COMMAND '))
    mutations = [original + PREFIX + 'INVENTED pass=1\n',
                 original.replace(command, command + '\n' + command),
                 original.replace(command + '\n', ''),
                 original.replace(command, command + ' ack_bytes=8192'),
                 original.replace(command, command + ' invented=1')]
    for kind, pc, field, value in (
        ('COMMAND', 3, 'engine', 2), ('COMMAND', 3, 'signal', 3),
        ('COMMAND', 3, 'ack_bytes', 4096), ('COMMAND', 3, 'published', 0),
        ('READ_DEP', 5, 'producer', 0), ('READ_DEP', 6, 'producer', 3),
        ('RESULT_HOLD', None, 'epoch', 10), ('RESULT_HOLD', None, 'pc', 5),
        ('RESULT_HOLD', None, 'completed', 6), ('END', None, 'metadata_reads', 120),
        ('END', None, 'ack_bytes', 20480), ('END', None, 'published_bytes', 20480),
        ('END', None, 'idma_transfers', 0), ('END', None, 'write_ack_beats', 0),
        ('END', None, 'reset_required', 1),
    ):
        mutations.append(change_line(original, kind, pc=pc, field=field, value=value))
    for changed in mutations:
        log.write_text(changed)
        with pytest.raises(ValueError):
            audit(artifacts)


def test_dependency_read_cannot_use_native_or_wrong_token_address(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    log, h, commands, spans = artifacts[2:]
    original = log.read_text()
    for address in (h['aa'], spans[3]['allocation'], spans[4]['begin'], commands[5]['input'] + commands[5]['input_bytes']):
        log.write_text(change_line(original, 'READ_DEP', pc=5, field='address', value=address))
        with pytest.raises(ValueError):
            audit(artifacts)
    log.write_text('\n'.join(row for row in original.splitlines()
                             if not (row.startswith(PREFIX + 'READ_DEP ') and 'pc=5' in row.split())) + '\n')
    with pytest.raises(ValueError):
        audit(artifacts)


def test_aggregate_read_counters_include_logged_predecessor_traffic(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    log = artifacts[2]
    original = log.read_text()
    end = next(row for row in original.splitlines() if row.startswith(PREFIX + 'END '))
    fields = dict(word.split('=', 1) for word in end.split()[1:])
    changed = original
    for field, value in (('read_beats', 121), ('read_ack_beats', 121), ('read_bursts', 121),
                         ('idma_transfers', 121 + int(fields['write_bursts']))):
        changed = change_line(changed, 'END', field=field, value=value)
    log.write_text(changed)
    with pytest.raises(ValueError):
        audit(artifacts)


def test_early_duplicate_ack_and_nonstable_completion_rejected(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    log = artifacts[2]
    original = log.read_text()
    rows = original.splitlines()
    request = next(i for i, row in enumerate(rows) if row.startswith(PREFIX + 'WRITE_REQUEST ') and 'pc=3' in row.split() and 'final=1' in row.split())
    request_cycle = int(dict(word.split('=', 1) for word in rows[request].split()[1:])['cycle'])
    ack = rows[request + 1]
    changed_ack = ' '.join('cycle=' + str(request_cycle + 1) if word.startswith('cycle=') else word for word in ack.split())
    hold_rows = [row for row in rows if row.startswith(PREFIX + 'HOLD ') and 'pc=3' in row.split()]
    first_hold = hold_rows[0]
    mutations = [original.replace(ack, changed_ack), original.replace(ack, ack + '\n' + ack),
                 original.replace(ack + '\n', ''), original.replace(hold_rows[1], first_hold),
                 change_line(original, 'HOLD', pc=3, field='word', value=0),
                 original.replace(first_hold + '\n', '').replace(ack, first_hold + '\n' + ack)]
    for changed in mutations:
        log.write_text(changed)
        with pytest.raises(ValueError):
            audit(artifacts)


def test_primary_norm_ack_cannot_publish_before_gate_ack(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    log, _, _, spans = artifacts[2:]
    original = log.read_text()
    gate = spans[4]
    rows = []
    for row in original.splitlines():
        if row.startswith((PREFIX + 'WRITE_REQUEST ', PREFIX + 'WRITE_ACK ')):
            fields = dict(word.split('=', 1) for word in row.split()[1:])
            if gate['begin'] <= int(fields['address']) < gate['begin'] + gate['bytes']:
                continue
        rows.append(row)
    log.write_text('\n'.join(rows) + '\n')
    with pytest.raises(ValueError):
        audit(artifacts)


@pytest.mark.parametrize('mode', ['activation-read-error', 'weight-read-error'])
def test_first_read_fault_cannot_hide_successful_partial_writes(tmp_path, mode):
    artifacts = fake_artifacts(tmp_path, mode=mode)
    source, output, log, h, _, spans = artifacts
    address = spans[7]['begin']
    rows = log.read_text().splitlines()
    index = next(i for i, row in enumerate(rows)
                 if row.startswith(PREFIX + 'HOLD ') and 'pc=6' in row.split())
    cycle = int(dict(word.split('=', 1) for word in rows[index].split()[1:])['cycle'])
    for i in range(index, len(rows)):
        rows[i] = ' '.join('cycle=' + str(int(word.split('=')[1]) + 3)
                           if word.startswith('cycle=') else word for word in rows[i].split())
    rows[index:index] = [
        f'{PREFIX}WRITE_REQUEST run=0 pc=6 cycle={cycle} address={address} bytes=64 final=0',
        f'{PREFIX}WRITE_ACK run=0 pc=6 cycle={cycle + 1} address={address} bytes=64 error=0 final=0',
    ]
    changed = change_line('\n'.join(rows) + '\n', 'COMMAND', pc=6, field='ack_bytes', value=64)
    end = next(row for row in changed.splitlines() if row.startswith(PREFIX + 'END '))
    fields = dict(word.split('=', 1) for word in end.split()[1:])
    for field in ('ack_bytes', 'write_beats', 'write_ack_beats', 'write_bursts', 'idma_transfers'):
        changed = change_line(changed, 'END', field=field,
                              value=int(fields[field]) + (64 if field == 'ack_bytes' else 1))
    log.write_text(changed)
    reference = (source / 'independent_rope_k.bf16le').read_bytes()[:64]
    # Make every raw output agree with the forged ACK; the fault contract must
    # reject this even though ordinary byte reconstruction is self-consistent.
    for name, offset in (('ddr_after.bin', address - h['base']),
                         ('writable_after_command6.bin', address - h['scratch']),
                         ('actual_rope_k.bf16le', 0)):
        path = output / name
        raw = bytearray(path.read_bytes())
        raw[offset:offset + 64] = reference
        path.write_bytes(raw)
    with pytest.raises(ValueError):
        audit(artifacts, mode)


def test_corrupted_sources_inactive_rows_guards_tails_and_old_outputs_rejected(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    _, output, _, h, _, spans = artifacts
    mutations = [
        ('ddr_after.bin', h['aa'] - h['base']),
        ('ddr_after.bin', h['trig'] + 127 * 128 - h['base']),
        ('ddr_after.bin', h['scratch'] - h['base'] - 1),
        ('writable_after_command0.bin', spans[0]['allocation'] - h['scratch']),
        ('writable_after_command1.bin', spans[0]['begin'] - h['scratch']),
        ('writable_after_command3.bin', spans[4]['begin'] - h['scratch']),
        ('writable_after_command5.bin', spans[6]['begin'] + 64 * 2 - h['scratch']),
        ('actual_rope_q.bf16le', 64 * 2),
        ('actual_gate.bf16le', 0),
        ('reference_norm_q.bf16le', 0),
    ]
    for name, offset in mutations:
        path = output / name
        raw = path.read_bytes()
        changed = bytearray(raw)
        changed[offset] ^= 1
        path.write_bytes(changed)
        try:
            with pytest.raises(ValueError):
                audit(artifacts)
        finally:
            path.write_bytes(raw)


def test_future_output_preload_and_native_source_substitution_rejected(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    source, output, _, h, _, spans = artifacts
    snapshot = output / 'writable_after_command0.bin'
    raw = snapshot.read_bytes()
    changed = bytearray(raw)
    norm = spans[3]
    start = norm['begin'] - h['scratch']
    changed[start:start + norm['bytes']] = (source / 'independent_norm_q.bf16le').read_bytes()
    snapshot.write_bytes(changed)
    with pytest.raises(ValueError):
        audit(artifacts)
    snapshot.write_bytes(raw)
    native = source / 'native_norm_q.bf16le'
    native.write_bytes(np.full(2048, 0x4200, dtype='<u2').tobytes())
    with pytest.raises(ValueError):
        audit(artifacts)


def test_artifact_inventory_rejects_extra_missing_and_symlink_files(tmp_path):
    artifacts = fake_artifacts(tmp_path)
    source, output = artifacts[:2]
    extra = output / 'unreported.bin'
    extra.write_bytes(b'unreported')
    with pytest.raises(ValueError):
        audit(artifacts)
    extra.unlink()
    path = output / 'reference_gate.bf16le'
    raw = path.read_bytes()
    path.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        audit(artifacts)
    path.symlink_to(source / 'independent_gate.bf16le')
    with pytest.raises(ValueError):
        audit(artifacts)
    path.unlink()
    path.write_bytes(raw)
