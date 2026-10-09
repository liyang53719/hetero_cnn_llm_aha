#!/usr/bin/env python3
"""Repack from authenticated official inputs; a self-signed manifest cannot pass."""
from pathlib import Path
import argparse
import json
import tempfile
from pack_host_bf16_qkv_fixture import ROOT, pack_fixture, pinned_session, fixture_input_hashes


def verify(fixture: Path, *, session=None, reference_session=None):
    fixture = Path(fixture)
    if fixture.is_symlink():
        raise ValueError('fixture root must not be a symlink')
    fixture = fixture.resolve()
    if not fixture.is_relative_to(ROOT / 'work') or not fixture.is_dir():
        raise ValueError('fixture must be under ignored work')
    if any(p.is_symlink() for p in fixture.rglob('*')):
        raise ValueError('fixture contains symlinks')
    manifest = json.loads((fixture / 'manifest.json').read_text())
    fresh_reference = manifest.get('independent_reference', {}).get('origin') == 'fresh_same_invocation_integer_c'
    if fresh_reference and reference_session is None:
        raise ValueError('fresh reference fixture requires its live independent reference authority')
    if session is None and (manifest.get('fresh_official_executions') != 0 or manifest.get('reused_official_executions') != 2):
        raise ValueError('fresh fixture requires its live same-invocation capture session')
    session = pinned_session() if session is None else session
    with tempfile.TemporaryDirectory(prefix='.host_qkv_verify_', dir=ROOT / 'work') as temporary:
        expected = Path(temporary) / 'expected'
        canonical = pack_fixture(expected, variant=manifest['variant'], phase=manifest['phase'], token_base=manifest['token_base'], token_count=manifest['token_count'], session=session, reference_session=reference_session)
        if manifest != canonical:
            raise ValueError('fixture manifest differs from authenticated source session')
        names = {p.name for p in expected.iterdir()}
        if {p.name for p in fixture.iterdir()} != names:
            raise ValueError('fixture inventory differs from authenticated packer')
        for name in names - {'manifest.json'}:
            if not (fixture / name).is_file() or (fixture / name).read_bytes() != (expected / name).read_bytes():
                raise ValueError('source-bound fixture bytes differ: ' + name)
    result = dict(status='PASS_FRESH_SAME_INVOCATION_HOST_QKV_FIXTURE' if session.fresh else 'PASS_CODE_PINNED_HOST_QKV_FIXTURE',
                scope='PROJECTION_ONLY', variant=manifest['variant'], phase=manifest['phase'],
                token_base=manifest['token_base'], token_count=manifest['token_count'],
                independent_reference=manifest['independent_reference'], input_sha256=fixture_input_hashes(fixture, manifest),
                **session.evidence())
    if fresh_reference:
        # This is established by typed authority selection during exact repack;
        # no Boolean in the caller's saved manifest establishes this fact.
        result['fresh_reference_authority_verified'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.fixture), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit('HOST_QKV_FIXTURE_REJECTED: ' + str(error))
