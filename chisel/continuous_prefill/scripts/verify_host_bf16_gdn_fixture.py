#!/usr/bin/env python3
"""Verify a live GDN source authority or independently regenerate pinned inputs.

A persisted manifest is never sufficient to authorize the comparison targets.
The CLI deliberately recomputes only the bounded two-token, 48-head proof.
"""
from pathlib import Path
import argparse
import json
import tempfile
from pack_host_bf16_gdn_fixture import ROOT, GdnFixtureSession, generate_fixture, require


def verify(fixture, *, session=None):
    fixture = Path(fixture)
    require(not fixture.is_symlink(), 'fixture root symlink')
    fixture = fixture.resolve()
    require(fixture.is_relative_to(ROOT / 'work') and fixture.is_dir(), 'fixture must be under ignored work')
    require(not any(p.is_symlink() for p in fixture.rglob('*')), 'fixture symlink')
    if session is not None:
        require(type(session) is GdnFixtureSession, 'live GdnFixtureSession required')
        report = session.verify(fixture)
        origin = 'same_invocation_source_authority'
    else:
        supplied = json.loads((fixture / 'manifest.json').read_text())
        with tempfile.TemporaryDirectory(prefix='.gdn_verify_', dir=ROOT / 'work') as tmp:
            expected = Path(tmp) / 'expected'
            authority = generate_fixture(expected)
            report = authority.verify(expected)
            require({p.name for p in fixture.iterdir()} == {p.name for p in expected.iterdir()}, 'fixture inventory differs from canonical generator')
            for name in report['files']:
                require((fixture / name).read_bytes() == (expected / name).read_bytes(), 'source-bound fixture bytes differ: ' + name)
            # Runtime paths/timing may differ. Every source, numerical metric,
            # descriptor, launch binding and file byte identity must agree.
            variable = {'tools', 'reference_elapsed_seconds', 'max_rss_kib'}
            require({k:v for k,v in supplied.items() if k not in variable} == {k:v for k,v in report.items() if k not in variable}, 'source-bound manifest differs')
        origin = 'fresh_bounded_recomputation'
    require(report['native_gate_pass'], 'fixed native operator gate failed')
    return dict(status='PASS_AUTHENTICATED_HOST_GDN_FIXTURE', verification=origin,
                commands=4, descriptor_records=60, head_jobs=48, matrix_accumulator_steps=12582912,
                native_gate_pass=True, native_metrics=report['native_metrics'],
                input_boundary=report['input_boundary'], full_block_supported=False)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('fixture',type=Path); a=p.parse_args()
    print(json.dumps(verify(a.fixture),indent=2))
