"""Mutation regressions for C06.1/C08.1/Q21.1; synthetic software only."""
from dataclasses import replace
import json
import struct
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from heteronpu import command_window_contract as control
from heteronpu import block_receipt as receipt
from heteronpu import weight_packing as weights
from test_block_receipt import fixture, run


def test_compiled_lifetimes_are_read_only():
    spec = control.compile_program(control.chain_program(65))
    with pytest.raises(TypeError):
        spec.last_use['t0'] = 0


def test_compiled_constructor_snapshots_mapping():
    spec = control.compile_program(control.chain_program(65))
    backing = dict(spec.last_use)
    snapshot = replace(spec, last_use=backing)
    backing['t0'] = 0
    assert snapshot.last_use['t0'] == 1


@pytest.mark.parametrize('field', ['last_use', 'peak_live', 'windows'])
def test_machine_rejects_forged_compiled_metadata(field):
    spec = control.compile_program(control.chain_program(65))
    value = {'last_use': {'input': -1}, 'peak_live': 1, 'windows': ((0, 65),)}[field]
    with pytest.raises(control.ControlError, match='compiled metadata'):
        control.WindowMachine(replace(spec, **{field: value}))


@pytest.mark.parametrize('member', ['actual_projection.bin', 'ref_projection.bin', 'receipt.json'])
@pytest.mark.parametrize('method', ['change', 'replace', 'rewrite_same'])
def test_receipt_rejects_files_changed_after_their_comparison(tmp_path, monkeypatch, member, method):
    fixture(tmp_path)
    original = receipt.compare_files
    calls = 0

    def compare_then_mutate(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 3:  # first tensor/receipt already read; modify during later work
            p = tmp_path / member
            data = p.read_bytes()
            if method == 'replace':
                new = tmp_path / 'replacement'
                new.write_bytes(data)
                new.replace(p)
            elif method == 'rewrite_same':
                p.write_bytes(data)
            elif member.endswith('.json'):
                doc = json.loads(data)
                doc['attestation']['cpu_fallback'] = 1
                p.write_text(json.dumps(doc))
            else:
                p.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        return result

    monkeypatch.setattr(receipt, 'compare_files', compare_then_mutate)
    with pytest.raises(receipt.ReceiptError, match='changed during'):
        run(tmp_path)


@pytest.mark.parametrize('member', ['manifest.json', 'weights.bf16le', 'source'])
@pytest.mark.parametrize('method', ['change', 'replace', 'rewrite_same'])
def test_weight_readback_rejects_mid_verification_mutation(tmp_path, monkeypatch, member, method):
    source = tmp_path / 'source'
    source.write_bytes(struct.pack('<6f', 1., 2., 3., 4., 5., 6.))
    contract = weights.PackContract(2, 3, True)
    package = tmp_path / 'package'
    weights.pack_file(source, package, contract)
    original = weights._independent_bf16
    fired = False

    def convert_then_mutate(*args, **kwargs):
        nonlocal fired
        result = original(*args, **kwargs)
        if not fired:
            fired = True
            p = source if member == 'source' else package / member
            data = p.read_bytes()
            if method == 'replace':
                new = tmp_path / 'replacement'
                new.write_bytes(data)
                new.replace(p)
            elif method == 'rewrite_same':
                p.write_bytes(data)
            elif member == 'manifest.json':
                doc = json.loads(data)
                doc['source_sha256'] = '0' * 64
                p.write_text(json.dumps(doc))
            else:
                p.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        return result

    monkeypatch.setattr(weights, '_independent_bf16', convert_then_mutate)
    with pytest.raises(weights.PackingError):
        weights.verify_package(source, package, contract)


def test_source_symlink_is_supported_when_unchanged(tmp_path):
    # HF caches may expose checkpoint data via symlinks; source policy unchanged.
    source = tmp_path / 'data'
    source.write_bytes(struct.pack('<f', 1.0))
    link = tmp_path / 'link'
    link.symlink_to(source)
    c = weights.PackContract(1, 1, False)
    weights.pack_file(link, tmp_path / 'package', c)
    assert weights.verify_package(link, tmp_path / 'package', c)['elements'] == 1
