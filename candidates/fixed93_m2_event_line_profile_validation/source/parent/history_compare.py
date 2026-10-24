"""Parent-only verification of the exact independently reviewed sealed M2 arm.

The admitted parent calls verify_history(own) only AFTER its fresh new arm has
sealed and the original supervisor has confirmed exit, reap and group cleanup.
It calls the same function again after comparison. This module grants no actual
authority, imports no DUT/codec/native code, and never changes historical files.
Historical paths live only in the source-pinned HISTORY.json, never child argv
or a child IO allowlist. Source preflight may inspect that small JSON without
calling this function or opening any historical payload.
"""
from pathlib import Path

import m2_authority as authority

HERE = Path(__file__).resolve().parent.parent
REVIEW_SHA256 = '8055216d02e43c73d62a6fefaea64f32498965421631c5028e53f9b758f5a9c4'
FIELDS = frozenset(('dot_raw', 'dot_bf16', 'scale_fp32', 'score_bf16',
    'score_difference', 'exp_fp32', 'denominator_step', 'packed_stripes',
    'fold_before', 'fold_after', 'probability_fp32', 'probability_bf16',
    'pv_key_raw', 'normalizer', 'pv_final_raw', 'pv_bf16'))
DOCUMENTS = frozenset(('M2_CASE.json', 'ARM_RESULT.json', 'attention/summary.json'))
REQUIRED = DOCUMENTS | {'actual_output.u32le', 'actual_transport.json',
    'attention/attention-events.lec1', 'wholeblock_events.lec1'} | {
    'attention/' + name + suffix for name in FIELDS for suffix in ('.u32le', '.presence')}
_FIRST_STAMPS = None


