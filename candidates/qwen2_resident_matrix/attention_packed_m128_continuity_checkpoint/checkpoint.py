"""Cold verification of this one interrupted execution checkpoint; no runtime imports."""
import hashlib
import json
from pathlib import Path
import re
import stat
import copy
import shutil
import tempfile
import unittest
import sys

ROOT = Path(__file__).parent
V = sys.modules[__name__]

STATUS = 'INCOMPLETE_EXECUTION_CONTINUITY_UNVERIFIED'
CONTRACT = 'cf20ec20ed2f023bf1d9b2b2f10ecd4d7963699cebab5f984e3a429e8f3ed9eb'
SOURCE_MAP = '4e0f86922cdc268f245aa0105e03fbae617add5da8b3609e3799b12ca72943b8'
ACTUAL = 'e642d97b3621f80666696a6c56e7ef01051aa735436843bd83b2176021066b1f'
CONTEXT = '99bd12bf22817d5d83e76fba9c63833362fda82652a712b88b361993b3f301d1'
SOURCE_PROOF = '2df1d5b7e2f7169357710dd9152763b32ae247c6ba88c95e9b11e2d60a2fb91e'
SNAPSHOT = '0b92832323093a5337fa6f5fb711bf8b016396a8d2557410e0ba1d69e25b90a3'
EXACT_COPIES = {
    'CALLER_PREFIX.json': 'c8c387b7912dfe29afb3e1f1825cc592c99b4ec5a05df1fc1a2c1da3cedebcda',
    'PROGRESS.json': '3b326fa4bcb96a810bf76fa44fe135a8a824d30fd5c635ac4789d8c456e6f0b1'}
PREFIX_KINDS = ['Norm', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'KvAppend']
UNKNOWN = {'launcher_exit_code', 'child_exit_code', 'actual_chain_complete',
           'process_cleanup_complete', 'process_running', 'numerical_outcome',
           'deadline_expiration_observed'}
ACCEPTANCE = {'numerical_acceptance', 'native_acceptance', 'public_m128_acceptance',
              'full_29_node_acceptance', 'rtl_acceptance', 'hardware_recipe_acceptance',
              'useful_wall_mac_90_percent', 'old_pass_inherited'}
ABSENT = {'summary.json', 'control/CHILD_COMPLETE.json', 'PRIVATE_LAUNCH_RECEIPT.json', 'SUPERVISOR.json'}
MAX_FILE = 65536
MAX_BUNDLE = 32768


