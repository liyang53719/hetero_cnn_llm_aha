import hashlib
import os
import subprocess
from pathlib import Path
import pytest
import gqa_selector_candidate as C
from run_profile import PIN, DIAGNOSTIC_ROOT


def test_exact_single_source_transformation():
    source = Path(os.environ.get('ATTENTION_PROFILE_SOURCE_ROOT', DIAGNOSTIC_ROOT))
    raw = subprocess.check_output(['git', '-C', str(source), 'show', PIN + ':' + C.TARGET])
    changed = C.transform(raw).decode()
    assert C.OLD not in changed and changed.count(C.NEW) == 1
    assert changed.replace(C.HELPER, '', 1).replace(C.NEW, C.OLD, 1).encode() == raw
    assert changed.endswith(C.HELPER)
    original_lines, changed_lines = raw.decode().splitlines(), changed.splitlines()
    first = original_lines.index(C.OLD.splitlines()[0])
    assert original_lines[:first] == changed_lines[:first]
    assert original_lines[first+3:] == changed_lines[first+3:len(original_lines)]
    assert 'valid' not in C.NEW and 'ready' not in C.NEW
    with pytest.raises(ValueError, match='exact frozen'): C.transform(raw + b'\n')
    with pytest.raises(ValueError, match='exact frozen'): C.transform(changed.encode())


def test_module_identity_is_byte_exact_and_closed(tmp_path):
    baseline = tmp_path/'old.sv'; candidate = tmp_path/'new.sv'
    raw = b'// common header\nmodule Other;\nwire a;\nendmodule\nmodule Bf16CausalGqaOwner;\nwire packed;\nendmodule\n'
    baseline.write_bytes(raw); candidate.write_bytes(raw.replace(b'wire packed;', b'wire selected;'))
    result = C.module_diff(baseline, candidate)
    assert result['changed_modules'] == ['Bf16CausalGqaOwner']
    assert result['unchanged_modules'] == 1 and not result['normalization_applied']
    assert result['baseline_sha256'] == hashlib.sha256(raw).hexdigest()
    for bad, reason in [(raw, 'unexpected'),
                        (candidate.read_bytes().replace(b'wire a;', b'wire b;'), 'unexpected'),
                        (b'// extra\n' + candidate.read_bytes(), 'outside'),
                        (candidate.read_bytes().replace(b'Other', b'Another'), 'module set')]:
        candidate.write_bytes(bad)
        with pytest.raises(ValueError, match=reason): C.module_diff(baseline, candidate)


@pytest.mark.parametrize('text', [b'', b'module X;\n', b'endmodule\n',
    b'module X;\nmodule Y;\nendmodule\n', b'module X;\nendmodule\nmodule X;\nendmodule\n'])
def test_malformed_module_inventory_rejected(tmp_path, text):
    p = tmp_path/'bad.sv'; p.write_bytes(text)
    with pytest.raises(ValueError): C.module_hashes(p)


def test_module_reorder_and_outside_comment_relocation_rejected(tmp_path):
    baseline = tmp_path/'old.sv'; candidate = tmp_path/'new.sv'
    other = b'module Other;\nwire a;\nendmodule\n'
    original = b'module Bf16CausalGqaOwner;\nwire packed;\nendmodule\n'
    changed = original.replace(b'wire packed;', b'wire selected;')
    comment = b'// fixed gap\n'
    baseline.write_bytes(other + comment + original)
    candidate.write_bytes(changed + comment + other)
    with pytest.raises(ValueError, match='order'): C.module_diff(baseline, candidate)
    candidate.write_bytes(other + changed + comment)
    with pytest.raises(ValueError, match='gaps'): C.module_diff(baseline, candidate)


def test_strict_failure_keeps_exact_modules_without_accepting_them(tmp_path, monkeypatch):
    import concat_inventory
    baseline, candidate = tmp_path/'old.sv', tmp_path/'new.sv'
    receipt = tmp_path/'candidate_build/generated_rtl_identity.json'
    receipt.parent.mkdir()
    baseline.write_bytes(b'module Mem;\n// source:109\nwire a;\nendmodule\nmodule Bf16CausalGqaOwner;\nwire packed;\nendmodule\n')
    candidate.write_bytes(baseline.read_bytes().replace(b'109', b'132').replace(b'packed', b'selected'))
    with pytest.raises(ValueError, match='unexpected'): C.module_diff(baseline,candidate)
    result=C.preserve_failure(baseline,candidate,receipt,'strict module mismatch')
    assert result['status']=='REJECTED' and result['normalization_applied'] is False
    assert result['changed_modules']==['Bf16CausalGqaOwner','Mem']
    assert result['numerical_acceptance'] is False and not receipt.exists()
    assert receipt.with_suffix('.failure.json').is_file()
    for row in result['saved_modules']:
        assert row['preserved'] is True
        raw=(tmp_path/'selected-source'/row['saved_as']).read_bytes()
        assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    assert result['selected_source_bytes']==baseline.stat().st_size+candidate.stat().st_size


def test_failed_module_preservation_obeys_source_byte_cap(tmp_path, monkeypatch):
    import concat_inventory
    monkeypatch.setattr(concat_inventory,'MAX_SOURCE_BYTES',1)
    baseline,candidate=tmp_path/'old.sv',tmp_path/'new.sv'
    baseline.write_bytes(b'module Bf16CausalGqaOwner;\nwire a;\nendmodule\n')
    candidate.write_bytes(baseline.read_bytes().replace(b'wire a',b'wire b'))
    receipt=tmp_path/'candidate_build/generated_rtl_identity.json';receipt.parent.mkdir()
    result=C.preserve_failure(baseline,candidate,receipt,'strict failure')
    assert result['selected_source_bytes']==0
    assert all(not row['preserved'] and row['reason']=='source_byte_budget' for row in result['saved_modules'])
