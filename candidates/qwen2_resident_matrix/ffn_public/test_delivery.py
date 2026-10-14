"""Source-only public FFN delivery checks; no actual payloads or EDA."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
COMMIT = 'df18ba25a439fd90c846b22b9aafe992a2a6ae79'

# The last complete delivery inventory, including the historical verifier.
# Neither this immutable manifest nor its numerical receipts is refreshed.
DELIVERY_COMMIT = 'c554e502dfe462d5a0acb7030eff4bb51570bdf2'
DELIVERY_SHA256 = '0aef27a69a21b32682ba664eb941e7c33859e1a0bddcbcefbd187c76d680e8c6'
PREFIX_HISTORICAL = dict(bytes=7657, sha256='3a57df5e1ea438663dcd9fb490366317356662994c77cb567d62b94876854369')
PREFIX_CURRENT_V3 = dict(bytes=8445, sha256='5391f807b8164511d6e3e5af156f1fb3dd5f298bb0dca66504c6b818d135f880')


def file_identity(raw):
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def verify_delivery(historical, current):
    """Check frozen delivery separately from the reviewed current v3 payload.

    test_delivery.py is the versioned verifier, not a current execution payload.
    Its original bytes are checked in the frozen delivery; its running identity
    is reported separately. All 31 other current files remain exact-byte pinned,
    with only the explicitly reviewed prefix v3 replacement permitted.
    """
    for label, files in (('historical', historical), ('current', current)):
        raw = files.get('delivery_manifest.json', b'')
        if hashlib.sha256(raw).hexdigest() != DELIVERY_SHA256:
            raise ValueError(label + ' delivery manifest identity')
    delivery = json.loads(historical['delivery_manifest.json'])
    names = set(delivery['files']) | {'delivery_manifest.json'}
    for label, files in (('historical', historical), ('current', current)):
        if set(files) != names:
            raise ValueError(label + ' delivery file inventory')
    if delivery['files']['prefix_arithmetic.py'] != PREFIX_HISTORICAL:
        raise ValueError('unknown historical prefix identity')
    for name, expected in delivery['files'].items():
        if file_identity(historical[name]) != expected:
            raise ValueError('historical delivery bytes/hash: ' + name)
        if name == 'test_delivery.py':
            continue  # Current verifier has no inherited numerical PASS.
        reviewed = PREFIX_CURRENT_V3 if name == 'prefix_arithmetic.py' else expected
        if file_identity(current[name]) != reviewed:
            raise ValueError('current delivery bytes/hash: ' + name)
    return dict(historical_delivery_commit=DELIVERY_COMMIT,
                historical_manifest_sha256=DELIVERY_SHA256,
                historical_files_verified=len(delivery['files']),
                current_payload_files_verified=len(delivery['files']) - 1,
                current_prefix_source_version='qwen2-prefix-source-guard-v3',
                current_source_commit=None,
                current_source_base_commit='f16df50adfb0f1f4bc668c517a2e29accffe6753',
                historical_prefix_identity=PREFIX_HISTORICAL,
                current_prefix_identity=PREFIX_CURRENT_V3,
                current_verifier_identity=file_identity(current['test_delivery.py']),
                results_inherited=False, current_numerical_capture_executed=False,
                current_rtl_executed=False)


def read_delivery_files():
    relative = str(HERE.relative_to(HERE.parents[2]))
    names = subprocess.check_output(
        ['git', 'ls-tree', '--name-only', DELIVERY_COMMIT + ':' + relative],
        cwd=HERE.parents[2], text=True).splitlines()
    historical = {name: subprocess.check_output(
        ['git', 'show', DELIVERY_COMMIT + ':' + relative + '/' + name],
        cwd=HERE.parents[2]) for name in names}
    current = {}
    for path in HERE.iterdir():
        if path.is_symlink():
            raise ValueError('current delivery symlink: ' + path.name)
        if path.is_file():
            current[path.name] = path.read_bytes()
    return historical, current


class DeliveryTests(unittest.TestCase):
    def test_prefix_capture_keeps_actual_public_fences_and_historical_scope(self):
        receipt = json.loads((HERE / 'prefix_numerical_receipt.json').read_text())
        self.assertEqual(receipt['scope'], 'PUBLIC21_PREFIX_PC0_9_SOFTWARE_MODEL_ONLY')
        self.assertEqual([c['rows'] for c in receipt['cases']], [16, 128])
        self.assertFalse(receipt['full_block_executed'])
        self.assertFalse(receipt['whole_program_terminal_observed'])
        self.assertFalse(receipt['carried_cache_executed'])
        self.assertIsNone(receipt['hardware_cycles'])
        self.assertIsNone(receipt['full_wall_mac_utilization'])
        self.assertEqual(receipt['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')
        self.assertEqual(receipt['historical_ffn4']['commit'], '8212a32f43338163baee4126e522dcacede0fa23')
        self.assertFalse(receipt['historical_ffn4']['new_source_pass_inherited'])
        self.assertEqual(hashlib.sha256((HERE / 'numerical_receipt.json').read_bytes()).hexdigest(),
                         '011712a7bbcee20cd4226452ab7d7b7d2d1dd78e7a0b83a83899d7f85ca19541')
        root = HERE.parents[2]
        for path, digest in receipt['source_sha256'].items():
            # The prefix PASS remains bound to the immutable original source,
            # never rebound to the new fullgraph successor's live files.
            raw = subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=root)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, path)
        for case in receipt['cases']:
            rows = case['rows']
            self.assertEqual(case['prelaunch_intermediate_payloads'], [])
            self.assertEqual(case['checkpoint']['public_completion_pcs'], list(range(10)))
            self.assertTrue(case['checkpoint']['all_actual_final_acks_before_comparison'])
            self.assertTrue(case['checkpoint']['pc10_not_executed'])
            self.assertIsNone(case['host']['launch_result'])
            self.assertEqual(case['host']['accepted']['result_fire'], 0)
            self.assertEqual(case['host']['accepted']['completion_fire'], 10)
            self.assertEqual(case['public_metadata']['command']['count'], 21)
            self.assertEqual(case['public_metadata']['descriptor']['count'], 215)
            self.assertEqual(case['metadata_read_bytes'], 7168)
            self.assertEqual(case['checked_values'], rows * 7936)
            writes = case['memory_accepted']['write_ack_bytes']
            self.assertEqual(writes, rows * 7936 * 4)
            self.assertEqual(writes, case['memory_accepted']['write_data_bytes'])
            self.assertEqual(case['all_read_write_bytes'],
                             writes + case['payload_read_bytes'] + case['metadata_read_bytes'])
            self.assertEqual(set(case['outputs']), set(case['comparison']))
            for name, output in case['outputs'].items():
                c = case['comparison'][name]
                self.assertTrue(output['terminal'] and output['published'])
                self.assertEqual(output['bytes'], output['written_bytes'])
                self.assertEqual(output['bytes'], output['ack_bytes'])
                self.assertEqual(output['sha256'], c['actual_sha256'])
                self.assertEqual(c['actual_sha256'], c['independent_sha256'])
                self.assertEqual(c['independent_bit_mismatches'], 0)
                self.assertIn(c['saved_bit_mismatches'], (None, 0))
            self.assertTrue(case['observed_software_macs']['not_hardware_measurement'])
            self.assertEqual(case['observed_software_macs']['useful'], rows * 1536 * 2048)
            self.assertEqual(case['observed_software_macs']['physical_host_fmas'], 402653184)

    def test_exact_files_and_software_scope(self):
        d = json.loads((HERE / 'delivery_manifest.json').read_text())
        identity = verify_delivery(*read_delivery_files())
        self.assertEqual(identity['historical_files_verified'], 32)
        self.assertEqual(identity['current_payload_files_verified'], 31)
        self.assertFalse(identity['results_inherited'])
        self.assertFalse(identity['current_numerical_capture_executed'])
        self.assertFalse(identity['current_rtl_executed'])
        self.assertIsNone(identity['current_source_commit'])
        for key in ('rtl_executed', 'scala_host_executed', 'full_block_executed', 'actual_idma'):
            self.assertFalse(d[key])
        self.assertEqual(d['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')

    def test_public_retirement_and_actual_dependency_receipts(self):
        receipt = json.loads((HERE / 'numerical_receipt.json').read_text())
        self.assertEqual([c['rows'] for c in receipt['cases']], [16, 128])
        self.assertIsNone(receipt['hardware_cycle_prediction'])
        self.assertIsNone(receipt['full_wall_mac_utilization'])
        self.assertEqual(receipt['scope'], 'PUBLIC_FFN4_SOFTWARE_MODEL_ONLY')
        for c in receipt['cases']:
            host = c['host']
            self.assertEqual([x['pc'] for x in host['completions']], [0, 1, 2, 3])
            self.assertTrue(all(x['status'] is None for x in host['completions']))
            self.assertEqual(host['launch_result']['completed'], 4)
            self.assertEqual(host['launch_result']['jobs'], 2)
            self.assertEqual(host['accepted']['owner_result_fire'], 2)
            self.assertEqual(host['accepted']['completion_fire'], 4)
            self.assertEqual(host['accepted']['result_fire'], 1)
            self.assertEqual(c['windows'], 56)
            self.assertEqual(c['retained_a_load_fences'], 1)
            self.assertEqual(c['window_terminals'], 112)
            self.assertEqual(c['drain_terminals'], 56)
            self.assertTrue(c['same_owner_and_banks'])
            self.assertTrue(c['comparison_after_public_terminal'])
            self.assertEqual(c['act_ddr']['ack_bytes'], c['rows'] * 8960 * 4)
            self.assertEqual(c['down_ddr']['ack_bytes'], c['rows'] * 1536 * 4)
            self.assertEqual(c['actual_act_source']['sha256'], c['act_ddr']['sha256'])
            self.assertTrue(c['actual_act_source']['actual_prior_ack_written'])
            self.assertTrue(c['down_final_ack_fence']['terminal_strictly_after_final_ack'])
            self.assertEqual(c['metadata']['physical_read_bytes'], c['metadata']['physical_read_beats'] * 64)
            self.assertEqual(c['metadata']['command_records'], 4)
            self.assertEqual(c['metadata']['descriptor_records'], 43)
            self.assertEqual(len(c['physical_spans']), 11)
            for output in c['comparison'].values():
                self.assertEqual(output['independent_direct_bit_mismatches'], 0)
                self.assertEqual(output['saved_producer_bit_mismatches'], 0)
                self.assertEqual(output['actual_sha256'], output['direct_sha256'])
                self.assertEqual(output['actual_sha256'], output['saved_sha256'])


class DeliveryIdentityGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historical, cls.current = read_delivery_files()

    def test_manifest_bytes_cannot_be_refreshed_or_reformatted(self):
        for which in ('historical', 'current'):
            for raw in (b'{}', self.historical['delivery_manifest.json'] + b'\n'):
                files = dict(getattr(self, which), **{'delivery_manifest.json': raw})
                pair = (files, self.current) if which == 'historical' else (self.historical, files)
                with self.subTest(which=which), self.assertRaisesRegex(ValueError, which + ' delivery manifest'):
                    verify_delivery(*pair)

    def test_missing_or_extra_files_fail_closed(self):
        for which in ('historical', 'current'):
            for missing in self.historical:
                files = dict(getattr(self, which)); del files[missing]
                pair = (files, self.current) if which == 'historical' else (self.historical, files)
                with self.subTest(which=which, missing=missing), self.assertRaises(ValueError):
                    verify_delivery(*pair)
            files = dict(getattr(self, which), **{'unreviewed.py': b''})
            pair = (files, self.current) if which == 'historical' else (self.historical, files)
            with self.assertRaisesRegex(ValueError, which + ' delivery file inventory'):
                verify_delivery(*pair)

    def test_all_historical_bytes_and_hashes_remain_strict(self):
        for name, raw in self.historical.items():
            if name == 'delivery_manifest.json':
                continue
            for bad in (raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
                files = dict(self.historical, **{name: bad})
                with self.subTest(name=name, bytes=len(bad)), self.assertRaisesRegex(ValueError, 'historical delivery bytes/hash'):
                    verify_delivery(files, self.current)

    def test_all_current_payload_bytes_and_hashes_remain_strict(self):
        for name, raw in self.current.items():
            if name in ('delivery_manifest.json', 'test_delivery.py'):
                continue
            for bad in (raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
                files = dict(self.current, **{name: bad})
                with self.subTest(name=name, bytes=len(bad)), self.assertRaisesRegex(ValueError, 'current delivery bytes/hash'):
                    verify_delivery(self.historical, files)

    def test_historical_and_current_prefix_are_not_interchangeable(self):
        name = 'prefix_arithmetic.py'
        with self.assertRaisesRegex(ValueError, 'historical delivery bytes/hash'):
            verify_delivery(dict(self.historical, **{name: self.current[name]}), self.current)
        with self.assertRaisesRegex(ValueError, 'current delivery bytes/hash'):
            verify_delivery(self.historical, dict(self.current, **{name: self.historical[name]}))

    def test_current_receipts_cannot_be_rebound_even_together(self):
        names = ('numerical_receipt.json', 'prefix_numerical_receipt.json',
                 'fullgraph_numerical_receipt.json')
        for name in names:
            raw = self.current[name] + b'\n'
            historical = dict(self.historical, **{name: raw})
            current = dict(self.current, **{name: raw})
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'historical delivery bytes/hash'):
                verify_delivery(historical, current)

    def test_live_prefix_guard_has_explicit_v3_default_off_provenance(self):
        sys.path.insert(0, str(HERE.parents[2]))
        try:
            from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import source_identity
            identity = source_identity(HERE.parents[2])
        finally:
            sys.path.pop(0)
        self.assertEqual(identity['source_version'], 'qwen2-prefix-source-guard-v3')
        self.assertEqual(identity['source_base_commit'], 'f16df50adfb0f1f4bc668c517a2e29accffe6753')
        self.assertIsNone(identity['source_commit'])
        for key in ('historical_results_inherited', 'borrower_enabled',
                    'elementwise_loan_enabled', 'hardware_simulation'):
            self.assertIs(identity[key], False, key)
        for key in ('enable_h2048_rms_borrower', 'external_elementwise_loan'):
            for value in (True, 0, None):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'default-disabled'):
                    source_identity(HERE.parents[2], **{key: value})

if __name__ == '__main__':
    unittest.main()
