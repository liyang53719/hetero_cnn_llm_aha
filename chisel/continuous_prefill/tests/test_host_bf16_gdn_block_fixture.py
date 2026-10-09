"""Small full-block source/geometry/threshold tests, no checkpoint execution."""
from pathlib import Path
import copy
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import pack_host_bf16_gdn_block_fixture as fixture
from host_bf16_gdn_block_descriptor import parse_host_gdn_block_commands, validate_host_gdn_block_continuation

class GdnBlockFixtureTests(unittest.TestCase):
    def test_all_seventeen_operators_are_public_and_prior_actual_producers(self):
        layout = fixture.build_layout(); decoded = []; producers = {}; outputs = []
        for token, launch in enumerate(layout['launches']):
            bindings = parse_host_gdn_block_commands([int(x,16) for x in launch['packed_commands']],
                {i:int(x,16) for i,x in enumerate(launch['packed_descriptors'])})
            decoded.append(bindings)
            self.assertEqual((len(bindings), launch['descriptor_records']), (17,216))
            self.assertEqual(launch['command_limit']-launch['command_base'],320)
            self.assertEqual([b.expected_generation for b in bindings], [token]*17)
            self.assertEqual([o['kind'] for o in launch['operations']], list(fixture.KINDS))
            for pc, op in enumerate(launch['operations']):
                for source in op['reads']:
                    if source['producer'] >= 0:
                        self.assertLess(source['producer'], token*17+pc)
                        self.assertEqual(producers[source['address']], source['producer'])
                for span in op['writes']:
                    for previous in outputs:
                        self.assertTrue(span['address']+span['bytes'] <= previous['address'] or
                                        previous['address']+previous['bytes'] <= span['address'])
                    outputs.append(span); producers[span['address']] = token*17+pc
        validate_host_gdn_block_continuation(*decoded)
        self.assertEqual(layout['launches'][1]['operations'][4]['reads'][2]['producer'],4)
        self.assertEqual(layout['launches'][1]['operations'][6]['reads'][1]['producer'],6)
        self.assertEqual(layout['actual_write_bytes'],2388096)
        self.assertEqual((fixture.ACTUAL_DENSE_MACS, fixture.REFERENCE_FMA_STEPS),(43057152,43515904))

    def test_raw_initialization_and_padded_tables(self):
        layout=fixture.build_layout(); files={}
        fixture._write_launch(layout, lambda name, value: files.update({name:value}))
        names={entry['file'] for entry in layout['inputs']}
        self.assertEqual(len(names),17)
        self.assertIn('hidden0.bf16le',names); self.assertIn('hidden1.bf16le',names)
        self.assertFalse(any(n.startswith(('expected_', 'native_', 'activation')) for n in names))
        self.assertEqual(len(files['host_commands0.bin']),320)
        self.assertEqual(files['host_commands0.bin'][272:],bytes(48))
        self.assertEqual(len(files['host_descriptors0.bin']),3456)
        self.assertTrue(files['launch.txt'].startswith(b'HOST_GDN_BLOCK_V3\n'))

    def test_original_full_block_hidden_and_fp32_state_thresholds_are_independent(self):
        canonical=[{name:np.zeros(32,'<u2') for name in fixture.KINDS[:-1]+('history',)} for _ in range(2)]
        for row in canonical: row['state']=np.zeros((1,32),'<f4')
        native=copy.deepcopy(canonical)
        self.assertTrue(all(r['passed'] for r in fixture.native_full_block_metrics(canonical,native)))
        native[1]['residual2'][0]=0x3d80 # .0625 > block .05
        native[0]['post_norm'][0]=0x3d40 # .046875 > operator .03125
        native[1]['state'][0,0]=np.float32(.0002)
        checks=fixture.native_full_block_metrics(canonical,native)
        self.assertFalse(checks[0]['passed']); self.assertFalse(checks[1]['passed'])
        self.assertEqual(checks[1]['checks']['residual2']['thresholds'],{'max_abs':.05,'mean_abs':.01})
        self.assertEqual(checks[0]['checks']['post_norm']['thresholds'],{'max_abs':.03125,'mean_abs':.005})
        self.assertEqual(checks[1]['checks']['state']['atol'],1e-4)
        self.assertEqual(checks[1]['checks']['state']['rtol'],1e-4)
        self.assertFalse(checks[1]['checks']['state']['pass'])

    def test_live_source_authority_cannot_be_forged(self):
        with self.assertRaises(TypeError): fixture.GdnBlockFixtureSession()
        with self.assertRaisesRegex(ValueError,'unissued'):
            object.__new__(fixture.GdnBlockFixtureSession).verify('/tmp')

if __name__=='__main__': unittest.main()
