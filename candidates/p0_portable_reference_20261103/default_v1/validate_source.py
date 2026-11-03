"""Exact, independently supplied source-manifest identity; no trust-on-first-use."""
from pathlib import Path
import re
from fixture_gate import strict_json, sha, need

HERE = Path(__file__).resolve().parent
RELATIVE = 'candidates/p0_portable_reference_20261103/default_v1'


def verify_source(repo, expected):
    repo = Path(repo).absolute()
    manifest = repo / RELATIVE / 'SOURCE_MANIFEST.json'
    need(re.fullmatch('[0-9a-f]{64}', expected or '') is not None and sha(manifest) == expected, 'PRECHECK_PIN')
    data = strict_json(manifest)
    need(set(data) == {'schema', 'candidate_id', 'files'} and data['schema'] == 'P0_DEFAULT_SOURCE_CLOSURE_V1' and data['candidate_id'] == 'P0_QWEN2_FULL128_DEFAULT_REFERENCE_V1', 'PRECHECK_PIN')
    pins = {str(manifest): expected}
    need(type(data['files']) is dict and 10 <= len(data['files']) <= 64, 'PRECHECK_PIN')
    for relative, record in data['files'].items():
        p = Path(relative)
        need(not p.is_absolute() and '..' not in p.parts and (relative.startswith(RELATIVE + '/') or relative == '.github/workflows/hetero-p0-portable-reference-default.yml'), 'PRECHECK_PIN')
        need(set(record) == {'bytes', 'sha256'} and type(record['bytes']) is int and 0 < record['bytes'] <= 1 << 20, 'PRECHECK_PIN')
        target = repo / p
        for node in (target, *target.parents):
            need(not node.is_symlink(), 'PRECHECK_PIN')
        need(target.is_file() and target.stat().st_size == record['bytes'] and sha(target) == record['sha256'], 'PRECHECK_PIN')
        pins[str(target)] = record['sha256']
    actual = {str(p.relative_to(repo)) for p in (repo / RELATIVE).rglob('*') if p.is_file() and p.name != 'SOURCE_MANIFEST.json'}
    need(actual == {p for p in data['files'] if p.startswith(RELATIVE + '/')}, 'PRECHECK_PIN')
    return pins
