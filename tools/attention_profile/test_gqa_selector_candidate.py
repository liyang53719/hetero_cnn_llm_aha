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
