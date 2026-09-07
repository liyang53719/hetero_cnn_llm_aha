#!/usr/bin/env python3
"""Metadata/verification tests only; never count them as numerical DUT passes."""
from pathlib import Path
import copy
import gzip
import json
import os
import struct
import sys
import unittest
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from pack_owner_multilayer_fixture import pack_layers
from verify_real_two_layer import fixed_contract, compare_all


class RealTwoLayerContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get('OWNER_TEST_ARTIFACTS', '/tmp/owner_real2_tests'))
        cls.out = root / uuid.uuid4().hex
        cls.out.mkdir(parents=True)
        shape = dict(H=1536, F=8960, HEADS=12, KVHEADS=2, HD=128, MAX_TOKENS=1024)
        cls.fixture = pack_layers(shape, 16, 2, cls.out / 'fixture', 9467985920)

    def altered(self):
        return copy.deepcopy(self.fixture)

    def test_real_geometry_and_direct_alias(self):
        fixed_contract(self.fixture)

    def test_tiny_is_not_real(self):
        m = self.altered(); m['shape']['H'] = 64
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_three_layers_are_not_this_gate(self):
        m = self.altered(); m['layers'] = 3
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_wrong_tokens_and_types(self):
        for value in (1, 17, 1024, '16', True):
            with self.subTest(value=value):
                m = self.altered(); m['tokens'] = value
                with self.assertRaises(ValueError): fixed_contract(m)

    def test_no_missing_command(self):
        m = self.altered(); m['schedule'].pop()
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_no_wrong_layer_ownership(self):
        m = self.altered(); m['schedule'][21]['layer'] = 0
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_no_hidden_copy_alias(self):
        m = self.altered(); m['tensors']['l1_x']['address'] += 64
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_no_host_initialization_of_second_hidden(self):
        for change in ('permission', 'allocation'):
            with self.subTest(change=change):
                m = self.altered()
                if change == 'permission': m['tensors']['l1_x']['readonly'] = True
                else: m['allocations'].append('l1_x')
                with self.assertRaises(ValueError): fixed_contract(m)

    def test_no_identical_weight_stimulus(self):
        m = self.altered(); m['layer_weight_salts'] = [0, 0]
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_seven_matrix_allocations_are_distinct(self):
        for name in ('wq', 'wk', 'wv', 'wo', 'wg', 'wu', 'wd'):
            with self.subTest(name=name):
                m = self.altered(); m['tensors']['l1_' + name]['address'] = m['tensors']['l0_' + name]['address']
                with self.assertRaises(ValueError): fixed_contract(m)

    def test_second_output_does_not_overwrite_first(self):
        m = self.altered(); m['tensors']['l1_y']['address'] = m['tensors']['l0_y']['address']
        with self.assertRaises(ValueError): fixed_contract(m)

    def test_compare_rejects_nonfinite_mismatch_or_short_output(self):
        for bits, reference in ((0x7fc00001, 0x7fc00001), (0x3f800001, 0x3f800000), (0, 0)):
            with self.subTest(bits=bits, reference=reference):
                out = self.out / uuid.uuid4().hex; (out / 'tensors').mkdir(parents=True)
                for kind, u in [('actual', bits), ('reference', reference)]:
                    (out / 'tensors' / ('y_' + kind + '.f32le')).write_bytes(struct.pack('<I', u))
                with gzip.open(out / 'all_owner_elements.csv.gz', 'wt') as f:
                    f.write('pc,tensor,index,actual_hex,reference_hex\n')
                    f.write(f'0,y,0,{bits:08x},{reference:08x}\n')
                fixture = {'schedule': [{'pc': 0, 'outputs': ['y']}], 'tensors': {'y': {'words': 1}}}
                with self.assertRaises(ValueError): compare_all(out, fixture)


if __name__ == '__main__':
    unittest.main(verbosity=2)
