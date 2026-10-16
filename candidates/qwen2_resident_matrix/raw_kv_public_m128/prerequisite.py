"""Pinned successful M16 evidence and explicit M128 source compatibility.

Hash/control preparation only. This does not admit an asset bundle, load a
library, execute numerical work, or grant M128/full29 acceptance.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = 'candidates/qwen2_resident_matrix/raw_kv_public_run/M16_EVIDENCE.json'
EVIDENCE_SHA256 = '6e11e881e4949dd088145fc5ff098102bb40555ab2cc16dfd7d8a5f0adb50a9a'
PROFILE = 'qwen2-public-pv16-fresh-m128-v1'
ENTRY = 'candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py'
ASSETS = 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py'
SETUP = 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'
VARIANTS = (ENTRY, ASSETS, SETUP)


def need(ok):
    if not ok:
        raise ValueError('M128 prerequisite or source compatibility')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def same(a, b):
    return encoded(a) == encoded(b)


def evidence(raw=None):
    if raw is None:
        raw = (ROOT / EVIDENCE).read_bytes()
    need(type(raw) is bytes and len(raw) <= 131072 and sha(raw) == EVIDENCE_SHA256)
    value = json.loads(raw)
    s = value['summary']; sources = value['source_hashes']
    need(value['run_id'] == 38904754050 and value['job_id'] == 116985413928)
    for key, want in dict(status='PASS_FRESH_PUBLIC_M16_OBSERVED_GATES', rows=16,
        enable_raw_kv=True, fresh_profile=True, actual_dataflow_pass=True,
        fixed_arithmetic_pass=True, assigned_official_gates=27, observed_fields=28,
        full_29_node_acceptance=False, native_acceptance='PASS_OBSERVED_ONLY').items():
        need(same(s[key], want))
    need(len(sources['source_sha256']) == 193 and len(sources['generated_sha256']) == 8)
    actual = dict(sources['source_sha256']); actual.update(sources['generated_sha256'])
    need(sha(encoded(actual)) == s['source_manifest_sha256'])
    return value


def compatible_sources(actual, replacements, *, profile, rows, past_tokens):
    """Require exact reviewed replacements; no arbitrary refresh of old pins.

The caller must obtain replacements from its independently frozen generated
contract. This function does not trust a caller-supplied map as a source pin.
New profile files are checked separately by that contract.
"""
    need(type(profile) is str and profile == PROFILE and type(rows) is int and rows == 128
         and type(past_tokens) is int and past_tokens == 0)
    need(type(actual) is dict and type(replacements) is dict and set(replacements) == set(VARIANTS))
    old = evidence()['source_hashes']
    baseline = dict(old['source_sha256']); baseline.update(old['generated_sha256'])
    need(set(baseline) <= set(actual))
    for name, identity in baseline.items():
        expected = replacements[name] if name in replacements else identity
        need(type(expected) is str and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected))
        need(actual[name] == expected)
    return dict(profile=PROFILE, rows=128, past_tokens=0,
        m16_evidence_sha256=EVIDENCE_SHA256, source_compatibility='EXPLICIT_THREE_VARIANTS',
        m128_executed=False, full_29_node_acceptance=False)