def need(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def same(a, b):
    return compact(a) == compact(b)


def clean_path(value):
    return (type(value) is str and value and not value.startswith('/') and
            '\\' not in value and not any(x in ('', '.', '..') for x in value.split('/')))


def strict_json(raw):
    need(len(raw) <= MAX_FILE, 'FILE_BOUND')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_KEY')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('NONFINITE')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    def visit(item, depth=0):
        need(depth <= 16, 'DEPTH_BOUND')
        if isinstance(item, dict):
            need(len(item) <= 1024, 'OBJECT_BOUND')
            for key, child in item.items():
                visit(key, depth + 1); visit(child, depth + 1)
        elif isinstance(item, list):
            need(len(item) <= 1024, 'ARRAY_BOUND')
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            need(len(item) <= 4096, 'STRING_BOUND')
        elif isinstance(item, float):
            need(item == item and abs(item) != float('inf'), 'NONFINITE')
    visit(value)
    return value


def validate_state(c):
    need(set(c) == {'schema', 'status', 'observation_utc', 'original_workspace',
         'frozen_wrapper', 'identities', 'attempt', 'observed_prefix', 'unknown',
         'acceptance', 'completion_artifacts', 'source_verification', 'interpretation'}, 'STATE_KEYS')
    need(type(c['schema']) is int and c['schema'] == 1, 'SCHEMA')
    need(c['status'] == STATUS, 'STATUS')
    need(re.fullmatch(r'2026-10-17T00:[0-5][0-9]:[0-5][0-9]Z', c['observation_utc']) is not None, 'OBSERVATION')
    need(c['original_workspace'] == 'packed_m128_run_gate_20261017', 'WORKSPACE')
    need(c['frozen_wrapper'] == 'packed-m128-run-gate-proposal-20261017', 'WRAPPER')
    need(c['identities'] == {'contract_sha256': CONTRACT, 'runtime_source_map_compact_sha256': SOURCE_MAP,
         'actual_summary_sha256': ACTUAL, 'context_sha256': CONTEXT}, 'IDENTITIES')
    need(set(c['unknown']) == UNKNOWN and all(x is None for x in c['unknown'].values()), 'UNKNOWN_NOT_NULL')
    need(set(c['acceptance']) == ACCEPTANCE and all(x is False for x in c['acceptance'].values()), 'ACCEPTANCE')
    a = c['attempt']
    need(same(a, {'tool_session_id': 94904, 'exec_cell_id': 376,
         'started_utc_observed': '2026-10-17T00:11:06Z',
         'outer_deadline_monotonic': 77060.445410078,
         'outer_deadline_utc_approximate': '2026-10-17T00:51:36Z',
         'numerical_run_started': True, 'namespace_parent_pid': 5, 'namespace_child_pid': 6,
         'host_pid_starttime_proof_available': False,
         'tool_continuity': 'UNAVAILABLE_AS_REPORTED_BY_PARENT',
         'tool_continuity_report': 'Unknown process id 94904; old exec cell 376 unavailable after wait aborted',
         'tool_observation_source': 'parent task handoff; not independently replayed by checkpoint builder'}), 'ATTEMPT')
    p = c['observed_prefix']
    need(same(p, {'status': 'ACTUAL_PREFIX_COMPLETE', 'rows': 128, 'actual_summary_bytes': 297936,
         'prefix_host_wall_seconds': 79.21691106600338, 'prefix_completions': 10,
         'operations': [dict(pc=i, kind=k) for i, k in enumerate(PREFIX_KINDS)]}), 'PREFIX')
    items = c['completion_artifacts']
    need(set(items) == ABSENT and all(same(v, {'present': False, 'observed_utc': c['observation_utc']}) for v in items.values()), 'ABSENCE_SCOPE')
    need(same(c['source_verification'], {'installed_files_checked': 350, 'matching_files': 350,
         'mismatch_count': 0, 'missing_count': 0,
         'input_map_equals_frozen_map': True, 'proof_map_equals_frozen_map': True,
         'actual_report_map_equals_frozen_map': True}), 'SOURCE_VERIFICATION')
    need(c['interpretation'] == 'Prefix completion only. Execution continuity, exits, cleanup, terminal completion, numerical outcome and deadline expiration are unknown. Absence is an observation at the recorded time. No timeout or numerical failure is inferred; no PASS is inherited. No kill, restart or numerical work was performed for this checkpoint.', 'INTERPRETATION')


PAYLOAD = {'CALLER_PREFIX.json', 'PROGRESS.json', 'EVIDENCE.json', 'checkpoint.py', 'README.md'}
PUBLISHED = PAYLOAD | {'MANIFEST.json'}
PUB_PREFIX = 'candidates/qwen2_resident_matrix/attention_packed_m128_continuity_checkpoint/'


def validate_evidence(e):
    need(set(e) == {'schema', 'state', 'original_artifacts', 'context_selected',
         'context_omitted_path_fields', 'source_proof_selected', 'source_map_reference',
         'contract_reference', 'log_observations', 'privacy', 'cold_checks'}, 'EVIDENCE_KEYS')
    need(type(e['schema']) is int and e['schema'] == 1, 'EVIDENCE_SCHEMA')
    validate_state(e['state'])
    originals = e['original_artifacts']
    need(set(originals) == {'actual/summary.json', 'snapshot/SNAPSHOT.json', 'CALLER_PREFIX.json',
         'CALLER_START.json', 'ATTEMPT_LOCK', 'INPUTS.json', 'control/SOURCE_PROOF.json',
         'control/progress.json', 'control/CONTEXT.json'}, 'ORIGINAL_KEYS')
    for name, length, digest in [('actual/summary.json', 297936, ACTUAL),
        ('control/CONTEXT.json', 942, CONTEXT), ('control/SOURCE_PROOF.json', 49884, SOURCE_PROOF),
        ('snapshot/SNAPSHOT.json', 447057, SNAPSHOT),
        ('CALLER_PREFIX.json', 1147, EXACT_COPIES['CALLER_PREFIX.json']),
        ('control/progress.json', 188, EXACT_COPIES['PROGRESS.json'])]:
        need(same(originals[name], {'bytes': length, 'sha256': digest}), 'ORIGINAL_IDENTITY')
    c = e['context_selected']; p = e['source_proof_selected']
    need(set(c) == {'schema', 'profile', 'contract_sha256', 'started', 'work_deadline', 'outer_deadline', 'parent_pid'} and
         set(p) == {'schema', 'context_sha256', 'source_manifest_sha256', 'git_head', 'committed_cpp_sha256', 'pid', 'work_deadline'}, 'PROJECTION_KEYS')
    need(c['contract_sha256'] == CONTRACT and type(c['parent_pid']) is int and c['parent_pid'] == 5 and
         type(c['outer_deadline']) is float and c['outer_deadline'] == 77060.445410078, 'CONTEXT')
    need(p['context_sha256'] == CONTEXT and p['source_manifest_sha256'] == SOURCE_MAP and
         type(p['pid']) is int and p['pid'] == 6, 'SOURCE_PROOF')
    ref = e['source_map_reference']
    need(ref['sha256'] == '3fc86df23e050110039e2e1de8cef877f0ecba10908fefff86d8ffe66e41e536' and
         ref['compact_sha256'] == SOURCE_MAP and type(ref['count']) is int and ref['count'] == 350 and
         ref['installed_files_independently_hashed'] == 350 and ref['all_installed_hashes_match'] is True and
         ref['source_map_republished'] is False, 'SOURCE_MAP_REFERENCE')
    need(e['contract_reference']['sha256'] == CONTRACT and e['contract_reference']['contract_republished'] is False, 'CONTRACT_REFERENCE')
    for log in e['log_observations'].values():
        need(same(log, {'bytes': 0, 'observed_utc': e['state']['observation_utc'], 'copied': False}), 'LOG_OBSERVATION')
    need(e['cold_checks']['numerical_acceptance'] is False, 'COLD_NOT_NUMERICAL')


def verify(root):
    root = Path(root)
    entries = {p.name for p in root.iterdir()}
    need(entries in (PUBLISHED, PUBLISHED | {'PUBLICATION_FILEMAP.json'}), 'FILE_SET')
    m = strict_json((root / 'MANIFEST.json').read_bytes())
    need(set(m) == {'schema', 'files'} and type(m['schema']) is int and m['schema'] == 1 and
         set(m['files']) == PAYLOAD, 'MANIFEST')
    total = 0
    for name in PUBLISHED:
        path = root / name
        need(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(), 'FILE_TYPE')
        raw = path.read_bytes(); total += len(raw)
        need(len(raw) <= MAX_FILE, 'FILE_BOUND')
        private_pattern = rb'/(?:workspace|home|tmp|private)/|file:' + rb'//|-----BEGIN [A-Z ]*PRIVATE KEY-----'
        need(not re.search(private_pattern, raw), 'PRIVATE_PATH_OR_SECRET')
        if name in PAYLOAD:
            need(same(m['files'][name], {'bytes': len(raw), 'sha256': sha(raw)}), 'FILE_IDENTITY')
    need(total <= MAX_BUNDLE, 'BUNDLE_BOUND')
    e = strict_json((root / 'EVIDENCE.json').read_bytes()); validate_evidence(e)
    for name, digest in EXACT_COPIES.items():
        need(sha((root / name).read_bytes()) == digest, 'EXACT_CONTROL_COPY')
    if 'PUBLICATION_FILEMAP.json' in entries:
        raw = (root / 'PUBLICATION_FILEMAP.json').read_bytes()
        need(len(raw) <= 2 * MAX_FILE, 'PUBLICATION_BOUND')
        pub = json.loads(raw)
        need(set(pub) == {PUB_PREFIX + n for n in PUBLISHED}, 'PUBLICATION_SET')
        need(all(pub[PUB_PREFIX + n] == (root / n).read_text() for n in PUBLISHED), 'PUBLICATION_BYTES')
    return {'status': 'VALID_INCOMPLETE_CHECKPOINT', 'numerical_acceptance': False,
            'published_files': len(PUBLISHED), 'published_bytes': total, 'source_hashes_recorded_checked': 350}

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((ROOT / 'EVIDENCE.json').read_text())['state']

    def test_original_checkpoint_is_incomplete(self):
        V.validate_state(self.c)
        self.assertEqual(self.c['status'], V.STATUS)

    def test_pass_failure_timeout_labels_cannot_replace_continuity_status(self):
        for status in ('PASS', 'PASS_OBSERVED_ONLY', 'FAIL', 'TIMEOUT', 'ACTUAL_PREFIX_COMPLETE'):
            c = copy.deepcopy(self.c); c['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                V.validate_state(c)

    def test_every_acceptance_remains_false(self):
        for key in V.ACCEPTANCE:
            for value in (True, 0, None, 'PASS'):
                c = copy.deepcopy(self.c); c['acceptance'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    V.validate_state(c)

    def test_unknown_exits_completion_cleanup_cannot_be_inferred(self):
        for key in V.UNKNOWN:
            for value in (0, 1, False, True, 'unknown'):
                c = copy.deepcopy(self.c); c['unknown'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    V.validate_state(c)

    def test_missing_or_added_acceptance_and_unknown_keys_rejected(self):
        for field in ('acceptance', 'unknown'):
            for change in ('missing', 'extra'):
                c = copy.deepcopy(self.c)
                if change == 'missing': c[field].pop(next(iter(c[field])))
                else: c[field]['future_native_acceptance'] = True
                with self.subTest(field=field, change=change), self.assertRaises(ValueError):
                    V.validate_state(c)

    def test_prefix_not_full_completion(self):
        for key, value in [('prefix_completions', 21), ('rows', 16), ('status', 'PASS'), ('actual_summary_bytes', 0)]:
            c = copy.deepcopy(self.c); c['observed_prefix'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): V.validate_state(c)

    def test_source_identity_cannot_rebind(self):
        for key in self.c['identities']:
            c = copy.deepcopy(self.c); c['identities'][key] = '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError): V.validate_state(c)

    def test_namespace_pid_is_not_host_identity(self):
        c = copy.deepcopy(self.c); c['attempt']['host_pid_starttime_proof_available'] = True
        with self.assertRaises(ValueError): V.validate_state(c)

    def test_absence_requires_same_observation_time(self):
        for key in V.ABSENT:
            for field, value in [('present', True), ('observed_utc', 'permanently absent')]:
                c = copy.deepcopy(self.c); c['completion_artifacts'][key][field] = value
                with self.subTest(key=key, field=field), self.assertRaises(ValueError): V.validate_state(c)

    def test_all_350_files_required(self):
        c = copy.deepcopy(self.c); c['source_verification']['matching_files'] = 349
        with self.assertRaises(ValueError): V.validate_state(c)

    def test_no_unknown_top_level_claim(self):
        c = copy.deepcopy(self.c); c['native_acceptance'] = 'PASS'
        with self.assertRaises(ValueError): V.validate_state(c)

    def test_strict_json_and_bounds(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
                    b'[' * 18 + b'0' + b']' * 18, b' ' * (V.MAX_FILE + 1)):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError): V.strict_json(raw)

    def test_relative_identity_paths_only(self):
        for path in ('/x', '../x', 'x/../y', 'x//y', 'x\\y', './x'):
            with self.subTest(path=path): self.assertFalse(V.clean_path(path))
        self.assertTrue(V.clean_path('candidates/example.py'))

    def test_source_map_reference_exact_count_and_hash(self):
        e = json.loads((ROOT / 'EVIDENCE.json').read_text())
        for key, value in [('count', 349), ('compact_sha256', '0' * 64), ('all_installed_hashes_match', False)]:
            changed = copy.deepcopy(e); changed['source_map_reference'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_evidence(changed)

    def test_json_numeric_types_not_conflated(self):
        for path, value in [(('observed_prefix', 'rows'), 128.0),
                            (('attempt', 'namespace_child_pid'), 6.0),
                            (('source_verification', 'input_map_equals_frozen_map'), 1)]:
            c = copy.deepcopy(self.c); c[path[0]][path[1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError): V.validate_state(c)

    def test_exact_safe_control_copies(self):
        for name, expected in V.EXACT_COPIES.items():
            with self.subTest(name=name): self.assertEqual(V.sha((ROOT / name).read_bytes()), expected)

    def test_private_identity_links_remain_hash_only(self):
        evidence = json.loads((ROOT / 'EVIDENCE.json').read_text())
        for name, expected in [('actual/summary.json', V.ACTUAL), ('control/CONTEXT.json', V.CONTEXT),
                               ('control/SOURCE_PROOF.json', V.SOURCE_PROOF), ('snapshot/SNAPSHOT.json', V.SNAPSHOT)]:
            with self.subTest(name=name): self.assertEqual(evidence['original_artifacts'][name]['sha256'], expected)
        self.assertFalse((ROOT / 'actual').exists())
        self.assertFalse((ROOT / 'snapshot').exists())

    def test_whole_bundle_and_publication_are_exact(self):
        result = V.verify(ROOT)
        self.assertEqual(result['status'], 'VALID_INCOMPLETE_CHECKPOINT')
        self.assertIs(result['numerical_acceptance'], False)

    def test_changed_missing_extra_or_symlinked_evidence_rejected(self):
        for change in ('changed', 'missing', 'extra', 'symlink', 'filemap'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'checkpoint'; shutil.copytree(ROOT, target)
                p = target / 'CALLER_PREFIX.json'
                if change == 'changed': p.write_bytes(p.read_bytes() + b'\n')
                elif change == 'missing': p.unlink()
                elif change == 'extra': (target / 'unexpected.json').write_text('{}')
                elif change == 'symlink': p.unlink(); p.symlink_to('PROGRESS.json')
                else:
                    pub = json.loads((target / 'PUBLICATION_FILEMAP.json').read_text())
                    pub[next(iter(pub))] += '\n'
                    (target / 'PUBLICATION_FILEMAP.json').write_text(json.dumps(pub))
                with self.assertRaises((ValueError, FileNotFoundError)): V.verify(target)

    def test_private_paths_rejected_even_after_manifest_rebind(self):
        for base in ('workspace', 'home', 'tmp', 'private'):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'checkpoint'; shutil.copytree(ROOT, target)
                (target / 'PUBLICATION_FILEMAP.json').unlink()
                path = target / 'README.md'; path.write_text('/' + base + '/not-for-publication')
                m = json.loads((target / 'MANIFEST.json').read_text())
                m['files']['README.md'] = {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
                (target / 'MANIFEST.json').write_text(json.dumps(m))
                with self.assertRaisesRegex(ValueError, 'PRIVATE_PATH_OR_SECRET'): verify(target)


if __name__ == '__main__':
    if sys.argv[1:] == ['--test']:
        unittest.main(argv=[sys.argv[0]])
    else:
        need(not sys.argv[1:], 'ARGUMENTS')
        print(json.dumps(verify(ROOT), sort_keys=True))