def verify_history(own):
    """Hash/stat-check all 39 pinned files, returning the fixed historical Path.

This is a postseal parent operation, not a preflight, child setup, decoder or
permission check. The caller retains responsibility for its fresh arm's seals
and supervisor cleanup. Repeated calls rehash every file and additionally
require the original file stamps to remain unchanged across the comparison.
"""
    global _FIRST_STAMPS
    need, checked, parse = authority.need, authority.checked, authority.parse
    need(authority._STATE is None, 'historical comparison is parent-only, never an admitted child')
    need(type(own) is dict and type(own.get('parent_files')) is dict and
         'parent/HISTORY.json' in own['parent_files'], 'parent-only source-pinned HISTORY.json required')
    stamps = {}

    def read(path, pin, *, retain=True, cap=1 << 20):
        path = Path(path)
        before = authority.stamp(path.lstat())
        value = checked(path, pin, retain=retain, cap=cap)
        need(before == authority.stamp(path.lstat()), 'history stamp changed during verification')
        stamps[str(path)] = before
        return value

    history = parse(read(HERE / 'parent/HISTORY.json', own['parent_files']['parent/HISTORY.json'], cap=32768))
    need(type(history) is dict and set(history) == {'schema', 'scope', 'root', 'review', 'files'} and
         history['schema'] == 'fixed93-reviewed-sealed-m2-history-v1' and
         history['scope'] == 'PARENT_POSTSEAL_COMPARISON_ONLY_NOT_CHILD_IO', 'exact history contract')
    review_pin = history['review']
    need(type(review_pin) is dict and set(review_pin) == {'path', 'bytes', 'sha256'} and
         type(review_pin['path']) is str and review_pin['bytes'] == 40115 and
         review_pin['sha256'] == REVIEW_SHA256, 'exact independent actual review pin')
    review = parse(read(Path(review_pin['path']), review_pin, cap=262144))
    need(review.get('status') == 'CONFIRMED_MATCHED_SUCCESS_M2_OBSERVER_EQUIVALENCE_ONLY' and
         review.get('actual_M2_executed') is True and review.get('M2_observer_equivalence_only') is True and
         review.get('fullblock_pass') is False and review.get('M128_acceptance') is False and
         review.get('numerical_acceptance') is False and review.get('old_unsealed_stream_read') is False,
         'reviewed sealed history is only limited M2 observer equivalence')
    supervisor = review['identity_and_cleanup']['new']['supervisor']
    need(supervisor.get('status') == 'PASS' and supervisor.get('exit_code') == 0 and
         supervisor.get('anchor_confirmed') is True and supervisor.get('reaped') is True and
         supervisor.get('cleanup_confirmed') is True and supervisor.get('group_state') == 'absent',
         'historical arm must have independently reviewed successful cleanup')
    need(type(history['root']) is str, 'exact historical root string required')
    root = Path(history['root'])
    need(root == Path(review['output']) / 'new' and
         root == Path(review['candidate']) / 'work/pair01/new' and
         root.is_absolute() and root.resolve() == root and root.is_dir() and
         not any(p.is_symlink() for p in (root, *root.parents)), 'exact reviewed historical new arm only')
    files = history['files']
    reviewed_files = {name[4:]: pin for name, pin in review['owned_file_pins'].items()
                      if name.startswith('new/')}
    need(type(files) is dict and set(files) == REQUIRED and len(files) == 39 and
         files == reviewed_files, 'exact 39 independently reviewed history pins')
    for name, pin in files.items():
        need(type(pin) is dict and set(pin) == {'bytes', 'sha256'} and
             type(pin['bytes']) is int and 0 <= pin['bytes'] <= 20971520 and
             type(pin['sha256']) is str and len(pin['sha256']) == 64 and
             all(c in '0123456789abcdef' for c in pin['sha256']), 'bounded exact history file pin')
    docs = {name: parse(read(root / name, files[name])) for name in sorted(DOCUMENTS)}
    case, arm, summary = (docs[name] for name in ('M2_CASE.json', 'ARM_RESULT.json', 'attention/summary.json'))
    need(case.get('status') == 'ACTUAL_SUCCESS_M2_CAPTURED_PENDING_PAIR_COMPARISON' and
         case.get('variant') == 'new' and case.get('m') == 2 and case.get('scope') == 'INCOMPLETE_WHOLEBLOCK' and
         case.get('wholeblock', {}).get('status') == 'SEALED_ACTUAL_M2_SUBCHAIN_ONLY' and
         case['wholeblock']['artifact'] == files['wholeblock_events.lec1'] and
         case.get('output') == files['actual_output.u32le'], 'historical case seal and artifact linkage')
    need(arm.get('status') == 'PASS_LIMITED_SUCCESS_M2_ARM_PENDING_PAIR_DIFF' and
         arm.get('arm') == 'new' and arm.get('actual_owner_M') == 2 and arm.get('case') == case and
         arm.get('scope') == 'INCOMPLETE_WHOLEBLOCK' and arm.get('fullblock_pass') is False and
         arm.get('M128_execution') is False and arm.get('numerical_acceptance') is False and
         arm.get('source_manifest_sha256') == review['source_manifest']['sha256'], 'historical arm exact-source result')
    need(summary.get('complete_observation') is True and set(summary.get('fields', {})) == FIELDS and
         summary['event_codec_seal']['encoded_bytes'] == files['attention/attention-events.lec1']['bytes'],
         'historical complete field/event seal required')
    for name in FIELDS:
        for suffix, key in (('.u32le', 'raw_sha256'), ('.presence', 'frequency_sha256')):
            need(summary['fields'][name][key] == files['attention/' + name + suffix]['sha256'],
                 'historical field/presence seal linkage')
    for name in sorted(REQUIRED - DOCUMENTS):
        read(root / name, files[name], retain=False, cap=20971520 if name.endswith('.lec1') else 1048576)
    need(all(authority.stamp(Path(path).lstat()) == value for path, value in stamps.items()),
         'history changed across complete verification')
    need(_FIRST_STAMPS is None or stamps == _FIRST_STAMPS, 'history changed across parent comparison')
    if _FIRST_STAMPS is None:
        _FIRST_STAMPS = dict(stamps)
    return root
