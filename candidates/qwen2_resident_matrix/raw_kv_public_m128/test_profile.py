"""Cold source/precondition checks; no asset, native, numerical or CI execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import prerequisite as p
from . import profile as m


def control_contract():
    """Synthetic metadata only: never a runtime-ready or numerical receipt."""
    old = p.evidence()['source_hashes']
    sources = dict(old['source_sha256'])
    sources[p.EVIDENCE] = p.EVIDENCE_SHA256
    for name in m.OWN:
        path = m.HERE / name
        sources[m.PREFIX + name] = m.sha(path.read_bytes()) if path.exists() else '0' * 64
    generated = dict(old['generated_sha256'])
    generated[p.ENTRY] = '1' * 64
    generated[p.ASSETS] = '2' * 64
    return dict(schema=1, profile=m.PROFILE, status=m.STATUS, rows=128, past_tokens=0,
                enable_raw_kv=True, m16_evidence_sha256=p.EVIDENCE_SHA256,
                source_sha256=sources, generated_sha256=generated,
                patch_sha256={name:sources[m.PREFIX + name] for name in m.PATCHES})


def control_snapshot():
    sources = {p.EVIDENCE:p.EVIDENCE_SHA256}
    return dict(rows=128, enable_raw_kv=True, fresh_profile=True,
                fresh_assets=dict(profile='qwen2-public-pv16-fresh-assets-m128-v1',
                    manifest='/CONTROL_ONLY/ASSETS.json', manifest_sha256='0' * 64, enable_raw_kv=True),
                independent_reference=dict(rows=128, past_tokens=0),
                source_sha256=sources, source_manifest_sha256=m.sha(p.encoded(sources)))


class PrerequisiteTests(unittest.TestCase):
    def test_frozen_successful_m16_is_not_m128_or_full29_acceptance(self):
        value = p.evidence()
        self.assertEqual(value['run_id'], 38904754050)
        self.assertEqual(value['summary']['rows'], 16)
        self.assertIs(value['summary']['full_29_node_acceptance'], False)
        self.assertEqual((len(value['source_hashes']['source_sha256']),
                          len(value['source_hashes']['generated_sha256'])), (193, 8))

    def test_altered_missing_or_provisional_evidence_rejected(self):
        raw = (p.ROOT / p.EVIDENCE).read_bytes()
        for changed in (b'', raw + b'\n', raw.replace(b'PASS_FRESH_PUBLIC_M16_OBSERVED_GATES', b'PENDING')):
            with self.subTest(rawlen=len(changed)), self.assertRaises(ValueError):
                p.evidence(changed)
        with tempfile.TemporaryDirectory() as directory, patch.object(p, 'ROOT', Path(directory)):
            with self.assertRaises(FileNotFoundError):
                p.evidence()

    def test_only_three_explicit_variants_can_differ(self):
        old = p.evidence()['source_hashes']
        actual = dict(old['source_sha256']); actual.update(old['generated_sha256'])
        replacements = {name:str(index) * 64 for index,name in enumerate(p.VARIANTS, 1)}
        actual.update(replacements)
        result = p.compatible_sources(actual, replacements, profile=p.PROFILE, rows=128, past_tokens=0)
        self.assertIs(result['m128_executed'], False)
        self.assertIs(result['full_29_node_acceptance'], False)
        for name in actual:
            if name in p.VARIANTS:
                continue
            changed = dict(actual); changed[name] = '0' * 64
            with self.subTest(source=name), self.assertRaises(ValueError):
                p.compatible_sources(changed, replacements, profile=p.PROFILE, rows=128, past_tokens=0)
        for changed in ({}, {**replacements, 'unexpected.py':'0' * 64},
                        {name:'X' * 64 for name in p.VARIANTS}):
            with self.assertRaises(ValueError):
                p.compatible_sources(actual, changed, profile=p.PROFILE, rows=128, past_tokens=0)

    def test_exact_m128_profile_rows_and_past_domain(self):
        for values in ((p.PROFILE, True, 0), (p.PROFILE, 128, False),
                       (p.PROFILE, 16, 0), (p.PROFILE, 128, 1), ('other', 128, 0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                p.compatible_sources({}, {}, profile=values[0], rows=values[1], past_tokens=values[2])


class ContractTests(unittest.TestCase):
    def test_exact_preparation_only_contract_and_nine_overlays(self):
        value = control_contract()
        self.assertIs(m.validate_contract(value), value)
        self.assertEqual(len(value['source_sha256']), 201)
        self.assertEqual(len(value['generated_sha256']), 9)
        self.assertNotIn(p.SETUP, value['generated_sha256'])
        self.assertNotIn(m.PINS, value['source_sha256'])

    def test_canonical_keys_types_and_no_readiness_upgrade(self):
        for key, bad in (('schema', True), ('profile', 'other'), ('status', 'READY_FOR_ACTUAL_M128'),
                         ('rows', 16), ('past_tokens', False), ('enable_raw_kv', 1),
                         ('m16_evidence_sha256', '0' * 64)):
            value = control_contract(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):m.validate_contract(value)
        for key in control_contract():
            value = control_contract(); del value[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['runtime_ready'] = True
        with self.assertRaises(ValueError):m.validate_contract(value)

    def test_original_sources_cannot_be_refreshed_or_omitted(self):
        for name in p.evidence()['source_hashes']['source_sha256']:
            value = control_contract(); value['source_sha256'][name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):m.validate_contract(value)
        for name in (p.EVIDENCE, m.PREFIX + 'profile.py', m.PREFIX + 'prerequisite.py'):
            value = control_contract(); value['source_sha256'][name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['source_sha256'].pop(m.PREFIX + 'README.md')
        with self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['source_sha256']['unexpected.py'] = '0' * 64
        with self.assertRaises(ValueError):m.validate_contract(value)

    def test_seven_old_generated_files_stay_exact_and_setup_is_absent(self):
        old = p.evidence()['source_hashes']['generated_sha256']
        for name in old:
            if name == p.ENTRY:continue
            value = control_contract(); value['generated_sha256'][name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):m.validate_contract(value)
        for target in (p.SETUP, 'unexpected.py'):
            value = control_contract(); value['generated_sha256'][target] = '0' * 64
            with self.subTest(target=target), self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['generated_sha256'].pop(p.ASSETS)
        with self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['generated_sha256'][p.ENTRY] = old[p.ENTRY]
        with self.assertRaises(ValueError):m.validate_contract(value)

    def test_patch_identity_is_bound_to_the_exact_new_source_map(self):
        for name in m.PATCHES:
            value = control_contract(); value['patch_sha256'][name] = '9' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):m.validate_contract(value)
        value = control_contract(); value['patch_sha256']['setup128.patch'] = '0' * 64
        with self.assertRaises(ValueError):m.validate_contract(value)

    def test_json_and_source_paths_are_bounded_and_canonical(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}',
                    b'{"a":1.0}', b' ' * (m.MAX_JSON_BYTES + 1)):
            with self.subTest(raw=raw[:24]), self.assertRaises(ValueError):m.json_bytes(raw)
        for name in ('../outside', '/absolute', 'a//b', 'a/./b', 'a\\b', 'a\x00b'):
            with self.subTest(name=name), self.assertRaises(ValueError):m.relative_name(name)

    def test_missing_pins_and_symlink_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'ROOT', Path(directory)):
            with self.assertRaises(FileNotFoundError):m.contract_snapshot()
            path = Path(directory) / 'source.py'; path.write_text('CONTROL_ONLY')
            (Path(directory) / 'alias.py').symlink_to(path)
            with self.assertRaises(ValueError):m.read_source('alias.py')
            with self.assertRaises(ValueError):m.read_source('source.py', 2)

    def test_runtime_api_never_grants_admission_in_this_slice(self):
        with patch.object(m, 'contract_snapshot', return_value={'runtime_ready':True}) as checked:
            with self.assertRaisesRegex(ValueError, 'setup_variant_missing'):
                m.asset_source_snapshot(enable_raw_kv=True)
            checked.assert_called_once_with(composed=True)
        for bad in (False, 1, None, 'true'):
            with patch.object(m, 'contract_snapshot', side_effect=AssertionError('source access')):
                with self.assertRaises(ValueError):m.asset_source_snapshot(enable_raw_kv=bad)

    def test_run_domain_rejected_before_source_access(self):
        valid = control_snapshot()
        with patch.object(m, 'asset_source_snapshot', side_effect=AssertionError('runtime source access')):
            for budget in (True, 0, -1, 2401, 10**1000, float('inf'), float('nan'), '2400'):
                with self.subTest(budget=budget), self.assertRaises(ValueError):
                    m.authorize_run(valid, wall_budget=budget, enable_raw_kv=True, fresh_profile=True)
            for key, bad in (('rows',True), ('rows',16), ('fresh_profile',1), ('enable_raw_kv',1),
                             ('source_manifest_sha256','0' * 64)):
                value = copy.deepcopy(valid); value[key] = bad
                with self.subTest(key=key), self.assertRaises(ValueError):
                    m.authorize_run(value, wall_budget=2400, enable_raw_kv=True, fresh_profile=True)
            value = copy.deepcopy(valid); value['independent_reference']['past_tokens'] = False
            with self.assertRaises(ValueError):
                m.authorize_run(value, wall_budget=2400, enable_raw_kv=True, fresh_profile=True)
        # Even a malicious success-returning source-map stub cannot authorize work.
        with patch.object(m, 'asset_source_snapshot', return_value=valid['source_sha256']):
            with self.assertRaisesRegex(ValueError, 'setup_variant_missing'):
                m.authorize_run(valid, wall_budget=2400, enable_raw_kv=True, fresh_profile=True)


class PreparedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='m128-source-tests-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.out = Path(cls.temporary.name) / 'generated'
        cls.result = m.prepare(cls.out)

    def test_real_frozen_preparation_and_composed_source_closure(self):
        self.assertEqual(len(self.result['inputs']), 202)
        self.assertEqual(len(self.result['generated']), 9)
        self.assertIs(self.result['runtime_ready'], False)
        self.assertIs(self.result['m128_executed'], False)
        with tempfile.TemporaryDirectory(prefix='m128-source-copy-') as directory:
            root = Path(directory)
            for name in self.result['inputs']:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((m.ROOT / name).read_bytes())
            for name in self.result['generated']:(root / name).write_bytes((self.out / name).read_bytes())
            with patch.object(m, 'ROOT', root):
                result = m.contract_snapshot(composed=True)
                self.assertEqual(result['generated'], self.result['generated'])
                with self.assertRaisesRegex(ValueError, 'setup_variant_missing'):
                    m.asset_source_snapshot(enable_raw_kv=True)
                target = root / 'candidates/qwen2_resident_matrix/official_bf16/owners.py'
                target.write_bytes(target.read_bytes() + b'\n# drift\n')
                with self.assertRaises(ValueError):m.contract_snapshot(composed=True)

    def test_m16_entry_ast_projection_and_scope_drift(self):
        from candidates.qwen2_resident_matrix.raw_kv_public_fresh import prepare as old
        baseline = Path(self.temporary.name) / 'm16'
        old.prepare(baseline, enable_raw_kv=True)
        original = (baseline / p.ENTRY).read_text()
        generated = (self.out / p.ENTRY).read_text()
        m.check_entry_scope(original, generated)
        with self.assertRaises(ValueError):m.check_entry_scope(original, generated + '\nextra_callback()\n')

    def test_enabled_only_callback_mutation_cannot_update_just_patch_hash(self):
        with tempfile.TemporaryDirectory(prefix='m128-patch-drift-') as directory:
            root = Path(directory)
            value = json.loads((m.ROOT / m.PINS).read_bytes())
            for name in self.result['inputs']:
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((m.ROOT / name).read_bytes())
            name = m.PREFIX + 'entry128.patch'; path = root / name
            raw = path.read_bytes()
            before = b'+        m128_profile.authorize_run(pending,wall_budget=wall_budget,'
            after = b'+        injected_callback();m128_profile.authorize_run(pending,wall_budget=wall_budget,'
            self.assertEqual(raw.count(before), 1)
            path.write_bytes(raw.replace(before, after))
            value['source_sha256'][name] = m.sha(path.read_bytes())
            value['patch_sha256']['entry128.patch'] = value['source_sha256'][name]
            (root / m.PINS).write_bytes(p.encoded(value))
            with patch.object(m, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'generated source identity drift'):
                    m.prepare(root / 'output')


if __name__ == '__main__':
    unittest.main()
